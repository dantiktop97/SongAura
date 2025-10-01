import os
import sys
import asyncio
from telethon import TelegramClient, events
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

# --- Настройки из окружения ---
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# --- Папка для сессий ---
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

# --- Aiogram bot setup ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Вспомогательные функции ---
def safe_session_name(phone: str) -> str:
    return phone.replace("+", "").replace(" ", "").replace("/", "_")

def list_sessions():
    return [f[:-8] for f in os.listdir(SESSIONS_DIR) if f.endswith(".session")]

async def get_client(session_name: str):
    path = os.path.join(SESSIONS_DIR, session_name)
    client = TelegramClient(path, API_ID, API_HASH, device_model="iPhone 13 Pro", system_version="iOS 18.1.1", app_version="9.6.0")
    await client.connect()
    return client

async def fetch_chats(session_name: str, limit: int = 10):
    client = await get_client(session_name)
    try:
        dialogs = await client.get_dialogs(limit=limit)
        return [(d.title or d.name or "ЛС", d.id) for d in dialogs]
    finally:
        await client.disconnect()

async def fetch_messages(session_name: str, chat_id: int, limit: int = 5):
    client = await get_client(session_name)
    try:
        msgs = []
        async for m in client.iter_messages(chat_id, limit=limit):
            text = m.text or "<media>"
            sender = getattr(m, "sender_id", None)
            msgs.append(f"{sender}: {text}")
        return msgs
    finally:
        await client.disconnect()

# --- Мониторинг новых сообщений (одно подключение на сессию) ---
MONITORS = {}  # session_name -> asyncio.Task

async def monitor_session(session_name: str):
    path = os.path.join(SESSIONS_DIR, session_name)
    client = TelegramClient(path, API_ID, API_HASH)
    await client.start()
    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        chat = await event.get_chat()
        name = getattr(chat, "title", None) or getattr(chat, "first_name", "ЛС")
        text = event.text or "📎 Медиа"
        await bot.send_message(ADMIN_ID, f"📩 [{session_name}] {name}:\n{text}")
    try:
        await client.run_until_disconnected()
    finally:
        await client.disconnect()

# --- Ui для админа ---
def main_menu_markup():
    sessions = list_sessions()
    buttons = [[InlineKeyboardButton(text=f"👤 {s}", callback_data=f"account:{s}")] for s in sessions]
    if not buttons:
        buttons = [[InlineKeyboardButton(text="❌ Нет аккаунтов", callback_data="none")]]
    buttons.append([InlineKeyboardButton(text="➕ Добавить (register)", callback_data="add")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        await msg.answer("🚫 Нет доступа")
        return
    await msg.answer("👑 Выберите аккаунт:", reply_markup=main_menu_markup())

@dp.callback_query()
async def on_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.message.answer("🚫 Нет доступа")
        return
    data = (call.data or "").split(":")
    action = data[0]
    if action == "account":
        session = data[1]
        chats = await fetch_chats(session, limit=10)
        buttons = [[InlineKeyboardButton(text=f"💬 {name}", callback_data=f"chat:{session}:{chat_id}")] for name, chat_id in chats]
        buttons.append([InlineKeyboardButton(text="📡 Мониторинг", callback_data=f"monitor:{session}")])
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
        await call.message.answer(f"📂 Аккаунт {session}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    elif action == "chat":
        session, chat_id = data[1], int(data[2])
        msgs = await fetch_messages(session, chat_id, limit=5)
        text = "\n".join(msgs) if msgs else "❌ Нет сообщений"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data=f"account:{session}")]])
        await call.message.answer(f"💬 Сообщения:\n\n{text}", reply_markup=kb)
    elif action == "monitor":
        session = data[1]
        if session in MONITORS:
            await call.message.answer(f"⚡ Мониторинг {session} уже запущен")
            return
        task = asyncio.create_task(monitor_session(session))
        MONITORS[session] = task
        await call.message.answer(f"📡 Мониторинг {session} запущен")
    elif action == "back":
        await call.message.answer("🔙 Главное меню", reply_markup=main_menu_markup())
    elif action == "add":
        await call.message.answer("Добавление аккаунта: запусти локально `python register.py` и загрузь .session в папку sessions/")

# --- Обработка обычного текста (поиск, если нужно) ---
SEARCH_STATE = {}  # user_id -> (session, chat_id)

@dp.message()
async def on_text(msg: types.Message):
    uid = msg.from_user.id
    if uid in SEARCH_STATE:
        session, chat_id = SEARCH_STATE.pop(uid)
        query = msg.text.strip().lower()
        client = await get_client(session)
        try:
            results = []
            async for m in client.iter_messages(chat_id, limit=200):
                if m.text and query in m.text.lower():
                    results.append(m.text)
                    if len(results) >= 5:
                        break
            await msg.answer("🔍 Результаты:\n\n" + ("\n\n".join(results) if results else "❌ Ничего"))
        finally:
            await client.disconnect()
    else:
        await msg.answer("👋 Используй /start")

# --- CLI регистрация аккаунта (register.py функционал встроен) ---
async def register_cli():
    phone = input("Введите номер телефона (например +491234567890): ").strip()
    session_name = safe_session_name(phone)
    path = os.path.join(SESSIONS_DIR, session_name)
    client = TelegramClient(path, API_ID, API_HASH)
    await client.start(phone=phone)
    me = await client.get_me()
    print("Успешно:", me.stringify())
    await client.disconnect()

# --- Точка входа ---
async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "register":
        await register_cli()
        return
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
