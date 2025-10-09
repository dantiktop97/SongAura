# -*- coding: utf-8 -*-
"""
Hourly broadcast with jitter and FloodWait handling.
Timing parameters are hardcoded here (NOT stored in secrets).
Render Secrets required only: API_ID, API_HASH, SESSION
"""

import asyncio
import logging
import sys
import random
from telethon import TelegramClient, errors
from telethon.errors import FloodWaitError
import os

# ---------------------------
# Secrets (only these must be in Render Secrets)
# ---------------------------
API_ID = int(os.getenv("API_ID"))      # secret
API_HASH = os.getenv("API_HASH")       # secret
SESSION = os.getenv("SESSION")         # secret

# ---------------------------
# Timing & behaviour (HARD-CODED — change in this file, not secrets)
# ---------------------------
# Initial wait before first broadcast (seconds)
START_DELAY = 15 * 60        # 15 minutes

# Base interval between broadcasts (seconds)
SEND_INTERVAL = 60 * 60      # 1 hour

# Interval jitter ± seconds (to avoid exact schedule)
INTERVAL_JITTER = 5 * 60     # ±5 minutes

# Base delay between sending to different chats (seconds)
SEND_DELAY = 2.0

# Jitter for per-chat send delay (seconds)
SEND_DELAY_JITTER = 1.0

# Minimum sleep enforced between rounds (seconds)
MIN_INTERVAL = 60            # at least 1 minute

# Optional: number of rounds to run (0 = infinite)
RUNS_LIMIT = 0

# Randomize order of chats each round?
RANDOMIZE_CHAT_ORDER = True

# ---------------------------
# Target chats & message (also not secret)
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
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

client = TelegramClient(SESSION, API_ID, API_HASH)

# ---------------------------
# Send helpers
# ---------------------------
async def send_to_chat(chat_id: int, text: str):
    try:
        await client.send_message(chat_id, text)
        logging.info(f"✅ Sent to chat {chat_id}")
    except FloodWaitError as e:
        logging.warning(f"FloodWait {e.seconds}s for chat {chat_id}, waiting...")
        await asyncio.sleep(e.seconds + 1)
        await send_to_chat(chat_id, text)
    except errors.RPCError as e:
        logging.error(f"❌ RPC error for {chat_id}: {e}")
    except Exception as e:
        logging.exception(f"❌ Unexpected error for {chat_id}: {e}")

async def send_broadcast():
    """Send message to all chats (optionally random order)."""
    chats = list(target_chats)
    if RANDOMIZE_CHAT_ORDER:
        random.shuffle(chats)
        logging.info("🔀 Chat order randomized this round")

    logging.info(f"📤 Starting broadcast to {len(chats)} chats...")
    for chat_id in chats:
        await send_to_chat(chat_id, message_text)
        # per-chat randomized delay
        delay = SEND_DELAY + random.uniform(-SEND_DELAY_JITTER, SEND_DELAY_JITTER)
        delay = max(0.5, delay)
        logging.info(f"⏱ Sleeping {delay:.2f}s before next chat")
        await asyncio.sleep(delay)
    logging.info("✅ Broadcast complete")

# ---------------------------
# Main loop
# ---------------------------
async def main_loop():
    await client.start()
    logging.info("✅ Client started and authorized.")
    logging.info(f"⏳ Waiting initial START_DELAY = {START_DELAY} seconds before first broadcast...")
    await asyncio.sleep(START_DELAY)

    rounds_done = 0
    while True:
        rounds_done += 1
        logging.info(f"📊 Starting round #{rounds_done}")
        await send_broadcast()

        if RUNS_LIMIT > 0 and rounds_done >= RUNS_LIMIT:
            logging.info(f"🏁 Reached RUNS_LIMIT={RUNS_LIMIT}. Exiting.")
            break

        # compute next interval with jitter
        jitter = random.randint(-INTERVAL_JITTER, INTERVAL_JITTER)
        interval = SEND_INTERVAL + jitter
        if interval < MIN_INTERVAL:
            interval = MIN_INTERVAL
        logging.info(f"⏳ Next broadcast in ~{interval} seconds (~{interval/60:.1f} minutes)")
        await asyncio.sleep(interval)

if __name__ == "__main__":
    try:
        client.loop.run_until_complete(main_loop())
    except KeyboardInterrupt:
        logging.info("🛑 Interrupted by user")
    finally:
        if client.is_connected():
            client.disconnect()
        logging.info("👋 Client disconnected")
