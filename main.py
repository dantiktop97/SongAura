import os
import asyncio
import threading
from flask import Flask
from telethon import TelegramClient
from telethon.sessions import StringSession

# 🔐 Данные из переменных окружения (Render → Environment)
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")

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

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Авторассылка Telegram активна"

async def send_ads():
    await client.start()
    while True:
        print("📤 Рассылка началась")
        for chat_id in target_chats:
            try:
                await client.send_message(chat_id, message_text)
                print(f"✅ Отправлено в {chat_id}")
                await asyncio.sleep(10)
            except Exception as e:
                print(f"❌ Ошибка при отправке в {chat_id}: {e}")
        print("⏳ Ждем 1 час...")
        await asyncio.sleep(3600)

def start_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(send_ads())

if __name__ == "__main__":
    threading.Thread(target=start_bot).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 10000)))
