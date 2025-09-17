import os
from telethon import TelegramClient, events, Button
from keep_alive import keep_alive

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session_path = "sessions/me.session"

if not os.path.exists("sessions"):
    os.mkdir("sessions")

client = TelegramClient(session_path, api_id, api_hash)

selected_chat = None

# Приветствие с инлайн кнопками
@client.on(events.NewMessage(pattern="/start"))
async def start(event):
    name = event.sender.first_name or "друг"
    buttons = [
        [Button.inline("💬 Выбрать чат", b"set_chat")],
        [Button.inline("✉️ Отправить сообщение", b"send_msg")],
        [Button.inline("ℹ️ Помощь", b"help")]
    ]
    await event.reply(f"👋 Привет, {name}!\nВыбери действие:", buttons=buttons)

# Обработка нажатий кнопок
@client.on(events.CallbackQuery)
async def callback(event):
    global selected_chat
    data = event.data.decode("utf-8")

    if data == "set_chat":
        await event.edit("✏️ Введи команду:\n/set <chat_id или @username>")
    elif data == "send_msg":
        if not selected_chat:
            await event.edit("⚠️ Сначала выбери чат через /set")
        else:
            await event.edit("✏️ Введи команду:\n/send <текст>")
    elif data == "help":
        await event.edit("📌 Команды:\n/set <chat_id или @username>\n/send <текст>\n/help")

# Основной функционал
@client.on(events.NewMessage)
async def handler(event):
    global selected_chat
    text = event.raw_text.strip()

    if text.startswith("/set "):
        selected_chat = text.split(" ", 1)[1].strip()
        await event.reply(f"✅ Чат {selected_chat} выбран!")
    elif text.startswith("/send "):
        if not selected_chat:
            await event.reply("⚠️ Сначала выбери чат через /set")
            return
        message = text.split(" ", 1)[1].strip()
        try:
            await client.send_message(selected_chat, message)
            await event.reply(f"✅ Сообщение отправлено в {selected_chat}")
        except Exception as e:
            await event.reply(f"⚠️ Ошибка: {e}")
    elif text == "/help":
        await event.reply("📌 Команды:\n/set <chat_id или @username>\n/send <текст>\n/help")

if __name__ == "__main__":
    keep_alive()
    client.start()
    client.run_until_disconnected()
