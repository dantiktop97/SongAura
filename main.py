import os
import json
import asyncio
from flask import Flask, request
from telebot import TeleBot, types
from telethon import TelegramClient

# ========== Настройки ==========
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION_PATH = "/etc/secrets/user_session.session"  # Render secret file
DATA_FILE = "data.json"

# ========== Инициализация ==========
app = Flask(__name__)
bot = TeleBot(BOT_TOKEN)
client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

# ========== Работа с JSON ==========
def load_data():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({"chats": [], "broadcast_text": ""}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ========== Меню ==========
def main_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Добавить чат", callback_data="add_chat"))
    kb.add(types.InlineKeyboardButton("Удалить чат", callback_data="remove_chat"))
    kb.add(types.InlineKeyboardButton("Список чатов", callback_data="list_chats"))
    kb.add(types.InlineKeyboardButton("Изменить текст", callback_data="edit_text"))
    kb.add(types.InlineKeyboardButton("Запустить рассылку", callback_data="broadcast"))
    return kb

# ========== Обработка команды меню ==========
@bot.message_handler(commands=["menu"])
def menu(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    bot.send_message(msg.chat.id, "Выберите действие:", reply_markup=main_menu())

# ========== Callback ==========
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(call.id, "🚫 Нет доступа")
    data = call.data
    json_data = load_data()

    if data == "add_chat":
        bot.send_message(call.message.chat.id, "Отправьте ID чата для добавления:")
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, add_chat)
    elif data == "remove_chat":
        bot.send_message(call.message.chat.id, "Отправьте ID чата для удаления:")
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, remove_chat)
    elif data == "list_chats":
        text = "\n".join(str(c) for c in json_data["chats"]) or "Список пуст."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu())
    elif data == "edit_text":
        bot.send_message(call.message.chat.id, "Отправьте новый текст рассылки:")
        bot.register_next_step_handler_by_chat_id(call.message.chat.id, edit_text)
    elif data == "broadcast":
        bot.send_message(call.message.chat.id, "✅ Рассылка запущена!")
        asyncio.run(send_broadcast(json_data))

# ========== Шаги меню ==========
def add_chat(msg):
    try:
        chat_id = int(msg.text)
        data = load_data()
        if chat_id not in data["chats"]:
            data["chats"].append(chat_id)
        save_data(data)
        bot.send_message(msg.chat.id, f"✅ Чат {chat_id} добавлен", reply_markup=main_menu())
    except:
        bot.send_message(msg.chat.id, "❌ Неверный ID", reply_markup=main_menu())

def remove_chat(msg):
    try:
        chat_id = int(msg.text)
        data = load_data()
        if chat_id in data["chats"]:
            data["chats"].remove(chat_id)
        save_data(data)
        bot.send_message(msg.chat.id, f"✅ Чат {chat_id} удален", reply_markup=main_menu())
    except:
        bot.send_message(msg.chat.id, "❌ Неверный ID", reply_markup=main_menu())

def edit_text(msg):
    data = load_data()
    data["broadcast_text"] = msg.text
    save_data(data)
    bot.send_message(msg.chat.id, "✅ Текст обновлен", reply_markup=main_menu())

# ========== Рассылка ==========
async def send_broadcast(data):
    await client.start()
    chats = data.get("chats", [])
    text = data.get("broadcast_text", "")
    for chat_id in chats:
        try:
            await client.send_message(chat_id, text)
        except Exception as e:
            print(f"Ошибка при отправке в {chat_id}: {e}")
    print("✅ Рассылка завершена")

# ========== Webhook Flask ==========
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = bot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

@app.route("/", methods=["GET"])
def index():
    return "ok", 200

# ========== Запуск ==========
if __name__ == "__main__":
    WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
    WEBHOOK_PORT = int(os.getenv("PORT", "8000"))
    bot.remove_webhook()
    if WEBHOOK_HOST:
        bot.set_webhook(url=f"{WEBHOOK_HOST.rstrip('/')}/{BOT_TOKEN}")
    app.run(host="0.0.0.0", port=WEBHOOK_PORT)
