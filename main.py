import os
import sqlite3
import io
import time
import qrcode
from flask import Flask, request
from telebot import TeleBot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, Update, InputMediaPhoto

# ====== Конфигурация ======
PLAY = os.getenv("PLAY") or "YOUR_BOT_TOKEN_HERE"  # токен бота
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "4902536707"))
DB_PATH = os.getenv("DB_PATH", "data.db")

BOT_USERNAME = "anonysms_bot"
BOT_NAME = "Anony SMS"

# ====== Инициализация ======
bot = TeleBot(PLAY, parse_mode="HTML")
app = Flask(__name__)

# ====== Инициализация базы данных ======
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS anon_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender INTEGER,
        receiver INTEGER,
        content TEXT,
        type TEXT,
        timestamp INTEGER
    )
    """)
    conn.commit()
    conn.close()

# ====== Память ======
waiting_message = {}      # кто пишет кому
anonymous_reply = {}      # ответы анонимные
blocked_users = set()     # отключили приём
last_message_time = {}    # антиспам
ANTISPAM_INTERVAL = 60    # 1 сообщение / 60 секунд

# ====== Меню ======
main_menu = ReplyKeyboardMarkup(resize_keyboard=True)
main_menu.add(KeyboardButton("📩 Моя ссылка"), KeyboardButton("📱 QR-код"))
main_menu.add(KeyboardButton("✉️ Ответить анонимно"), KeyboardButton("⚙️ Настройки"))
main_menu.add(KeyboardButton("ℹ️ Помощь"))

settings_menu = ReplyKeyboardMarkup(resize_keyboard=True)
settings_menu.add(KeyboardButton("🔕 Отключить приём"), KeyboardButton("🔔 Включить приём"))
settings_menu.add(KeyboardButton("⬅️ Назад"))

cancel_menu = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_menu.add(KeyboardButton("❌ Отмена"))

# ====== /start ======
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    args = message.text.split()

    if len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])
        if target_id in blocked_users:
            bot.send_message(user_id, "🚫 Пользователь отключил приём сообщений.", reply_markup=main_menu)
            return

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.send_message(user_id, f"⏱ Подожди {ANTISPAM_INTERVAL} секунд между сообщениями.", reply_markup=main_menu)
            return

        waiting_message[user_id] = target_id
        last_message_time[user_id] = now
        bot.send_message(user_id, "🕶 Напиши сообщение — оно будет отправлено <b>анонимно</b>.", reply_markup=cancel_menu)
        return

    # Приветственное сообщение
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
        f"👋 Добро пожаловать в {BOT_NAME}!\n\n"
        f"🔗 Твоя персональная ссылка:\n{link}\n\n"
        "Меню для работы с анонимными сообщениями ниже:",
        reply_markup=main_menu)

# ====== Меню и обработка сообщений ======
@bot.message_handler(func=lambda m: True)
def handle_text(message):
    user_id = message.from_user.id
    text = message.text

    # Главное меню
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, f"🔗 Ваша персональная ссылка:\n{link}", reply_markup=main_menu)

    elif text == "📱 QR-код":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        bio.name = "qrcode.png"
        img.save(bio, "PNG")
        bio.seek(0)
        bot.send_photo(user_id, bio, caption="Вот твоя персональная ссылка в QR-коде")

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ Настройки анонимности:", reply_markup=settings_menu)

    elif text == "🔕 Отключить приём":
        blocked_users.add(user_id)
        bot.send_message(user_id, "🔕 Приём сообщений отключён.", reply_markup=main_menu)

    elif text == "🔔 Включить приём":
        blocked_users.discard(user_id)
        bot.send_message(user_id, "🔔 Приём сообщений включён.", reply_markup=main_menu)

    elif text == "⬅️ Назад":
        bot.send_message(user_id, "Главное меню:", reply_markup=main_menu)

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id,
            "ℹ️ Как пользоваться:\n"
            "1️⃣ Получи ссылку или QR-код\n"
            "2️⃣ Отправляй анонимно по ссылке\n"
            "3️⃣ Отвечай через меню\n"
            f"❗️Ограничение: 1 сообщение каждые {ANTISPAM_INTERVAL} секунд",
            reply_markup=main_menu)

    elif text == "✉️ Ответить анонимно":
        anonymous_reply[user_id] = None
        bot.send_message(user_id, "Введите ID пользователя для анонимного ответа:", reply_markup=cancel_menu)

    elif text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        anonymous_reply.pop(user_id, None)
        bot.send_message(user_id, "❌ Отправка отменена.", reply_markup=main_menu)

    else:
        # Анонимное сообщение через ссылку
        if user_id in waiting_message:
            target = waiting_message.pop(user_id)
            if target in blocked_users:
                bot.send_message(user_id, "🚫 Пользователь отключил приём сообщений.", reply_markup=main_menu)
                return

            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT INTO anon_messages (sender, receiver, content, type, timestamp) VALUES (?, ?, ?, ?, ?)",
                      (user_id, target, text, "text", int(time.time())))
            conn.commit()
            conn.close()

            bot.send_message(target, f"🕶 <b>Анонимное сообщение:</b>\n\n{text}")
            bot.send_message(user_id, "✅ Сообщение доставлено анонимно.", reply_markup=main_menu)
            return

        # Анонимный ответ через меню
        if user_id in anonymous_reply:
            if anonymous_reply[user_id] is None:
                if text.isdigit():
                    anonymous_reply[user_id] = int(text)
                    bot.send_message(user_id, "Теперь напиши сообщение анонимно:", reply_markup=cancel_menu)
                else:
                    bot.send_message(user_id, "Введите корректный ID.", reply_markup=cancel_menu)
            else:
                target = anonymous_reply.pop(user_id)
                bot.send_message(target, f"🕶 Анонимный ответ:\n\n{text}")
                bot.send_message(user_id, "✅ Анонимный ответ отправлен.", reply_markup=main_menu)

# ====== Webhook для Render ======
@app.route(f"/{PLAY}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK"

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

def setup_webhook():
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(f"{WEBHOOK_HOST}/{PLAY}")

# ====== Запуск ======
if __name__ == "__main__":
    init_db()
    setup_webhook()
    app.run(host="0.0.0.0", port=PORT)
