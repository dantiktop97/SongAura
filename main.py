import os
import sqlite3
import io
import time
import qrcode
from flask import Flask, request
from telebot import TeleBot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton, Update,
    InlineKeyboardMarkup, InlineKeyboardButton
)

# ====== Конфигурация ======
PLAY = os.getenv("PLAY") or "YOUR_BOT_TOKEN_HERE"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))  # Твой ID
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "-1004902536707"))  # Канал для логов (с -100)
DB_PATH = os.getenv("DB_PATH", "data.db")

BOT_USERNAME = "anonysms_bot"
BOT_NAME = "Anony SMS"

# ====== Инициализация ======
bot = TeleBot(PLAY, parse_mode="HTML")
app = Flask(__name__)

# ====== База данных ======
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
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        link_clicks INTEGER DEFAULT 0,
        messages_received INTEGER DEFAULT 0,
        messages_sent INTEGER DEFAULT 0,
        last_active INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ====== Память и настройки ======
waiting_message = {}        # {user_id: target_id} — ожидает сообщение
blocked_users = set()       # отключён приём
last_message_time = {}      # антиспам
ANTISPAM_INTERVAL = 30      # 30 секунд между сообщениями

# ====== Клавиатуры ======
def get_main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton("📩 Моя ссылка"), KeyboardButton("📱 QR-код"))
    markup.add(KeyboardButton("✉️ Ответить анонимно"), KeyboardButton("⚙️ Настройки"))
    markup.add(KeyboardButton("📌 Профиль"), KeyboardButton("ℹ️ Помощь"))
    return markup

settings_menu = ReplyKeyboardMarkup(resize_keyboard=True)
settings_menu.add(KeyboardButton("🔕 Отключить приём"), KeyboardButton("🔔 Включить приём"))
settings_menu.add(KeyboardButton("⬅️ Назад"))

cancel_menu = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_menu.add(KeyboardButton("❌ Отмена"))

admin_menu = ReplyKeyboardMarkup(resize_keyboard=True)
admin_menu.add(KeyboardButton("📊 Статистика бота"), KeyboardButton("📨 Рассылка"))
admin_menu.add(KeyboardButton("⬅️ Назад в главное"))

# ====== Утилиты ======
def log_message(sender_id, receiver_id, content_type, text=""):
    try:
        msg = f"📩 Новое анонимное сообщение\n\n" \
              f"От: <a href='tg://user?id={sender_id}'>{sender_id}</a>\n" \
              f"Кому: <a href='tg://user?id={receiver_id}'>{receiver_id}</a>\n" \
              f"Тип: {content_type}"
        if text:
            msg += f"\nТекст: {text[:500]}"
        bot.send_message(LOG_CHANNEL, msg, disable_web_page_preview=True)
    except:
        pass

def update_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO users 
                 (user_id, username, first_name, last_active) 
                 VALUES (?, ?, ?, ?)""",
              (user.id, user.username or "", user.first_name or "", int(time.time())))
    conn.commit()
    conn.close()

def increment_stat(user_id, field):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(f"UPDATE users SET {field} = {field} + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user = message.from_user
    update_user(user)
    
    args = message.text.split()
    user_id = user.id

    # Если переход по ссылке — увеличиваем счётчик
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        if sender_id in blocked_users:
            bot.send_message(user_id, "🚫 Пользователь отключил приём сообщений.", reply_markup=get_main_menu())
            return

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.send_message(user_id, f"⏱ Подожди {ANTISPAM_INTERVAL} секунд между сообщениями.", reply_markup=get_main_menu())
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now
        bot.send_message(user_id, "🕶 Отправь сообщение (текст, фото, видео, стикер и т.д.) — оно уйдёт анонимно.", reply_markup=cancel_menu)
        return

    # Обычный старт
    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
        f"👋 Добро пожаловать в <b>{BOT_NAME}</b>!\n\n"
        f"🔗 Твоя анонимная ссылка:\n{link}\n\n"
        "Распространяй её — получай анонимные сообщения!",
        reply_markup=get_main_menu())

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice'])
def handle_media(message):
    user_id = message.from_user.id
    text = message.text or message.caption or ""

    # Админские команды
    if user_id == ADMIN_ID:
        if text == "📊 Статистика бота":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM anon_messages")
            total_msgs = c.fetchone()[0]
            conn.close()
            bot.send_message(user_id, f"📊 <b>Статистика бота</b>\n\n"
                                     f"👥 Пользователей: {total_users}\n"
                                     f"💬 Всего сообщений: {total_msgs}", reply_markup=admin_menu)
            return
        if text == "📨 Рассылка":
            bot.send_message(user_id, "Отправь сообщение для рассылки всем пользователям (текст, фото, видео и т.д.).", reply_markup=cancel_menu)
            waiting_message[user_id] = "broadcast"
            return
        if text == "⬅️ Назад в главное":
            bot.send_message(user_id, "Главное меню:", reply_markup=get_main_menu())
            return

    # Кнопки главного меню
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, f"🔗 Твоя ссылка:\n{link}", reply_markup=get_main_menu())

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
        bot.send_photo(user_id, bio, caption="Твоя ссылка в QR-коде 📱", reply_markup=get_main_menu())

    elif text == "📌 Профиль":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT username, first_name, link_clicks, messages_received FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()

        username = row[0] or "отсутствует"
        first_name = row[1] or "Неизвестно"
        clicks = row[2] or 0
        msgs = row[3] or 0

        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
            f"📌 <b>Твой профиль</b>\n\n"
            f"👤 Имя: {first_name}\n"
            f"🌀 Username: @{username}\n"
            f"🆔 ID: <code>{user_id}</code>\n\n"
            f"📊 <b>Статистика</b>\n"
            f"➖ За всё время:\n"
            f"💬 Получено сообщений: {msgs}\n"
            f"👀 Переходов по ссылке: {clicks}\n\n"
            f"🔝 Чтобы попасть в топ — распространяй ссылку:\n{link}",
            reply_markup=get_main_menu())

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ Настройки:", reply_markup=settings_menu)

    elif text == "🔕 Отключить приём":
        blocked_users.add(user_id)
        bot.send_message(user_id, "🔕 Приём анонимных сообщений отключён.", reply_markup=get_main_menu())

    elif text == "🔔 Включить приём":
        blocked_users.discard(user_id)
        bot.send_message(user_id, "🔔 Приём анонимных сообщений включён.", reply_markup=get_main_menu())

    elif text == "⬅️ Назад":
        bot.send_message(user_id, "Главное меню:", reply_markup=get_main_menu())

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id,
            "ℹ️ <b>Как пользоваться</b>\n\n"
            "1️⃣ Получи свою ссылку или QR-код\n"
            "2️⃣ Распространяй — люди будут писать тебе анонимно\n"
            "3️⃣ Под каждым сообщением — кнопка «Ответить»\n"
            f"⏱ Лимит: 1 сообщение каждые {ANTISPAM_INTERVAL} секунд",
            reply_markup=get_main_menu())

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id, "Введи ID пользователя для анонимного ответа:", reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"

    elif text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        bot.send_message(user_id, "❌ Отправка отменена.", reply_markup=get_main_menu())

    # Рассылка от админа
    elif user_id == ADMIN_ID and waiting_message.get(user_id) == "broadcast":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [row[0] for row in c.fetchall()]
        conn.close()

        sent = 0
        failed = 0
        for uid in users:
            try:
                bot.copy_message(uid, user_id, message.message_id)
                sent += 1
            except:
                failed += 1
            time.sleep(0.05)  # антифлуд

        bot.send_message(user_id, f"📨 Рассылка завершена!\nУспешно: {sent}\nОшибок: {failed}", reply_markup=admin_menu)
        waiting_message.pop(user_id, None)
        return

    # Ручной анонимный ответ
    elif waiting_message.get(user_id) == "manual_reply":
        if text.isdigit():
            target = int(text)
            waiting_message[user_id] = target
            bot.send_message(user_id, "Теперь отправь сообщение анонимно:", reply_markup=cancel_menu)
        else:
            bot.send_message(user_id, "❌ Введи корректный ID пользователя.", reply_markup=cancel_menu)

    # Ожидание анонимного сообщения (по ссылке или ответу)
    elif user_id in waiting_message:
        target_id = waiting_message.pop(user_id)

        if target_id in blocked_users and target_id != "broadcast":
            bot.send_message(user_id, "🚫 Этот пользователь отключил приём сообщений.", reply_markup=get_main_menu())
            return

        # Определяем тип контента
        content_type = message.content_type
        if content_type == 'text':
            content = text
        else:
            content = ""

        # Сохраняем в БД
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO anon_messages (sender, receiver, content, type, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (user_id, target_id, content, content_type, int(time.time())))
        conn.commit()
        conn.close()

        # Увеличиваем статистику полученных сообщений
        increment_stat(target_id, "messages_received")

        # Логируем
        log_message(user_id, target_id, content_type, text)

        # Инлайн-кнопки для получателя
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✉️ Ответить анонимно", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data="ignore")
        )

        # Отправляем анонимно
        try:
            if content_type == 'text':
                sent_msg = bot.send_message(target_id, f"🕶 <b>Анонимное сообщение:</b>\n\n{text}", reply_markup=markup)
            elif content_type in ['photo', 'video', 'audio', 'document', 'voice', 'sticker']:
                sent_msg = bot.copy_message(target_id, user_id, message.message_id, reply_markup=markup)
                bot.send_message(target_id, "🕶 <b>Анонимное сообщение:</b>", reply_to_message_id=sent_msg.message_id)
            else:
                bot.send_message(target_id, "🕶 <b>Анонимное сообщение:</b>", reply_markup=markup)
                bot.copy_message(target_id, user_id, message.message_id)
        except:
            bot.send_message(user_id, "❌ Не удалось доставить — пользователь заблокировал бота или отключил приём.")
            return

        bot.send_message(user_id, "✅ Сообщение отправлено анонимно!", reply_markup=get_main_menu())

# ====== Callback от инлайн-кнопок ======
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data

    if data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Проигнорировано")

    elif data.startswith("reply_"):
        sender_id = int(data.split("_")[1])

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.answer_callback_query(call.id, f"⏱ Подожди {ANTISPAM_INTERVAL} сек")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now

        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "🕶 Напиши ответ (текст, фото, видео и т.д.) — он уйдёт анонимно.", reply_markup=cancel_menu)
        bot.answer_callback_query(call.id, "Пиши ответ!")

# ====== Админ доступ ======
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and m.text == "/admin")
def admin_panel(message):
    bot.send_message(ADMIN_ID, "🔧 Админ-панель", reply_markup=admin_menu)

# ====== Webhook ======
@app.route(f"/{PLAY}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

def setup_webhook():
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(f"{WEBHOOK_HOST}/{PLAY}")

if __name__ == "__main__":
    setup_webhook()
    app.run(host="0.0.0.0", port=PORT)
