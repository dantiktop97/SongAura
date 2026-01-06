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
ADMIN_ID = 7549204023
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "-1004902536707"))  # опционально
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
        last_active INTEGER
    )
    """)
    c.execute("""
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        message_id INTEGER,
        chat_id INTEGER,
        timestamp INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

# ====== Память и настройки ======
waiting_message = {}        # {user_id: target_id или "support"/"manual_reply"/"admin_reply_XXXX"/"broadcast"}
blocked_users = set()
last_message_time = {}
ANTISPAM_INTERVAL = 30

# ====== Клавиатуры ======
def get_main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📩 Моя ссылка"), KeyboardButton("📱 QR-код"))
    markup.row(KeyboardButton("✉️ Ответить анонимно"), KeyboardButton("⚙️ Настройки"))
    markup.row(KeyboardButton("📌 Профиль"), KeyboardButton("📩 Поддержка"))
    markup.row(KeyboardButton("ℹ️ Помощь"))
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
admin_menu.row(KeyboardButton("🔥 Топ-10 пользователей"), KeyboardButton("📜 Последние 20 логов"))
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
    c.execute("SELECT username, first_name FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        username = f"@{row[0]}" if row[0] else "отсутствует"
        name = row[1] or "Неизвестно"
        return name, username
    return "Неизвестно", "отсутствует"

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user = message.from_user
    update_user(user)
    user_id = user.id
    is_admin = (user_id == ADMIN_ID)

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        if sender_id in blocked_users:
            bot.send_message(user_id, "🚫 <b>Этот пользователь отключил приём анонимных сообщений.</b>", reply_markup=get_main_menu(is_admin))
            return

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.send_message(user_id, f"⏱ <b>Подожди {ANTISPAM_INTERVAL} секунд</b> перед следующим сообщением!", reply_markup=get_main_menu(is_admin))
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now
        bot.send_message(user_id,
            "🕶 <b>Отправь любое сообщение</b> — текст, фото 📸, видео 🎥, стикер, голосовое и т.д.\n"
            "Оно придёт <b>полностью анонимно</b>! ✨",
            reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
        f"🎉 <b>Добро пожаловать в {BOT_NAME}!</b> 🎉\n\n"
        f"🔗 <b>Твоя личная анонимная ссылка:</b>\n<code>{link}</code>\n\n"
        f"📢 Распространяй её — получай <b>анонимные сообщения</b> от всех!\n"
        f"💬 Под каждым анонимным сообщением — кнопки <b>«Ответить»</b> и <b>«Игнор»</b> 🚀",
        reply_markup=get_main_menu(is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation'])
def handle_all(message):
    user_id = message.from_user.id
    is_admin = (user_id == ADMIN_ID)
    text = message.text or message.caption or ""

    # === Админ-панель ===
    if is_admin:
        if text == "🔧 Админ-панель":
            bot.send_message(user_id, "🔧 <b>Админ-панель открыта</b> 🔥", reply_markup=admin_menu)
            return

        if text == "📊 Статистика бота":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM anon_messages")
            total_msgs = c.fetchone()[0]
            conn.close()
            bot.send_message(user_id,
                f"📊 <b>Статистика бота</b> 📈\n\n"
                f"👥 <b>Всего пользователей:</b> <code>{total_users}</code>\n"
                f"💬 <b>Всего анонимных сообщений:</b> <code>{total_msgs}</code>",
                reply_markup=admin_menu)
            return

        if text == "📨 Рассылка":
            bot.send_message(user_id,
                "📨 <b>Рассылка всем пользователям</b>\n\n"
                "Отправь сообщение (текст, фото, видео...) — оно уйдёт всем!",
                reply_markup=cancel_menu)
            waiting_message[user_id] = "broadcast"
            return

        if text == "🔥 Топ-10 пользователей":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""SELECT user_id, messages_received, link_clicks 
                         FROM users 
                         ORDER BY messages_received DESC, link_clicks DESC 
                         LIMIT 10""")
            rows = c.fetchall()
            conn.close()

            if not rows:
                bot.send_message(user_id, "📊 <b>Топ-10 пока пуст</b> — нет данных!", reply_markup=admin_menu)
                return

            top_text = "🔥 <b>Топ-10 самых популярных профилей</b> 🏆\n\n"
            for i, (uid, msgs, clicks) in enumerate(rows, 1):
                name, username = get_user_info(uid)
                top_text += f"<b>{i}.</b> 👤 {name} ({username})\n"
                top_text += f"   🆔 <code>{uid}</code>\n"
                top_text += f"   💬 <b>Получено сообщений:</b> <code>{msgs}</code>\n"
                top_text += f"   👀 <b>Переходов по ссылке:</b> <code>{clicks}</code>\n\n"
            bot.send_message(user_id, top_text, reply_markup=admin_menu)
            return

        if text == "📜 Последние 20 логов":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""SELECT sender, receiver, type, content, timestamp 
                         FROM anon_messages 
                         ORDER BY timestamp DESC 
                         LIMIT 20""")
            logs = c.fetchall()
            conn.close()

            if not logs:
                bot.send_message(user_id, "📜 <b>Логов пока нет</b>", reply_markup=admin_menu)
                return

            log_text = "📜 <b>Последние 20 анонимных сообщений</b> ⏳\n\n"
            for sender, receiver, mtype, content, ts in reversed(logs):
                time_str = time.strftime("%d.%m.%Y %H:%M", time.localtime(ts))
                sender_name, sender_un = get_user_info(sender)
                receiver_name, receiver_un = get_user_info(receiver)
                log_text += f"<b>{time_str}</b>\n"
                log_text += f"👤 <b>От:</b> {sender_name} ({sender_un}) <code>{sender}</code>\n"
                log_text += f"👤 <b>Кому:</b> {receiver_name} ({receiver_un}) <code>{receiver}</code>\n"
                log_text += f"📥 <b>Тип:</b> <code>{mtype}</code>\n"
                if content:
                    log_text += f"💬 <b>Текст:</b> {content[:200]}\n"
                log_text += "➖➖➖\n\n"
            bot.send_message(user_id, log_text, reply_markup=admin_menu)
            return

        if text == "⬅️ Назад в главное меню":
            bot.send_message(user_id, "🏠 <b>Главное меню</b>", reply_markup=get_main_menu(True))
            return

    # === Главное меню ===
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
            f"🔗 <b>Твоя анонимная ссылка:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"📢 Распространяй — получай анонимки! 🚀",
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
            caption=f"📱 <b>Твой QR-код</b> ✨\n\n<i>Ссылка: {link}</i>",
            reply_markup=get_main_menu(is_admin))

    elif text == "📌 Профиль":
        name, username = get_user_info(user_id)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT link_clicks, messages_received FROM users WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()

        clicks = row[0] if row else 0
        msgs = row[1] if row else 0

        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
            f"📌 <b>Твой профиль</b> 👤\n\n"
            f"👤 <b>Имя:</b> {name}\n"
            f"🌀 <b>Username:</b> {username}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
            f"📊 <b>Статистика за всё время</b> 📈\n"
            f"💬 <b>Получено сообщений:</b> <code>{msgs}</code>\n"
            f"👀 <b>Переходов по ссылке:</b> <code>{clicks}</code>\n\n"
            f"🔝 <b>Распространяй ссылку — поднимайся в топ!</b>\n{link}",
            reply_markup=get_main_menu(is_admin))

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ <b>Настройки анонимности</b>", reply_markup=settings_menu)

    elif text == "🔕 Отключить приём":
        blocked_users.add(user_id)
        bot.send_message(user_id, "🔕 <b>Приём анонимных сообщений отключён</b> 🔒", reply_markup=get_main_menu(is_admin))

    elif text == "🔔 Включить приём":
        blocked_users.discard(user_id)
        bot.send_message(user_id, "🔔 <b>Приём анонимных сообщений включён</b> ✅", reply_markup=get_main_menu(is_admin))

    elif text == "⬅️ Назад в меню":
        bot.send_message(user_id, "🏠 <b>Главное меню</b>", reply_markup=get_main_menu(is_admin))

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id,
            "ℹ️ <b>Как пользоваться ботом</b> ❓\n\n"
            "1️⃣ Получи свою ссылку или QR-код\n"
            "2️⃣ Распространи её где угодно\n"
            "3️⃣ Получай анонимные сообщения с кнопками <b>«Ответить»</b> и <b>«Игнор»</b>\n"
            "4️⃣ Отвечай анонимно одним кликом!\n\n"
            f"⏱ <b>Лимит:</b> 1 сообщение каждые <code>{ANTISPAM_INTERVAL}</code> секунд\n"
            f"📩 Проблема или вопрос? — жми <b>Поддержка</b>!",
            reply_markup=get_main_menu(is_admin))

    elif text == "📩 Поддержка":
        bot.send_message(user_id,
            "📩 <b>Поддержка</b> 👨‍💻\n\n"
            "<b>Напиши свой вопрос</b>, опиши баг или пришли скриншот/видео.\n"
            "Мы ответим как можно скорее! 🚀\n\n"
            "<i>Поддерживаются текст, фото, видео, документы...</i>",
            reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return  # НЕ отправляем подтверждение сразу!

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id,
            "🔍 <b>Ручной анонимный ответ</b>\n\n"
            "Введи <b>ID пользователя</b>, которому хочешь написать:",
            reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"
        return

    elif text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        bot.send_message(user_id, "❌ <b>Отправка отменена</b>", reply_markup=get_main_menu(is_admin))
        return

    # === Рассылка ===
    if is_admin and waiting_message.get(user_id) == "broadcast":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        users = [row[0] for row in c.fetchall()]
        conn.close()

        sent = failed = 0
        for uid in users:
            try:
                bot.copy_message(uid, user_id, message.message_id)
                sent += 1
            except:
                failed += 1
            time.sleep(0.05)

        bot.send_message(user_id, f"📨 <b>Рассылка завершена!</b>\n✅ Успешно: <code>{sent}</code>\n❌ Ошибок: <code>{failed}</code>", reply_markup=admin_menu)
        waiting_message.pop(user_id, None)
        return

    # === Поддержка (отправка сообщения) ===
    if waiting_message.get(user_id) == "support" and not is_admin:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO support_tickets (user_id, message_id, chat_id, timestamp) VALUES (?, ?, ?, ?)",
                  (user_id, message.message_id, message.chat.id, int(time.time())))
        conn.commit()
        conn.close()

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✉️ Ответить", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data=f"sup_ignore_{user_id}")
        )

        caption = (f"📩 <b>Новое обращение в поддержку</b> ❗\n\n"
                   f"👤 <b>От пользователя:</b> <a href='tg://user?id={user_id}'>{user_id}</a>\n"
                   f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                   f"⏰ <b>Время:</b> {time.strftime('%d.%m.%Y %H:%M')}")

        try:
            bot.copy_message(ADMIN_ID, user_id, message.message_id, caption=caption, reply_markup=markup)
        except:
            bot.forward_message(ADMIN_ID, user_id, message.message_id)
            bot.send_message(ADMIN_ID, caption, reply_markup=markup)

        bot.send_message(user_id, "✅ <b>Сообщение отправлено в поддержку!</b>\nМы ответим скоро 🚀", reply_markup=get_main_menu(is_admin))
        waiting_message.pop(user_id, None)
        return

    # === Ручной ввод ID для анонимного ответа ===
    if waiting_message.get(user_id) == "manual_reply":
        if text.isdigit():
            target = int(text)
            waiting_message[user_id] = target
            bot.send_message(user_id, "🕶 <b>Теперь отправь сообщение анонимно</b> (текст, фото, видео...):", reply_markup=cancel_menu)
        else:
            bot.send_message(user_id, "❌ <b>Некорректный ID! Введи только цифры.</b>", reply_markup=cancel_menu)
        return

    # === Отправка анонимного сообщения (по ссылке, ответу или вручную) ===
    if user_id in waiting_message:
        target_id = waiting_message.pop(user_id)

        if target_id in blocked_users and not is_admin:
            bot.send_message(user_id, "🚫 <b>Пользователь отключил приём сообщений</b>", reply_markup=get_main_menu(is_admin))
            return

        content_type = message.content_type
        content_text = text

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO anon_messages (sender, receiver, content, type, timestamp) VALUES (?, ?, ?, ?, ?)",
                  (user_id, target_id, content_text, content_type, int(time.time())))
        conn.commit()
        conn.close()

        increment_stat(target_id, "messages_received")

        # Инлайн-кнопки ВСЕГДА (кроме если отправитель — админ)
        markup = None
        if user_id != ADMIN_ID:
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✉️ Ответить анонимно", callback_data=f"reply_{user_id}"),
                InlineKeyboardButton("🚫 Игнор", callback_data="ignore")
            )

        try:
            if content_type == 'text':
                bot.send_message(target_id, f"🕶 <b>Анонимное сообщение</b> ✨\n\n{content_text}", reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id, reply_markup=markup)
                if content_type != 'sticker':
                    bot.send_message(target_id, "🕶 <b>Анонимное сообщение</b> ✨", reply_to_message_id=copied.message_id)
        except:
            bot.send_message(user_id, "❌ <b>Не удалось доставить</b> — пользователь заблокировал бота или удалил аккаунт.")

        bot.send_message(user_id, "✅ <b>Сообщение отправлено анонимно!</b> 🚀", reply_markup=get_main_menu(is_admin))
        return

# ====== Callback анонимные сообщения ======
@bot.callback_query_handler(func=lambda call: call.data.startswith("reply_") or call.data == "ignore")
def anon_callback(call):
    user_id = call.from_user.id
    if call.data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "🚫 Проигнорировано")
        return

    sender_id = int(call.data.split("_")[1])
    now = time.time()
    if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
        bot.answer_callback_query(call.id, f"⏱ Подожди {ANTISPAM_INTERVAL} сек")
        return

    waiting_message[user_id] = sender_id
    last_message_time[user_id] = now

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(user_id, "🕶 <b>Напиши ответ</b> — он уйдёт анонимно! (текст, фото, видео...)", reply_markup=cancel_menu)
    bot.answer_callback_query(call.id, "✉️ Пиши ответ!")

# ====== Callback поддержка ======
@bot.callback_query_handler(func=lambda call: call.data.startswith("sup_reply_") or call.data.startswith("sup_ignore_"))
def support_callback(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "❌ Доступ запрещён")
        return

    user_id = int(call.data.split("_")[-1])

    if call.data.startswith("sup_ignore_"):
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "🚫 Игнорировано")
        return

    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(ADMIN_ID,
        f"✉️ <b>Ответ пользователю</b> <a href='tg://user?id={user_id}'>{user_id}</a>\n\n"
        f"Отправь сообщение — оно придёт ему от бота.",
        reply_markup=cancel_menu)
    waiting_message[ADMIN_ID] = f"admin_reply_{user_id}"
    bot.answer_callback_query(call.id, "Пиши ответ")

# ====== Ответ админа в поддержку ======
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and str(waiting_message.get(ADMIN_ID, "")).startswith("admin_reply_"))
def admin_support_reply(message):
    target_str = waiting_message.pop(ADMIN_ID)
    target_id = int(target_str.split("_")[2])

    try:
        bot.copy_message(target_id, ADMIN_ID, message.message_id)
        bot.send_message(ADMIN_ID, "✅ <b>Ответ отправлен пользователю!</b>", reply_markup=admin_menu)
    except:
        bot.send_message(ADMIN_ID, "❌ <b>Не удалось отправить</b> — пользователь заблокировал бота.")

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
