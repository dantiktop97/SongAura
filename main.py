import os
import asyncio
import threading
from flask import Flask
import telebot
from telethon import TelegramClient

# === Конфигурация ===
TOKEN = os.getenv("PLAY")
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", 8000))
SESSION_NAME = "me_userbot"

if not TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("PLAY, API_ID или API_HASH не заданы")

# === Инициализация ===
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(name)

# === Целевые чаты и сообщение ===
targets = [
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

report_user_id = 7902738665
interval_minutes = 15

# === Рассылка через Telethon ===
async def send_messages(client):
    success = []
    failed = []
    for chat_id in targets:
        try:
            await client.send_message(chat_id, message_text)
            success.append(str(chat_id))
        except Exception:
            failed.append(str(chat_id))
    report = "📢 Отчёт по рассылке:\n\n"
    report += "✅ Отправлено в:\n" + ("\n".join(success) if success else "нет") + "\n\n"
    report += "❌ Ошибки при отправке:\n" + ("\n".join(failed) if failed else "нет")
    await client.send_message(report_user_id, report)

async def auto_loop():
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        while True:
            await send_messages(client)
            await asyncio.sleep(interval_minutes * 60)

def start_autoposter():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(auto_loop())

# === Web и polling ===
@app.route("/")
def index():
    return "Bot is running"

def start_bot():
    bot.polling(none_stop=True)

if name == "main":
    threading.Thread(target=start_autoposter, daemon=True).start()
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
