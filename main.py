import os
import sys
import asyncio
from telethon import TelegramClient
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
    client = TelegramClient(
        f"sessions/{session_name}",
        API_ID,
        API_HASH
    )
    msgs = []
    async with client:
        async for msg in client.iter_messages(chat_id, limit=5):
            msgs.append(f"{msg.sender_id}: {msg.text}")
    return msgs

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

    # Выбор аккаунта → сразу список чатов
    if action == "account":
        session = data[1]
        chats = await get_chats(session)
        buttons = [
            [InlineKeyboardButton(text=f"💬 {name}", callback_data=f"chat:{session}:{chat_id}")]
            for name, chat_id in chats
        ]
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back")])
        await call.message.answer(f"📂 Чаты аккаунта `{session}`:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    # Выбор чата → последние сообщения
    elif action == "chat":
        session, chat_id = data[1], int(data[2])
        msgs = await get_messages(session, chat_id)
        text = "\n".join(msgs) if msgs else "❌ Нет сообщений"
        buttons = [[InlineKeyboardButton(text="🔙 Назад", callback_data=f"account:{session}")]]
        await call.message.answer(f"💬 Сообщения:\n\n{text}", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

    elif action == "back":
        await call.message.answer("🔙 Главное меню:", reply_markup=get_main_menu())

    elif action == "add":
        await call.message.answer("📲 Добавление аккаунта пока доступно только через консоль:\n\n`python3 main.py register`")

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
