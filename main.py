# -*- coding: utf-8 -*-
"""
Hourly broadcast using Pyrogram (works on Render/iPhone).
Secrets required: API_ID, API_HASH, SESSION
Timing parameters are hardcoded (not secrets).
"""

import asyncio
import logging
import random
import os
from pyrogram import Client
from pyrogram.errors import FloodWait

# ---------------------------
# Secrets
# ---------------------------
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")  # session string

# ---------------------------
# Timing & behavior
# ---------------------------
START_DELAY = 15 * 60        # wait 15 min before first broadcast
SEND_INTERVAL = 60 * 60      # base interval = 1 hour
INTERVAL_JITTER = 5 * 60     # ±5 min
SEND_DELAY = 2.0             # delay between chats
SEND_DELAY_JITTER = 1.0      # ±1 sec random jitter
MIN_INTERVAL = 60            # minimum interval 1 min
RUNS_LIMIT = 0               # 0 = infinite
RANDOMIZE_CHAT_ORDER = True  # random chat order each round

# ---------------------------
# Target chats & message
# ---------------------------
target_chats = [
    -1002163895139,
    -1001300573578,
    -1002094964873,
    -1002423716563,
    -1002768695068
]

message_text = """ХОЧЕШЬ НАКРУТИТЬ ПОДПИСЧИКОВ ИЛИ РЕАКЦИЙ❓

✅ТОГДА ТЕБЕ К НАМ ✅

✅НАКРУТКА ЗА РЕФЕРАЛОВ✅

👇👇👇

👉  @Hshzgsbot (https://t.me/Hshzgsbot?start=7902738665)  👈
"""

# ---------------------------
# Logging
# ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# ---------------------------
# Pyrogram client
# ---------------------------
app = Client(SESSION, api_id=API_ID, api_hash=API_HASH)

# ---------------------------
# Sending helpers
# ---------------------------
async def send_to_chat(chat_id, text):
    try:
        await app.send_message(chat_id, text)
        logging.info(f"✅ Sent to chat {chat_id}")
    except FloodWait as e:
        logging.warning(f"FloodWait {e.x} seconds for chat {chat_id}, waiting...")
        await asyncio.sleep(e.x + 1)
        await send_to_chat(chat_id, text)
    except Exception as e:
        logging.exception(f"❌ Error sending to {chat_id}: {e}")

async def send_broadcast():
    chats = list(target_chats)
    if RANDOMIZE_CHAT_ORDER:
        random.shuffle(chats)
        logging.info("🔀 Chat order randomized this round")

    logging.info(f"📤 Broadcasting to {len(chats)} chats...")
    for chat_id in chats:
        await send_to_chat(chat_id, message_text)
        delay = max(0.5, SEND_DELAY + random.uniform(-SEND_DELAY_JITTER, SEND_DELAY_JITTER))
        logging.info(f"⏱ Sleeping {delay:.2f}s before next chat")
        await asyncio.sleep(delay)
    logging.info("✅ Broadcast complete")

async def main_loop():
    async with app:
        logging.info(f"⏳ Waiting {START_DELAY} seconds before first broadcast...")
        await asyncio.sleep(START_DELAY)

        rounds_done = 0
        while True:
            rounds_done += 1
            logging.info(f"📊 Starting round #{rounds_done}")
            await send_broadcast()

            if RUNS_LIMIT > 0 and rounds_done >= RUNS_LIMIT:
                logging.info(f"🏁 Reached RUNS_LIMIT={RUNS_LIMIT}. Exiting.")
                break

            interval = SEND_INTERVAL + random.randint(-INTERVAL_JITTER, INTERVAL_JITTER)
            interval = max(MIN_INTERVAL, interval)
            logging.info(f"⏳ Next broadcast in ~{interval} sec (~{interval/60:.1f} min)")
            await asyncio.sleep(interval)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logging.info("🛑 Interrupted by user")
