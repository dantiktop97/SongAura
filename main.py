import os
import json
import threading
import asyncio
from flask import Flask
import telebot
from telethon import TelegramClient

# ====== Конфиги ======
TOKEN = os.getenv("PLAY")       # Токен бота из секрета PLAY
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
PORT = int(os.getenv("PORT", "8000"))
SESSION_NAME = "me_userbot"    # имя файла сессии Telethon

if not TOKEN or not API_ID or not API_HASH:
    raise RuntimeError("Не заданы обязательные переменные PLAY, API_ID или API_HASH")

# ====== Инициализация ======
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(name)

# ====== Баланс ====== (если нужен, можно убрать)
BALANCE_FILE = "balances.json"
balances_lock = threading.Lock()

def load_balances():
    try:
        with balances_lock:
            if not os.path.exists(BALANCE_FILE):
                return {}
            with open(BALANCE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}

def save_balances(balances):
    try:
        with balances_lock:
            with open(BALANCE_FILE, "w", encoding="utf-8") as f:
                json.dump(balances, f, ensure_ascii=False)
    except Exception as e:
        print("Ошибка сохранения балансов:", e)

balances = load_balances()

# ====== Целевые чаты и сообщение ======
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

report_user_id = 7902738665  # куда слать отчет
interval_minutes = 15

# ====== Функция авторассылки ======
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
    report += "❌ Ошибки при отправке в:\n" + ("\n".join(failed) if failed else "нет") + "\n"
    await client.send_message(report_user_id, report)

async def bot_loop():
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        while True:
            await send_messages(client)
            await asyncio.sleep(interval_minutes * 60)

def start_telethon_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(bot_loop())

# ====== Flask + Telebot сервер ======
@app.route("/")
def index():
    return "Bot is running"

def run_telebot():
    bot.polling(none_stop=True)

if name == "main":
    threading.Thread(target=start_telethon_bot, daemon=True).start()
    threading.Thread(target=run_telebot, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
