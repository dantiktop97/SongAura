# send_in_15min.py
import os
import asyncio
import random
from datetime import datetime
from telethon import TelegramClient, errors
from telethon.tl.types import InputPeerChannel

# Конфиг из окружения на Render
SESSION = os.environ.get("SESSION")        # string session
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "0"))

# Целевые чаты и текст сообщения
target_chats = [
    -1002163895139,
    -1001300573578,
    -1002094964873,
    -1002423716563,
    -1002768695068
]

message_text = """
ХОЧЕШЬ НАКРУТИТЬ ПОДПИСЧИКОВ ИЛИ РЕАКЦИЙ❓

✅ТОГДА ТЕБЕ К НАМ ✅

✅НАКРУТКА ЗА РЕФЕРАЛОВ✅

          👇👇👇

👉  @Hshzgsbot (https://t.me/Hshzgsbot?start=7902738665)  👈
"""

# Параметры безопасности рассылки
BATCH_SIZE = 1               # отправляем по одному чату за итерацию
MIN_DELAY = 2.0              # минимальная пауза между отправками в секундах
MAX_DELAY = 5.0              # максимальная пауза между отправками в секундах
PAUSE_BETWEEN_BATCHES = 3.0  # пауза между батчами в секундах
START_DELAY_SECONDS = 15 * 60  # ждать 15 минут перед рассылкой

client = TelegramClient(SESSION, API_ID, API_HASH)

async def safe_send(chat_id: int, text: str) -> bool:
    try:
        await client.send_message(chat_id, text)
        return True
    except errors.FloodWaitError as e:
        wait = e.seconds + 1
        await asyncio.sleep(wait)
        try:
            await client.send_message(chat_id, text)
            return True
        except Exception:
            return False
    except (errors.UserIsBlockedError, errors.InputUserDeactivatedError, errors.ChatWriteForbiddenError):
        return False
    except Exception:
        return False

async def send_all():
    success = 0
    fail = 0
    # ждем стартовое время
    start_at = datetime.utcnow() + timedelta(seconds=START_DELAY_SECONDS)
    await client.send_message(ADMIN_ID, f"Рассылка запланирована на {start_at.isoformat()} UTC")
    await asyncio.sleep(START_DELAY_SECONDS)
    # отправляем в батчах
    for i in range(0, len(target_chats), BATCH_SIZE):
        batch = target_chats[i:i+BATCH_SIZE]
        for chat_id in batch:
            ok = await safe_send(chat_id, message_text)
            if ok:
                success += 1
            else:
                fail += 1
            await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
        await asyncio.sleep(PAUSE_BETWEEN_BATCHES)
    # уведомление админу
    try:
        await client.send_message(ADMIN_ID, f"Рассылка завершена. Успех: {success}, Ошибки: {fail}")
    except Exception:
        pass

from datetime import timedelta

async def main():
    await client.start()
    await send_all()
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
