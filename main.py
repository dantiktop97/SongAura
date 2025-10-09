# -*- coding: utf-8 -*-
import asyncio
import os
import logging
import sys
from telethon import TelegramClient, errors
from telethon.errors import FloodWaitError

# Получаем из секретов Render
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")

# Список целевых чатов (из твоего сообщения)
target_chats = [
    -1002163895139,
    -1001300573578,
    -1002094964873,
    -1002423716563,
    -1002768695068
]

# Текст сообщения
message_text = """ХОЧЕШЬ НАКРУТИТЬ ПОДПИСЧИКОВ ИЛИ РЕАКЦИЙ❓

✅ТОГДА ТЕБЕ К НАМ ✅

✅НАКРУТКА ЗА РЕФЕРАЛОВ✅

👇👇👇

👉  @Hshzgsbot (https://t.me/Hshzgsbot?start=7902738665)  👈
"""

# Через сколько секунд начать рассылку (15 минут)
START_DELAY = 15 * 60
# Задержка между отправками в разные чаты
SEND_DELAY = 2

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

client = TelegramClient(SESSION, API_ID, API_HASH)

async def send_to_chat(chat_id: int, text: str):
    try:
        await client.send_message(chat_id, text)
        logging.info(f"✅ Sent to chat {chat_id}")
    except FloodWaitError as e:
        logging.warning(f"FloodWait {e.seconds} sec for chat {chat_id}")
        await asyncio.sleep(e.seconds + 1)
        await send_to_chat(chat_id, text)
    except errors.RPCError as e:
        logging.error(f"RPC error for {chat_id}: {e}")
    except Exception as e:
        logging.exception(f"Unexpected error for {chat_id}: {e}")

async def main():
    await client.start()
    logging.info(f"✅ Client authorized. Waiting {START_DELAY} sec before sending...")
    await asyncio.sleep(START_DELAY)

    for chat_id in target_chats:
        await send_to_chat(chat_id, message_text)
        await asyncio.sleep(SEND_DELAY)

    logging.info("✅ All messages sent. Exiting.")

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        logging.info("🛑 Interrupted")
    finally:
        if client.is_connected():
            client.disconnect()
