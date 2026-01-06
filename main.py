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
DB_PATH = os.getenv("DB_PATH", "data.db")

BOT_USERNAME = "anonysms_bot"

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
user_language = {}

def load_blocked():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM blocked_users")
    for row in c.fetchall():
        blocked_users.add(row[0])
    conn.close()

load_blocked()

# ====== Мультиязычные данные ======
TEXTS = {
    'ru': {
        'welcome': "🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉\n\n"
                   "🔥 Получай и отправляй сообщения <b>полностью анонимно</b>! 🕶️\n\n"
                   "🔗 <b>Твоя личная ссылка:</b>\n<code>{link}</code>\n\n"
                   "Распространи её — и получай тайные сообщения! 💌❤️\n"
                   "Жми кнопки ниже! 🚀",
        'my_link': "🔗 <b>Твоя анонимная ссылка</b>\n\n<code>{link}</code>\n\nРаспространяй — получай больше анонимок!",
        'qr_caption': "📱 <b>Твой QR-код</b>\n\nСканируй или покажи друзьям!\n\n<i>Ссылка: {link}</i>",
        'profile': "📌 <b>ТВОЙ ПОЛНЫЙ ПРОФИЛЬ В ANONY SMS</b> 👤✨\n\n"
                   "📛 <b>Имя:</b> {name}\n"
                   "🌀 <b>Username:</b> {username}\n"
                   "🆔 <b>ID:</b> <code>{user_id}</code>\n"
                   "⏰ <b>Последняя активность:</b> {last_active}\n\n"
                   "📊 <b>ТВОЯ ВНУШИТЕЛЬНАЯ СТАТИСТИКА</b> 📈🔥\n"
                   "💌 Получено анонимных сообщений: <code>{received}</code>\n"
                   "📤 Отправлено анонимных сообщений: <code>{sent}</code>\n"
                   "👀 Переходов по твоей ссылке: <code>{clicks}</code>\n\n"
                   "🔗 Твоя ссылка: {link}\n\n"
                   "🚀 Ты — настоящая звезда анонимного общения! Продолжай сиять! ⭐❤️",
        'support_entry': "📩 <b>Поддержка Anony SMS</b>\n\nНапиши вопрос или пришли медиа — ответим быстро! ❤️",
        'support_sent': "✅ <b>Сообщение отправлено!</b>\n\nСкоро ответим. Спасибо! ❤️",
        'support_reply_header': "✉️ <b>Ответ от поддержки Anony SMS</b> 👨‍💻\n\nЕсли не по вашему вопросу — проигнорируйте.",
        'anon_msg': "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ!</b> 🔥✨",
        'sent_anon': "✅ <b>Отправлено анонимно!</b>\n\nПолучатель видит сообщение. Анонимность 100% 🕶️",
        'help': "ℹ️ <b>Как работает бот?</b>\n\n1. Получи ссылку\n2. Распространи\n3. Получай анонимки\n4. Отвечай одним нажатием\n\n🌍 Сменить язык — кнопка ниже",
        'settings': "⚙️ <b>Настройки приватности</b>\n\nКонтролируй приём сообщений.",
        'receive_on': "🔔 <b>Приём включён!</b>\n\nГотов к анонимкам! 🔥",
        'receive_off': "🔕 <b>Приём отключён!</b>\n\nТишина.",
        'cancel': "❌ <b>Отменено</b>\n\nВозвращаемся в меню",
        'lang_changed': "✅ <b>Язык изменён!</b> 🌍",
        'admin_stats': "📊 <b>Статистика бота</b>\n\nПользователей: {users}\nСообщений: {messages}",
        'top10': "🏆 <b>ТОП-10 пользователей</b>\n\n{top_list}",
        'buttons': {
            'my_link': "📩 Моя ссылка",
            'qr': "📱 QR-код",
            'settings': "⚙️ Настройки",
            'profile': "📌 Профиль",
            'support': "📩 Поддержка",
            'help': "ℹ️ Помощь",
            'language': "🌍 Язык",
            'admin': "🔧 Админ-панель",
            'receive_on': "🔔 Включить приём",
            'receive_off': "🔕 Отключить приём",
            'back': "⬅️ Назад",
            'stats': "📊 Статистика",
            'top10': "🔥 Топ-10"
        }
    },
    'en': {
        'welcome': "🎉 <b>Welcome to Anony SMS!</b> 🎉\n\n"
                   "🔥 Send & receive messages <b>anonymously</b>! 🕶️\n\n"
                   "🔗 <b>Your link:</b>\n<code>{link}</code>\n\n"
                   "Share it — get anonymous messages! 💌❤️\n"
                   "Tap below! 🚀",
        'my_link': "🔗 <b>Your anonymous link</b>\n\n<code>{link}</code>\n\nShare it!",
        'qr_caption': "📱 <b>Your QR code</b>\n\nScan or show friends!\n\n<i>Link: {link}</i>",
        'profile': "📌 <b>YOUR FULL PROFILE IN ANONY SMS</b> 👤✨\n\n"
                   "📛 <b>Name:</b> {name}\n"
                   "🌀 <b>Username:</b> {username}\n"
                   "🆔 <b>ID:</b> <code>{user_id}</code>\n"
                   "⏰ <b>Last active:</b> {last_active}\n\n"
                   "📊 <b>YOUR STATS</b> 📈🔥\n"
                   "💌 Received: <code>{received}</code>\n"
                   "📤 Sent: <code>{sent}</code>\n"
                   "👀 Clicks: <code>{clicks}</code>\n\n"
                   "🔗 Your link: {link}\n\n"
                   "🚀 You're a star! Keep shining! ⭐❤️",
        'support_entry': "📩 <b>Support</b>\n\nSend question or media — fast reply!",
        'support_sent': "✅ <b>Sent!</b>\n\nWe'll reply soon.",
        'support_reply_header': "✉️ <b>Reply from support</b> 👨‍💻\n\nIf not your question — ignore.",
        'anon_msg': "🕶️ <b>ANONYMOUS MESSAGE!</b> 🔥✨",
        'sent_anon': "✅ <b>Sent anonymously!</b>\n\n100% anonymous 🕶️",
        'help': "ℹ️ <b>How it works</b>\n\n1. Get link\n2. Share\n3. Receive messages\n4. Reply\n\n🌍 Change language — button below",
        'settings': "⚙️ <b>Privacy settings</b>\n\nControl receiving.",
        'receive_on': "🔔 <b>Receiving enabled!</b>",
        'receive_off': "🔕 <b>Receiving disabled!</b>",
        'cancel': "❌ <b>Cancelled</b>",
        'lang_changed': "✅ <b>Language changed!</b> 🌍",
        'admin_stats': "📊 <b>Bot stats</b>\n\nUsers: {users}\nMessages: {messages}",
        'top10': "🏆 <b>Top-10 users</b>\n\n{top_list}",
        'buttons': {
            'my_link': "📩 My link",
            'qr': "📱 QR code",
            'settings': "⚙️ Settings",
            'profile': "📌 Profile",
            'support': "📩 Support",
            'help': "ℹ️ Help",
            'language': "🌍 Language",
            'admin': "🔧 Admin panel",
            'receive_on': "🔔 Enable receiving",
            'receive_off': "🔕 Disable receiving",
            'back': "⬅️ Back",
            'stats': "📊 Stats",
            'top10': "🔥 Top-10"
        }
    }
    # Добавь 'uk' если нужно — по аналогии с 'ru'
}

def t(user_id, key, **kwargs):
    lang = user_language.get(user_id, 'ru')
    return TEXTS.get(lang, TEXTS['ru'])[key].format(**kwargs)

def btn(user_id, key):
    lang = user_language.get(user_id, 'ru')
    return TEXTS.get(lang, TEXTS['ru'])['buttons'][key]

# ====== Клавиатуры ======
def main_menu(user_id, is_admin=False):
    m = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(btn(user_id, 'my_link'), btn(user_id, 'qr'))
    m.add(btn(user_id, 'settings'))
    m.add(btn(user_id, 'profile'))
    m.add(btn(user_id, 'support'), btn(user_id, 'help'))
    m.add(btn(user_id, 'language'))
    if is_admin:
        m.add(btn(user_id, 'admin'))
    return m

def settings_menu(user_id):
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(btn(user_id, 'receive_on'), btn(user_id, 'receive_off'))
    m.add(btn(user_id, 'back'))
    return m

def admin_menu(user_id):
    m = ReplyKeyboardMarkup(resize_keyboard=True)
    m.add(btn(user_id, 'stats'), btn(user_id, 'top10'))
    m.add(btn(user_id, 'back'))
    return m

cancel_menu = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_menu.add("❌ Отмена")

# ====== Утилиты ======
def update_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (user_id, username, first_name, last_active) VALUES (?, ?, ?, ?)",
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
    lang = user_language.get(user_id, 'ru')
    if row:
        username = f"@{row[0]}" if row[0] else ("скрыт 😶" if lang == 'ru' else "hidden 😶")
        username = f"<i>{username}</i>"
        name = row[1] or "Аноним 🕶️"
        clicks, received, sent = row[2] or 0, row[3] or 0, row[4] or 0
        last_active = time.strftime("%d.%m.%Y в %H:%M", time.localtime(row[5])) if row[5] else "сейчас"
        return name, username, clicks, received, sent, last_active
    return "Аноним 🕶️", "<i>скрыт 😶</i>", 0, 0, 0, "сейчас"

def get_bot_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM anon_messages")
    messages = c.fetchone()[0]
    conn.close()
    return users, messages

def get_top10():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, messages_received, link_clicks FROM users ORDER BY messages_received DESC, link_clicks DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    top_list = ""
    for i, (uid, rec, clk) in enumerate(rows, 1):
        name, _, _, _, _, _ = get_user_info(uid)
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        top_list += f"{medal} <b>{name}</b> — 💌 {rec} | 👀 {clk}\n"
    return top_list or "Пока пусто"

# ====== Обработчики ======
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        bot.send_message(user_id, "Доступ ограничен")
        return

    update_user(message.from_user)
    is_admin = user_id == ADMIN_ID

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")
        if time.time() - last_message_time.get(user_id, 0) < ANTISPAM_INTERVAL:
            bot.send_message(user_id, "Подожди немного")
            return
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.send_message(user_id, "Готов отправить анонимное сообщение?", reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id, t(user_id, 'welcome', link=link), reply_markup=main_menu(user_id, is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_all(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return

    is_admin = user_id == ADMIN_ID
    text = message.text or message.caption or ""

    update_user(message.from_user)

    # Отмена
    if text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        admin_reply_mode.pop(user_id, None)
        bot.send_message(user_id, t(user_id, 'cancel'), reply_markup=main_menu(user_id, is_admin))
        return

    # Язык
    if text == btn(user_id, 'language'):
        markup = InlineKeyboardMarkup(row_width=3)
        markup.add(
            InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk"),
            InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
        )
        bot.send_message(user_id, "Выберите язык:", reply_markup=markup)
        return

    # Админ-панель
    if is_admin and text == btn(user_id, 'admin'):
        bot.send_message(user_id, "Админ-панель", reply_markup=admin_menu(user_id))
        return

    if is_admin and text == btn(user_id, 'stats'):
        users, messages = get_bot_stats()
        bot.send_message(user_id, t(user_id, 'admin_stats', users=users, messages=messages), reply_markup=admin_menu(user_id))

    if is_admin and text == btn(user_id, 'top10'):
        top_list = get_top10()
        bot.send_message(user_id, t(user_id, 'top10', top_list=top_list), reply_markup=admin_menu(user_id))

    if is_admin and text == btn(user_id, 'back'):
        bot.send_message(user_id, "Главное меню", reply_markup=main_menu(user_id, True))
        return

    # Поддержка
    if text == btn(user_id, 'support'):
        bot.send_message(user_id, t(user_id, 'support_entry'), reply_markup=cancel_menu)
        waiting_message[user_id] = ("support", message.message_id)
        return

    if waiting_message.get(user_id) and waiting_message[user_id][0] == "support":
        _, orig_msg_id = waiting_message.pop(user_id)
        name, username, _, received, sent, _ = get_user_info(user_id)
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Ответить", callback_data=f"sup_reply_{user_id}_{orig_msg_id}"),
            InlineKeyboardButton("Игнор", callback_data=f"sup_ignore_{user_id}")
        )
        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, f"Новое обращение от {name} (@{username or 'скрыт'}) ID: {user_id}", reply_to_message_id=forwarded.message_id, reply_markup=kb)
        bot.send_message(user_id, t(user_id, 'support_sent'), reply_markup=main_menu(user_id, is_admin))
        return

    # Админ ответ
    if is_admin and user_id in admin_reply_mode:
        target_id, orig_msg_id = admin_reply_mode.pop(user_id)
        header = t(target_id, 'support_reply_header')
        try:
            if message.content_type == 'text':
                bot.send_message(target_id, f"{header}\n\n{message.text}", reply_to_message_id=orig_msg_id)
            else:
                bot.copy_message(target_id, user_id, message.message_id, reply_to_message_id=orig_msg_id)
                bot.send_message(target_id, header, reply_to_message_id=orig_msg_id)
            bot.send_message(user_id, "Ответ отправлен как reply")
        except:
            bot.send_message(user_id, "Ошибка доставки")
        return

    # Анонимка
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)
        increment_stat(target_id, "messages_received")
        increment_stat(user_id, "messages_sent")
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Ответить анонимно", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("Игнор", callback_data="ignore")
        )
        try:
            if message.content_type == 'text':
                bot.send_message(target_id, t(target_id, 'anon_msg') + ("\n\n" + text if text else ""), reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id)
                bot.send_message(target_id, t(target_id, 'anon_msg'), reply_to_message_id=copied.message_id, reply_markup=markup)
        except:
            bot.send_message(user_id, "Не удалось доставить")
            return
        bot.send_message(user_id, t(user_id, 'sent_anon'), reply_markup=main_menu(user_id, is_admin))
        return

    # Основные кнопки
    if text == btn(user_id, 'my_link'):
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'my_link', link=link), reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'qr'):
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        qr = qrcode.QRCode(box_size=10, border=4)
        qr.add_data(link)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        bio = io.BytesIO()
        bio.name = "qr.png"
        img.save(bio, "PNG")
        bio.seek(0)
        bot.send_photo(user_id, bio, caption=t(user_id, 'qr_caption', link=link), reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'profile'):
        name, username, clicks, received, sent, last_active = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'profile', name=name, username=username, user_id=user_id,
                                    last_active=last_active, received=received, sent=sent, clicks=clicks, link=link),
                         reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'settings'):
        bot.send_message(user_id, t(user_id, 'settings'), reply_markup=settings_menu(user_id))

    elif text in [btn(user_id, 'receive_on'), btn(user_id, 'receive_off')]:
        on = text == btn(user_id, 'receive_on')
        bot.send_message(user_id, t(user_id, 'receive_on' if on else 'receive_off'), reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'help'):
        bot.send_message(user_id, t(user_id, 'help'), reply_markup=main_menu(user_id, is_admin))

# ====== Callbacks ======
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    if user_id in blocked_users:
        return

    data = call.data

    if data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    elif data.startswith("reply_"):
        sender_id = int(data.split("_")[1])
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "Напиши анонимный ответ", reply_markup=cancel_menu)

    elif data.startswith("sup_reply_") and user_id == ADMIN_ID:
        parts = data.split("_")
        target_id = int(parts[2])
        orig_msg_id = int(parts[3])
        admin_reply_mode[ADMIN_ID] = (target_id, orig_msg_id)
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        bot.send_message(ADMIN_ID, "Отправь ответ — будет как reply", reply_markup=cancel_menu)

    elif data.startswith("lang_"):
        new_lang = data.split("_")[1]
        user_language[user_id] = new_lang
        bot.answer_callback_query(call.id)
        bot.send_message(user_id, t(user_id, 'lang_changed'), reply_markup=main_menu(user_id, user_id == ADMIN_ID))

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
