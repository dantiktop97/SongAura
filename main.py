import os
from telethon import TelegramClient, events, functions, types
from telethon.tl.custom import Button

# ==== Переменные окружения ====
api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")
session_path = "sessions/me.session"  # путь к твоей сессии

client = TelegramClient(session_path, api_id, api_hash)

# ==== Словарь для хранения выбранных чатов ====
selected_chats = {}

# ==== Команда /start ====
@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_name = event.sender.first_name or "друг"
    buttons = [
        [Button.inline("📋 Показать мои чаты", b"show_chats")],
        [Button.inline("✉️ Отправить сообщение", b"send_message")]
    ]
    await event.respond(f"👋 Привет, {user_name}!\nВыбери действие:", buttons=buttons)

# ==== Обработчик кнопок ====
@client.on(events.CallbackQuery)
async def callback_handler(event):
    global selected_chats

    if event.data == b"show_chats":
        # Получаем список чатов
        dialogs = await client.get_dialogs()
        buttons = []
        for d in dialogs:
            if d.is_group or d.is_channel:
                # отмечаем выбранные чаты
                mark = "✅" if selected_chats.get(d.id) else "❌"
                buttons.append([Button.inline(f"{mark} {d.name}", f"toggle_{d.id}")])
        buttons.append([Button.inline("⬅️ Назад", b"back")])
        await event.edit("Выбери чаты для рассылки:", buttons=buttons)

    elif event.data.startswith(b"toggle_"):
        chat_id = int(event.data.decode().split("_")[1])
        selected_chats[chat_id] = not selected_chats.get(chat_id, False)
        await callback_handler(event)  # обновляем список кнопок

    elif event.data == b"send_message":
        await event.respond("Отправь мне сообщение, я разошлю его в выбранные чаты.")

    elif event.data == b"back":
        buttons = [
            [Button.inline("📋 Показать мои чаты", b"show_chats")],
            [Button.inline("✉️ Отправить сообщение", b"send_message")]
        ]
        await event.edit("Главное меню:", buttons=buttons)

# ==== Обработка текста для рассылки ====
@client.on(events.NewMessage)
async def message_handler(event):
    if event.text and selected_chats:
        text = event.text
        count = 0
        for chat_id, send in selected_chats.items():
            if send:
                try:
                    await client.send_message(chat_id, text)
                    count += 1
                except:
                    pass
        if count > 0:
            await event.respond(f"✅ Сообщение отправлено в {count} чат(ов).")
        else:
            await event.respond("⚠️ Не выбрано ни одного чата для рассылки.")
    else:
        pass  # обычные сообщения без рассылки игнорируем

# ==== Запуск бота ====
print("Бот запущен!")
client.start()
client.run_until_disconnected()
