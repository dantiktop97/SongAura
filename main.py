import asyncio
import json
from telethon import TelegramClient, events
import os

# Подключение через сессию (userbot)
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session_file = "sessions/me.session"  # твоя сессия в GitHub

client = TelegramClient(session_file, api_id, api_hash)

# Файл для хранения списка групп
GROUPS_FILE = "groups.json"

# Загружаем список групп
if os.path.exists(GROUPS_FILE):
    with open(GROUPS_FILE, "r", encoding="utf-8") as f:
        GROUPS = json.load(f)
else:
    GROUPS = [
        -1001300573578,
        -1001966255283,
        -1002423716563,
        -1002633910583,
        -1002489693744,
        -1002942057666
    ]
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(GROUPS, f, ensure_ascii=False, indent=2)

# Текст для авто-рассылки
MESSAGE = "⭐🎮💸 Привет! Нашёл бот, где можно зарабатывать звёзды за друзей и выводить на баланс или деньги! Много игр и заданий!\n👉 https://t.me/STARS_SNOW_bot?start=6525179440"

async def auto_broadcast():
    while True:
        for group_id in GROUPS:
            try:
                await client.send_message(group_id, MESSAGE)
                print(f"✅ Сообщение отправлено в группу {group_id}")
            except Exception as e:
                print(f"❌ Ошибка при отправке в группу {group_id}: {e}")
        await asyncio.sleep(300)  # пауза 5 минут

# Команда для добавления новой группы
@client.on(events.NewMessage(pattern=r"/addgroup (\-?\d+)"))
async def add_group(event):
    sender = await event.get_sender()
    if sender.id != client.get_me().id:
        return  # Только владелец бота может добавлять группы

    new_group = int(event.pattern_match.group(1))
    if new_group not in GROUPS:
        GROUPS.append(new_group)
        with open(GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(GROUPS, f, ensure_ascii=False, indent=2)
        await event.reply(f"✅ Группа {new_group} добавлена в список рассылки.")
    else:
        await event.reply("⚠️ Эта группа уже есть в списке.")

async def main():
    await client.start()
    print("Бот запущен! Авто-рассылка каждые 5 минут.")
    asyncio.create_task(auto_broadcast())
    # Клиент остаётся на прослушивании команд
    await client.run_until_disconnected()

if __name__ == "__main__":
    client.loop.run_until_complete(main())
