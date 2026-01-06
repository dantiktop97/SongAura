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
ADMIN_ID = 7549204023  # Твой ID
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
    c.execute("""
    CREATE TABLE IF NOT EXISTS blocked_users (
        user_id INTEGER PRIMARY KEY,
        blocked_at INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ====== Память ======
waiting_message = {}
admin_reply_mode = {}
blocked_users = set()
last_message_time = {}
ANTISPAM_INTERVAL = 30

def load_blocked():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM blocked_users")
    for row in c.fetchall():
        blocked_users.add(row[0])
    conn.close()

load_blocked()

# ====== Клавиатуры ======
def get_main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📩 Моя ссылка"), KeyboardButton("📱 QR-код"))
    markup.row(KeyboardButton("✉️ Ответить анонимно"), KeyboardButton("⚙️ Настройки"))
    markup.row(KeyboardButton("📌 Профиль"))
    markup.row(KeyboardButton("📩 Поддержка"), KeyboardButton("ℹ️ Помощь"))
    if is_admin:
        markup.add(KeyboardButton("🔧 Админ-панель"))
    return markup

settings_menu = ReplyKeyboardMarkup(resize_keyboard=True)
settings_menu.row(KeyboardButton("🔕 Отключить приём"), KeyboardButton("🔔 Включить приём"))
settings_menu.add(KeyboardButton("⬅️ Назад в меню"))

cancel_menu = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_menu.add(KeyboardButton("❌ Отмена"))

admin_menu = ReplyKeyboardMarkup(resize_keyboard=True)
admin_menu.row(KeyboardButton("📊 Статистика бота"), KeyboardButton("📨 Рассылка"))
admin_menu.row(KeyboardButton("🔥 Топ-10 пользователей"), KeyboardButton("🔍 Проверка пользователя"))
admin_menu.row(KeyboardButton("🚫 Заблокировать"), KeyboardButton("✅ Разблокировать"))
admin_menu.add(KeyboardButton("⬅️ Назад в главное меню"))

# ====== Утилиты ======
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

def get_user_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, first_name, link_clicks, messages_received, messages_sent, last_active FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        username = f"@{row[0]}" if row[0] else "<i>скрыт 😶</i>"
        name = row[1] or "Аноним 🕶️"
        clicks = row[2] or 0
        received = row[3] or 0
        sent = row[4] or 0
        last = time.strftime("%d.%m.%Y в %H:%M", time.localtime(row[5])) if row[5] else "давно не был(а) онлайн ⏳"
        return name, username, clicks, received, sent, last
    return "Аноним 🕶️", "<i>скрыт 😶</i>", 0, 0, 0, "неизвестно"

def is_blocked(user_id):
    return user_id in blocked_users

# ====== ТОП-10 ТОЛЬКО ДЛЯ АДМИНА ======
def show_top10_admin(chat_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT user_id, messages_received, link_clicks 
                 FROM users 
                 ORDER BY messages_received DESC, link_clicks DESC 
                 LIMIT 10""")
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(chat_id, "🔥 <b>ТОП-10 ПОКА ПУСТОЙ</b>\n\nПользователей ещё мало или активности недостаточно.")
        return

    text = "🏆 <b>ТОП-10 ПОЛЬЗОВАТЕЛЕЙ (АДМИН-ПАНЕЛЬ)</b>\n\n"
    for i, (uid, msgs, clicks) in enumerate(rows, 1):
        name, _, _, _, _, _ = get_user_info(uid)
        medal = ["🥇 1-е место", "🥈 2-е место", "🥉 3-е место"][i-1] if i <= 3 else f"{i}-е место"
        text += f"<b>{medal}</b>\n<b>{name}</b>\n💌 Анонимок: <code>{msgs}</code>\n👀 Кликов: <code>{clicks}</code>\n\n"
    bot.send_message(chat_id, text, reply_markup=admin_menu)

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        bot.send_message(user_id, 
            "🚫 <b>ДОСТУП К БОТУ ОГРАНИЧЕН</b> 🔒\n\n"
            "К сожалению, ваш аккаунт временно заблокирован.\n"
            "Если это ошибка — напиши в поддержку, мы разберёмся! ❤️")
        return

    update_user(message.from_user)
    is_admin = (user_id == ADMIN_ID)

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.send_message(user_id, 
                "⏳ <b>ПОДОЖДИ НЕМНОГО!</b> 😊\n\n"
                f"Можно отправлять сообщение раз в <code>{ANTISPAM_INTERVAL}</code> секунд.")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now
        bot.send_message(user_id, 
            "🕶️ <b>ГОТОВ(А) ОТПРАВИТЬ АНОНИМНОЕ СООБЩЕНИЕ?</b> 🔥\n\n"
            "Пиши текст, фото, видео, голосовое — всё уйдёт анонимно!",
            reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
                     f"🎉 <b>ДОБРО ПОЖАЛОВАТЬ В ANONY SMS!</b> 🎉\n\n"
                     f"🌟 Здесь ты можешь получать и отправлять сообщения <b>полностью анонимно</b>!\n\n"
                     f"🔗 <b>ТВОЯ ЛИЧНАЯ ССЫЛКА:</b>\n"
                     f"<code>{link}</code>\n\n"
                     f"📢 Распространи её среди друзей — и получай анонимные сообщения!\n"
                     f"💬 Под каждым сообщением можно ответить анонимно одним нажатием.\n\n"
                     f"Всё просто, безопасно и захватывающе! 🚀✨❤️",
                     reply_markup=get_main_menu(is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_all(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        bot.send_message(user_id, "🚫 <b>ДОСТУП ОГРАНИЧЕН</b> 🔒")
        return

    is_admin = (user_id == ADMIN_ID)
    text = message.text or message.caption or ""

    update_user(message.from_user)

    # Отмена
    if text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        if user_id == ADMIN_ID and ADMIN_ID in admin_reply_mode:
            admin_reply_mode.pop(ADMIN_ID)
            bot.send_message(user_id, "❌ <b>ДЕЙСТВИЕ ОТМЕНЕНО</b>\nРежим ответа завершён.", reply_markup=admin_menu)
        else:
            bot.send_message(user_id, "❌ <b>ДЕЙСТВИЕ ОТМЕНЕНО</b>", reply_markup=get_main_menu(is_admin))
        return

    # Поддержка: вход
    if text == "📩 Поддержка":
        bot.send_message(user_id,
                         "📩 <b>СЛУЖБА ПОДДЕРЖКИ ANONY SMS</b> 👨‍💻✨\n\n"
                         "Мы всегда на связи и готовы помочь! ❤️\n\n"
                         "Напиши вопрос, пришли скриншот, видео или голосовое.\n\n"
                         "Ждём твоё сообщение! 🚀",
                         reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    # Поддержка: отправка сообщения админу
    if waiting_message.get(user_id) == "support":
        name, username, _, _, _, last = get_user_info(user_id)

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton("✉️ Ответить", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data=f"sup_ignore_{user_id}")
        )

        info_text = (
            f"📩 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ</b>\n\n"
            f"👤 <b>Имя:</b> {name}\n"
            f"🌀 <b>Username:</b> {username}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"⏰ <b>Активность:</b> {last}\n"
            f"🕐 <b>Время:</b> {time.strftime('%d.%m.%Y в %H:%M')}"
        )

        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, info_text, reply_to_message_id=forwarded.message_id, reply_markup=kb)

        bot.send_message(user_id,
                         "✅ <b>ОБРАЩЕНИЕ ОТПРАВЛЕНО!</b> 🎉\n\n"
                         "Мы получили твоё сообщение и скоро ответим.\n"
                         "Спасибо, что ты с нами! ❤️",
                         reply_markup=get_main_menu(is_admin))

        waiting_message.pop(user_id, None)
        return

    # Админ: ответ в поддержку
    if user_id == ADMIN_ID and ADMIN_ID in admin_reply_mode:
        target_id = admin_reply_mode.pop(ADMIN_ID)

        try:
            if message.content_type == 'text':
                sent = bot.send_message(target_id, message.text)
            else:
                sent = bot.copy_message(target_id, ADMIN_ID, message.message_id)

            bot.send_message(target_id,
                             "✉️ <b>Вам ответил оператор поддержки Anony SMS</b> 👨‍💻✨\n\n"
                             "Если это не относится к вашему вопросу — просто проигнорируйте.\n"
                             "По всем вопросам пишите в «📩 Поддержка» — мы на связи! ❤️🚀",
                             reply_to_message_id=sent.message_id)

            bot.send_message(ADMIN_ID, "✅ <b>ОТВЕТ ОТПРАВЛЕН!</b>\nПользователь получил сообщение.", reply_markup=admin_menu)
        except:
            bot.send_message(ADMIN_ID, "❌ <b>ОШИБКА</b>\nПользователь заблокировал бота.", reply_markup=admin_menu)
        return

    # Админ-панель: топ-10
    if is_admin and text == "🔥 Топ-10 пользователей":
        show_top10_admin(user_id)
        return

    # Основные команды
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, 
            "🔗 <b>ТВОЯ ЛИЧНАЯ АНОНИМНАЯ ССЫЛКА</b>\n\n"
            f"<code>{link}</code>\n\n"
            "Распространяй её — и получай анонимные сообщения!",
            reply_markup=get_main_menu(is_admin))

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
        bot.send_photo(user_id, bio, 
                       caption="📱 <b>ТВОЙ QR-КОД</b>\n\nСканируй и переходи к анонимному общению!\n\n"
                               f"<i>Ссылка: {link}</i>",
                       reply_markup=get_main_menu(is_admin))

    elif text == "📌 Профиль":
        name, username, clicks, received, sent, last = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
                         f"📌 <b>ТВОЙ ПРОФИЛЬ</b>\n\n"
                         f"📛 Имя: {name}\n"
                         f"🌀 Username: {username}\n"
                         f"🆔 ID: <code>{user_id}</code>\n"
                         f"⏰ Активность: {last}\n\n"
                         f"📊 Статистика:\n"
                         f"💌 Получено сообщений: <code>{received}</code>\n"
                         f"📤 Отправлено: <code>{sent}</code>\n"
                         f"👀 Переходов по ссылке: <code>{clicks}</code>\n\n"
                         f"🔗 Ссылка: {link}",
                         reply_markup=get_main_menu(is_admin))

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ <b>НАСТРОЙКИ</b>\n\nВыберите действие:", reply_markup=settings_menu)

    elif text in ["🔕 Отключить приём", "🔔 Включить приём"]:
        status = "отключён" if "Отключить" in text else "включён"
        bot.send_message(user_id, f"Приём анонимных сообщений {status}!", reply_markup=get_main_menu(is_admin))

    elif text == "⬅️ Назад в меню":
        bot.send_message(user_id, "🏠 Главное меню", reply_markup=get_main_menu(is_admin))

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id,
                         "ℹ️ <b>КАК РАБОТАЕТ ANONY SMS?</b>\n\n"
                         "1. Получи свою ссылку или QR-код\n"
                         "2. Распространи её\n"
                         "3. Получай анонимные сообщения\n"
                         "4. Отвечай анонимно одним нажатием\n\n"
                         "Всё просто и полностью анонимно! ❤️",
                         reply_markup=get_main_menu(is_admin))

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id, "🔍 Введи <b>ID пользователя</b> для ручного ответа:", reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"
        return

    # Анонимная отправка по ссылке
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO anon_messages (sender, receiver, content, type, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (user_id, target_id, text, message.content_type, int(time.time())))
        conn.commit()
        conn.close()

        increment_stat(target_id, "messages_received")
        increment_stat(user_id, "messages_sent")

        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Ответить анонимно", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data="ignore")
        )

        try:
            if message.content_type == 'text':
                bot.send_message(target_id, f"🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ!</b>\n\n{text}", reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id)
                bot.send_message(target_id, "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ!</b>", reply_to_message_id=copied.message_id, reply_markup=markup)
        except:
            bot.send_message(user_id, "❌ Не удалось доставить")

        bot.send_message(user_id, "✅ <b>СООБЩЕНИЕ ОТПРАВЛЕНО АНОНИМНО!</b>", reply_markup=get_main_menu(is_admin))
        return

# ====== Callbacks ======
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    if is_blocked(user_id):
        return

    data = call.data

    if data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        return

    if data.startswith("reply_"):
        sender_id = int(data.split("_")[1])
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "🕶️ <b>НАПИШИ АНОНИМНЫЙ ОТВЕТ</b>", reply_markup=cancel_menu)
        return

    if data.startswith("sup_reply_") and user_id == ADMIN_ID:
        target_id = int(data.split("_")[-1])
        admin_reply_mode[ADMIN_ID] = target_id
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        name, _, _, _, _, _ = get_user_info(target_id)
        bot.send_message(ADMIN_ID,
                         f"✉️ <b>ОТВЕТ ПОЛЬЗОВАТЕЛЮ</b>\n"
                         f"👤 {name}\n"
                         f"🆔 <code>{target_id}</code>\n\n"
                         "Отправь сообщение — оно уйдёт от имени бота.",
                         reply_markup=cancel_menu)
        return

    if data.startswith("sup_ignore_") and user_id == ADMIN_ID:
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Проигнорировано")
        return

# ====== Webhook ======
@app.route(f"/{PLAY}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_data().decode("utf-8"))
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
