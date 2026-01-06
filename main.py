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
from collections import Counter
import re

# ====== Конфигурация ======
PLAY = os.getenv("PLAY") or "YOUR_BOT_TOKEN_HERE"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = 7549204023
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
    CREATE TABLE IF NOT EXISTS support_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        original_message_id INTEGER,
        forwarded_message_id INTEGER,
        chat_id INTEGER,
        timestamp INTEGER
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
waiting_message = {}        # {user_id: target или режим}
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
    markup.row(KeyboardButton("📌 Профиль"), KeyboardButton("🔥 Топ-10"))
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
        username = f"@{row[0]}" if row[0] else "отсутствует"
        name = row[1] or "Неизвестно"
        clicks = row[2] or 0
        received = row[3] or 0
        sent = row[4] or 0
        last = time.strftime("%d.%m.%Y %H:%M", time.localtime(row[5])) if row[5] else "никогда"
        return name, username, clicks, received, sent, last
    return "Неизвестно", "отсутствует", 0, 0, 0, "никогда"

def is_blocked(user_id):
    return user_id in blocked_users

def block_user(user_id):
    if user_id not in blocked_users:
        blocked_users.add(user_id)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO blocked_users (user_id, blocked_at) VALUES (?, ?)", (user_id, int(time.time())))
        conn.commit()
        conn.close()

def unblock_user(user_id):
    if user_id in blocked_users:
        blocked_users.discard(user_id)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

def get_top_words(user_id, limit=5):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT content FROM anon_messages WHERE sender = ? AND type = 'text'", (user_id,))
    texts = [row[0] for row in c.fetchall() if row[0]]
    conn.close()

    all_words = []
    for text in texts:
        words = re.findall(r'\b\w+\b', text.lower())
        all_words.extend(words)
    
    if not all_words:
        return "Нет текстовых анонимных сообщений"
    
    counter = Counter(all_words)
    top = counter.most_common(limit)
    return "\n".join([f"• {word} — {count} раз" for word, count in top])

def resolve_user_id(text):
    if text.isdigit():
        return int(text)
    if text.startswith("@"):
        username = text[1:]
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None
    return None

def show_top10(chat_id, is_admin=False):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""SELECT user_id, messages_received, link_clicks 
                 FROM users 
                 ORDER BY messages_received DESC, link_clicks DESC 
                 LIMIT 10""")
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.send_message(chat_id, "🔥 <b>Топ-10 пуст</b> — мало активности!")
        return

    text = "🔥 <b>Топ-10 самых популярных профилей</b> 🏆\n\n"
    for i, (uid, msgs, clicks) in enumerate(rows, 1):
        name, username, _, _, _, _ = get_user_info(uid)
        text += f"<b>{i}.</b> {name} ({username})\n"
        text += f"   🆔 <code>{uid}</code>\n"
        text += f"   💬 Получено: <code>{msgs}</code> | 👀 Переходы: <code>{clicks}</code>\n\n"
    bot.send_message(chat_id, text, reply_markup=admin_menu if is_admin else get_main_menu(is_admin))

def show_user_profile(admin_id, target_id):
    name, username, clicks, received, sent, last = get_user_info(target_id)
    top_words = get_top_words(target_id)
    blocked = "Да" if is_blocked(target_id) else "Нет"

    text = f"🔍 <b>Полная информация о пользователе</b>\n\n"
    text += f"👤 <b>Имя:</b> {name}\n"
    text += f"🌀 <b>Username:</b> {username}\n"
    text += f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
    text += f"⏰ <b>Последняя активность:</b> {last}\n"
    text += f"🚫 <b>Заблокирован:</b> {blocked}\n\n"
    text += f"📊 <b>Статистика</b>\n"
    text += f"💌 Получено анонимок: <code>{received}</code>\n"
    text += f"📤 Отправлено анонимок: <code>{sent}</code>\n"
    text += f"👀 Переходов по ссылке: <code>{clicks}</code>\n\n"
    text += f"🔥 <b>Топ-5 самых частых слов в анонимках:</b>\n{top_words}"

    bot.send_message(admin_id, text, reply_markup=admin_menu)

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user = message.from_user
    if is_blocked(user.id):
        bot.send_message(user.id, "🚫 <b>Вы заблокированы в этом боте.</b>")
        return

    update_user(user)
    user_id = user.id
    is_admin = (user_id == ADMIN_ID)

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.send_message(user_id, f"⏱ <b>Подожди {ANTISPAM_INTERVAL} секунд</b> перед отправкой!")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now
        bot.send_message(user_id,
            "🕶 <b>Отправь сообщение анонимно</b> (текст, фото, видео, стикер...):\nОно уйдёт полностью анонимно ✨",
            reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
        f"🎉 <b>Добро пожаловать в {BOT_NAME}!</b> 🎉\n\n"
        f"🔗 <b>Твоя анонимная ссылка:</b>\n<code>{link}</code>\n\n"
        f"Распространяй — получай анонимки с кнопками <b>«Ответить»</b> и <b>«Игнор»</b> 🚀",
        reply_markup=get_main_menu(is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_all(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        bot.send_message(user_id, "🚫 <b>Вы заблокированы в этом боте.</b>")
        return

    is_admin = (user_id == ADMIN_ID)
    text = message.text or message.caption or ""

    update_user(message.from_user)

    # === Блокировка: проверка на каждом сообщении ===
    if is_blocked(user_id) and text != "❌ Отмена":
        bot.send_message(user_id, "🚫 <b>Вы заблокированы в этом боте.</b>")
        return

    # === Админ-панель ===
    if is_admin:
        if text == "🔧 Админ-панель":
            bot.send_message(user_id, "🔧 <b>Админ-панель</b>", reply_markup=admin_menu)
            return
        if text == "📊 Статистика бота":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users"); total_users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM anon_messages"); total_msgs = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM blocked_users"); blocked = c.fetchone()[0]
            conn.close()
            bot.send_message(user_id,
                f"📊 <b>Статистика</b>\n\n"
                f"👥 Пользователей: <code>{total_users}</code>\n"
                f"💬 Анонимных сообщений: <code>{total_msgs}</code>\n"
                f"🚫 Заблокировано: <code>{blocked}</code>",
                reply_markup=admin_menu)
            return
        if text == "📨 Рассылка":
            bot.send_message(user_id, "📨 Отправь сообщение для рассылки:", reply_markup=cancel_menu)
            waiting_message[user_id] = "broadcast"
            return
        if text in ["🔥 Топ-10 пользователей", "🔥 Топ-10"]:
            show_top10(user_id, True)
            return
        if text == "🔍 Проверка пользователя":
            bot.send_message(user_id, "🔍 Введи ID или @username:", reply_markup=cancel_menu)
            waiting_message[user_id] = "check_user"
            return
        if text == "🚫 Заблокировать":
            bot.send_message(user_id, "🚫 Введи ID для блокировки:", reply_markup=cancel_menu)
            waiting_message[user_id] = "block_user"
            return
        if text == "✅ Разблокировать":
            bot.send_message(user_id, "✅ Введи ID для разблокировки:", reply_markup=cancel_menu)
            waiting_message[user_id] = "unblock_user"
            return
        if text == "⬅️ Назад в главное меню":
            bot.send_message(user_id, "🏠 Главное меню", reply_markup=get_main_menu(True))
            return

    # === Основное меню ===
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, f"🔗 <b>Твоя ссылка:</b>\n\n<code>{link}</code>", reply_markup=get_main_menu(is_admin))

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
        bot.send_photo(user_id, bio, caption=f"📱 <b>QR-код</b>\n\n<i>{link}</i>", reply_markup=get_main_menu(is_admin))

    elif text == "📌 Профиль":
        name, username, clicks, received, sent, last = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
            f"📌 <b>Профиль</b>\n\n"
            f"👤 Имя: {name}\n"
            f"🌀 Username: {username}\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"⏰ Активность: {last}\n\n"
            f"💌 Получено: <code>{received}</code>\n"
            f"📤 Отправлено: <code>{sent}</code>\n"
            f"👀 Переходы: <code>{clicks}</code>\n\n"
            f"{link}",
            reply_markup=get_main_menu(is_admin))

    elif text == "🔥 Топ-10":
        show_top10(user_id, is_admin)

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ Настройки", reply_markup=settings_menu)

    elif text == "🔕 Отключить приём":
        bot.send_message(user_id, "🔕 Приём отключён 🔒", reply_markup=get_main_menu(is_admin))

    elif text == "🔔 Включить приём":
        bot.send_message(user_id, "🔔 Приём включён ✅", reply_markup=get_main_menu(is_admin))

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id,
            "ℹ️ <b>Помощь</b>\n\n"
            "1. Получи ссылку/QR\n"
            "2. Распространи\n"
            "3. Получай анонимки с кнопками\n"
            "4. Отвечай анонимно!\n\n"
            f"⏱ Лимит: 1 сообщение / {ANTISPAM_INTERVAL} сек",
            reply_markup=get_main_menu(is_admin))

    elif text == "📩 Поддержка":
        bot.send_message(user_id, "📩 Напиши вопрос или проблему (можно с медиа):", reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id, "🔍 Введи ID получателя:", reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"
        return

    elif text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        bot.send_message(user_id, "❌ Отменено", reply_markup=get_main_menu(is_admin))
        return

    # === Админ: действия с пользователями ===
    if is_admin:
        if waiting_message.get(user_id) == "check_user":
            target = resolve_user_id(text)
            if target:
                show_user_profile(user_id, target)
            else:
                bot.send_message(user_id, "❌ Пользователь не найден")
            waiting_message.pop(user_id, None)
            return

        if waiting_message.get(user_id) == "block_user":
            if text.isdigit():
                block_user(int(text))
                bot.send_message(user_id, f"🚫 Заблокирован <code>{text}</code>", reply_markup=admin_menu)
            else:
                bot.send_message(user_id, "❌ Только цифры ID")
            waiting_message.pop(user_id, None)
            return

        if waiting_message.get(user_id) == "unblock_user":
            if text.isdigit():
                unblock_user(int(text))
                bot.send_message(user_id, f"✅ Разблокирован <code>{text}</code>", reply_markup=admin_menu)
            else:
                bot.send_message(user_id, "❌ Только цифры ID")
            waiting_message.pop(user_id, None)
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

        bot.send_message(user_id, f"📨 Рассылка завершена\n✅ {sent}\n❌ {failed}", reply_markup=admin_menu)
        waiting_message.pop(user_id, None)
        return

    # === Поддержка ===
    if waiting_message.get(user_id) == "support":
        name, username, _, _, _, _ = get_user_info(user_id)

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✉️ Ответить", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data=f"sup_ignore_{user_id}")
        )

        caption = (
            f"📩 <b>Новое обращение в поддержку</b> ❗\n\n"
            f"👤 <b>Имя:</b> {name}\n"
            f"🌀 <b>Username:</b> {username}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"⏰ <b>Время:</b> {time.strftime('%d.%m.%Y %H:%M')}"
        )

        forwarded = None
        try:
            forwarded = bot.copy_message(
                ADMIN_ID, user_id, message.message_id,
                caption=caption if message.content_type in ['text', 'photo', 'video', 'document'] else None,
                reply_markup=markup
            )
            if message.content_type not in ['text', 'photo', 'video', 'document']:
                bot.send_message(ADMIN_ID, caption, reply_to_message_id=forwarded.message_id, reply_markup=markup)
        except:
            forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
            bot.send_message(ADMIN_ID, caption, reply_to_message_id=forwarded.message_id, reply_markup=markup)

        bot.send_message(user_id, "✅ Обращение отправлено! Скоро ответим 🚀", reply_markup=get_main_menu(is_admin))
        waiting_message.pop(user_id, None)
        return

    # === Ручной ответ по ID ===
    if waiting_message.get(user_id) == "manual_reply":
        if text.isdigit():
            target = int(text)
            if is_blocked(target):
                bot.send_message(user_id, "🚫 Этот пользователь заблокирован")
                waiting_message.pop(user_id, None)
                return
            waiting_message[user_id] = target
            bot.send_message(user_id, "🕶 Отправь анонимное сообщение:", reply_markup=cancel_menu)
        else:
            bot.send_message(user_id, "❌ Только цифры ID")
        return

    # === Отправка анонимного сообщения ===
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)

        if is_blocked(target_id):
            bot.send_message(user_id, "🚫 Получатель заблокирован")
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
        increment_stat(user_id, "messages_sent")

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
            bot.send_message(user_id, "❌ Не удалось доставить (пользователь заблокировал бота)")

        bot.send_message(user_id, "✅ Анонимно отправлено! 🚀", reply_markup=get_main_menu(is_admin))
        return

# ====== Callback ======
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    if is_blocked(user_id):
        bot.answer_callback_query(call.id, "🚫 Вы заблокированы")
        return

    if call.data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "🚫 Игнорировано")
        return

    if call.data.startswith("reply_"):
        sender_id = int(call.data.split("_")[1])
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > time.time():
            bot.answer_callback_query(call.id, f"⏱ Подожди {ANTISPAM_INTERVAL} сек")
            return
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "🕶 Напиши ответ анонимно:", reply_markup=cancel_menu)
        bot.answer_callback_query(call.id, "Пиши!")

    if call.data.startswith("sup_reply_") and user_id == ADMIN_ID:
        target = int(call.data.split("_")[-1])
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        bot.send_message(ADMIN_ID, f"✉️ Ответ пользователю <code>{target}</code>:\nОтправь сообщение — уйдёт от бота.", reply_markup=cancel_menu)
        waiting_message[ADMIN_ID] = f"admin_reply_{target}"
        bot.answer_callback_query(call.id, "Пиши")

    if call.data.startswith("sup_ignore_") and user_id == ADMIN_ID:
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Игнорировано")

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and str(waiting_message.get(ADMIN_ID, "")).startswith("admin_reply_"))
def admin_support_reply(message):
    target_str = waiting_message.pop(ADMIN_ID)
    target_id = int(target_str.split("_")[2])
    try:
        bot.copy_message(target_id, ADMIN_ID, message.message_id)
        bot.send_message(ADMIN_ID, "✅ Ответ отправлен!", reply_markup=admin_menu)
    except:
        bot.send_message(ADMIN_ID, "❌ Не удалось — пользователь заблокировал бота")

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
