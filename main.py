import os
import asyncio
from telethon import TelegramClient

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session_name = 'me_userbot'

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

interval_minutes = 15

my_user_id = 7902738665  # Твой Telegram ID для отчёта

async def send_messages(client):
    success = []
    failed = []

    for target in targets:
        try:
            await client.send_message(target, message_text)
            print(f"✅ Отправлено в {target}")
            success.append(str(target))
        except Exception as e:
            print(f"❌ Ошибка при отправке в {target}: {e}")
            failed.append(str(target))

    report = "📢 Отчёт по рассылке:\n\n"
    report += "✅ Успешно отправлено в:\n" + ("\n".join(success) if success else "нет") + "\n\n"
    report += "❌ Не удалось отправить в:\n" + ("\n".join(failed) if failed else "нет") + "\n"

    await client.send_message(my_user_id, report)
    print("📩 Отчёт отправлен тебе в Telegram")

async def main():
    async with TelegramClient(session_name, api_id, api_hash) as client:
        while True:
            await send_messages(client)
            await asyncio.sleep(interval_minutes * 60)

if name == "main":
    asyncio.run(main())
