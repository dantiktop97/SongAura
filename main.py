import os
import asyncio
from flask import Flask
from telethon import TelegramClient

# === Конфигурация ===
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_NAME = "user_session"  # Файл сохранится как user_session.session
PORT = int(os.getenv("PORT", 8000))

# === Целевые чаты и сообщение ===
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

report_user_id = 7902738665
interval_minutes = 15

# === Flask — чтобы Render не вырубил процесс ===
app = Flask(name)

@app.route('/')
def home():
    return "AutoPoster is running"

# === Основной цикл рассылки ===
async def auto_post():
    async with TelegramClient(SESSION_NAME, API_ID, API_HASH) as client:
        while True:
            success = []
            failed = []

            for chat_id in target_chats:
                try:
                    await client.send_message(chat_id, message_text)
                    success.append(str(chat_id))
                except Exception as e:
                    failed.append(f"{chat_id} — {str(e)}")

            report = "📢 <b>Отчёт по рассылке:</b>\n\n"
            report += "✅ Успешно:\n" + ("\n".join(success) if success else "—") + "\n\n"
            report += "❌ Ошибки:\n" + ("\n".join(failed) if failed else "—")

            try:
                await client.send_message(report_user_id, report, parse_mode='html')
            except Exception as e:
                print("Не удалось отправить отчёт:", e)

            await asyncio.sleep(interval_minutes * 60)

# === Запуск ===
if name == "main":
    loop = asyncio.get_event_loop()
    loop.create_task(auto_post())
    app.run(host="0.0.0.0", port=PORT)
