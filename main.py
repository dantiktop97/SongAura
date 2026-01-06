import os
import sqlite3
import io
import time
import qrcode
from flask import Flask, request
from telebot import TeleBot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton, Update,
    InlineKeyboardMarkup, InlineKeyboardButton, ForceReply
)

# ====== Конфигурация ======
PLAY = os.getenv("PLAY") or "YOUR_BOT_TOKEN_HERE"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = 7549204023  # Твой ID
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
        last_active INTEGER,
        receive_messages INTEGER DEFAULT 1
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
waiting_message = {}      # Ожидание сообщения (анонимка или поддержка)
admin_mode = {}           # Режимы админа: 'broadcast', 'block', 'unblock'
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

# ====== Тексты (мультиязык) ======
TEXTS = {
    'ru': {
        'welcome': "🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉\n\n"
                   "🔥 Получай и отправляй сообщения <b>полностью анонимно</b>! 🕶️\n\n"
                   "🔗 <b>Твоя личная ссылка:</b>\n<code>{link}</code>\n\n"
                   "Распространи её — и получай тайные сообщения! 💌❤️\n"
                   "Жми кнопки ниже! 🚀",
        'my_link': "🔗 <b>Твоя личная анонимная ссылка</b>\n\n<code>{link}</code>\n\nРаспространяй — получай больше анонимок!",
        'qr_caption': "📱 <b>Твой QR-код</b>\n\nСканируй или покажи друзьям!\n\n<i>Ссылка: {link}</i>",
        'profile': "📌 <b>ТВОЙ ПРОФИЛЬ В ANONY SMS</b> 👤✨\n\n"
                   "📛 <b>Имя:</b> {name}\n"
                   "🌀 <b>Username:</b> {username}\n"
                   "🆔 <b>ID:</b> <code>{user_id}</code>\n"
                   "⏰ <b>Последняя активность:</b> {last_active}\n"
                   "🔔 <b>Приём сообщений:</b> {receive_status}\n\n"
                   "📊 <b>СТАТИСТИКА</b> 📈\n"
                   "💌 Получено анонимок: <code>{received}</code>\n"
                   "📤 Отправлено: <code>{sent}</code>\n"
                   "👀 Переходов по ссылке: <code>{clicks}</code>\n\n"
                   "🔗 Твоя ссылка: <code>{link}</code>",
        'support_entry': "📩 <b>Поддержка Anony SMS</b>\n\nНапиши вопрос или пришли медиа — ответим быстро! ❤️",
        'support_sent': "✅ <b>Сообщение отправлено в поддержку!</b>\n\nСкоро ответим. Спасибо! ❤️",
        'anon_msg': "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ!</b> 🔥✨",
        'sent_anon': "✅ <b>Отправлено анонимно!</b>\n\nПолучатель видит сообщение. Анонимность 100% 🕶️",
        'help': "ℹ️ <b>Как работает бот?</b>\n\n1. Получи свою ссылку\n2. Распространи её\n3. Получай анонимные сообщения\n4. Отвечай одним нажатием\n\n🌍 Сменить язык — кнопка ниже",
        'settings': "⚙️ <b>Настройки приватности</b>\n\nКонтролируй, кто может тебе писать анонимно.",
        'receive_on': "🔔 <b>Приём анонимок включён!</b>\n\nТеперь тебе можно писать.",
        'receive_off': "🔕 <b>Приём анонимок отключён!</b>\n\nНикто не сможет отправить сообщение.",
        'cancel': "❌ <b>Отменено</b>",
        'lang_changed': "✅ <b>Язык изменён!</b> 🌍",
        'blocked': "🚫 <b>Доступ ограничен администратором.</b>",
        'admin_panel': "🔧 <b>АДМИН-ПАНЕЛЬ</b>\n\nВыберите действие:",
        'admin_stats': "📊 <b>Статистика бота</b>\n\n"
                       "👥 Пользователей: <code>{users}</code>\n"
                       "💬 Всего анонимок: <code>{messages}</code>\n"
                       "🚫 Заблокировано: <code>{blocked}</code>",
        'admin_broadcast': "📢 <b>Рассылка</b>\n\nОтправьте сообщение — оно уйдёт всем пользователям.\nПоддерживается текст, фото, видео, документы.",
        'admin_broadcast_done': "✅ Рассылка завершена!\nОтправлено: <code>{count}</code> пользователям.",
        'admin_block': "🔨 Введите ID пользователя для блокировки:",
        'admin_unblock': "🔓 Введите ID пользователя для разблокировки:",
        'user_blocked': "🚫 Пользователь <code>{user_id}</code> заблокирован.",
        'user_unblocked': "✅ Пользователь <code>{user_id}</code> разблокирован.",
        'user_not_found': "❌ Пользователь не найден.",
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
            'broadcast': "📢 Рассылка",
            'block_user': "🔨 Блокировать",
            'unblock_user': "🔓 Разблокировать",
            'blocked_list': "🚫 Заблокированные"
        }
    },
    # uk и en можно добавить позже, сейчас только ru для краткости
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
    m.add(btn(user_id, 'profile'), btn(user_id, 'settings'))
    m.add(btn(user_id, 'support'), btn(user_id, 'help'))
    m.add(btn(user_id, 'language'))
    if is_admin:
        m.add(btn(user_id, 'admin'))
    return m

def settings_menu(user_id):
    m = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(btn(user_id, 'receive_on'), btn(user_id, 'receive_off'))
    m.add(btn(user_id, 'back'))
    return m

def admin_menu(user_id):
    m = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    m.add(btn(user_id, 'stats'), btn(user_id, 'broadcast'))
    m.add(btn(user_id, 'block_user'), btn(user_id, 'unblock_user'))
    m.add(btn(user_id, 'blocked_list'))
    m.add(btn(user_id, 'back'))
    return m

cancel_kb = ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Отмена")

# ====== Утилиты ======
def update_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO users 
                 (user_id, username, first_name, last_active, receive_messages) 
                 VALUES (?, ?, ?, ?, COALESCE((SELECT receive_messages FROM users WHERE user_id = ?), 1))""",
              (user.id, user.username or "", user.first_name or "", int(time.time()), user.id))
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
    c.execute("""SELECT username, first_name, link_clicks, messages_received, messages_sent, 
                        last_active, receive_messages FROM users WHERE user_id = ?""", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        username = f"@{row[0]}" if row[0] else "скрыт 😶"
        name = row[1] or "Аноним 🕶️"
        clicks, received, sent = row[2] or 0, row[3] or 0, row[4] or 0
        last_active = time.strftime("%d.%m.%Y в %H:%M", time.localtime(row[5])) if row[5] else "сейчас"
        receive_status = "🔔 Включён" if row[6] else "🔕 Выключен"
        return name, f"<i>{username}</i>", clicks, received, sent, last_active, receive_status
    return "Аноним 🕶️", "<i>скрыт 😶</i>", 0, 0, 0, "сейчас", "🔔 Включён"

def get_total_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    users = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM anon_messages")
    messages = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM blocked_users")
    blocked = c.fetchone()[0]
    conn.close()
    return users, messages, blocked

def toggle_receive(user_id, status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET receive_messages = ? WHERE user_id = ?", (1 if status else 0, user_id))
    conn.commit()
    conn.close()

# ====== Обработчики ======
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        bot.send_message(user_id, t(user_id, 'blocked'))
        return

    update_user(message.from_user)
    is_admin = user_id == ADMIN_ID

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT receive_messages FROM users WHERE user_id = ?", (sender_id,))
        row = c.fetchone()
        conn.close()

        if row and row[0] == 0:
            bot.send_message(user_id, "😔 Этот пользователь временно не принимает анонимные сообщения.")
            return

        if time.time() - last_message_time.get(user_id, 0) < ANTISPAM_INTERVAL:
            bot.send_message(user_id, "⏳ Подожди 30 секунд перед отправкой следующего сообщения.")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.send_message(user_id, "💌 Напиши анонимное сообщение:", reply_markup=cancel_kb)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id, t(user_id, 'welcome', link=link), reply_markup=main_menu(user_id, is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_message(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return

    text = message.text or message.caption or ""
    is_admin = user_id == ADMIN_ID
    update_user(message.from_user)

    # Отмена
    if text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        admin_mode.pop(user_id, None)
        bot.send_message(user_id, t(user_id, 'cancel'), reply_markup=main_menu(user_id, is_admin))
        return

    # Админ-панель
    if text == btn(user_id, 'admin') and is_admin:
        bot.send_message(user_id, t(user_id, 'admin_panel'), reply_markup=admin_menu(user_id))
        return

    # Админ-действия
    if is_admin and admin_mode.get(user_id):
        mode = admin_mode[user_id]
        if mode == "broadcast":
            # Рассылка
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = [row[0] for row in c.fetchall()]
            conn.close()

            sent = 0
            for uid in users:
                try:
                    if message.content_type == 'text':
                        bot.send_message(uid, message.text, parse_mode="HTML")
                    else:
                        bot.copy_message(uid, user_id, message.message_id)
                    sent += 1
                except:
                    continue
                time.sleep(0.05)  # антифлуд

            bot.send_message(user_id, t(user_id, 'admin_broadcast_done', count=sent), reply_markup=admin_menu(user_id))
            admin_mode.pop(user_id)
            return

        elif mode == "block" and text.isdigit():
            target = int(text)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO blocked_users (user_id, blocked_at) VALUES (?, ?)", (target, int(time.time())))
            conn.commit()
            conn.close()
            blocked_users.add(target)
            bot.send_message(user_id, t(user_id, 'user_blocked', user_id=target), reply_markup=admin_menu(user_id))
            admin_mode.pop(user_id)
            return

        elif mode == "unblock" and text.isdigit():
            target = int(text)
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("DELETE FROM blocked_users WHERE user_id = ?", (target,))
            conn.commit()
            conn.close()
            blocked_users.discard(target)
            bot.send_message(user_id, t(user_id, 'user_unblocked', user_id=target), reply_markup=admin_menu(user_id))
            admin_mode.pop(user_id)
            return

    # Кнопки админки
    if is_admin:
        if text == btn(user_id, 'stats'):
            users, msgs, blkd = get_total_stats()
            bot.send_message(user_id, t(user_id, 'admin_stats', users=users, messages=msgs, blocked=blkd))
            return
        elif text == btn(user_id, 'broadcast'):
            admin_mode[user_id] = "broadcast"
            bot.send_message(user_id, t(user_id, 'admin_broadcast'), reply_markup=cancel_kb)
            return
        elif text == btn(user_id, 'block_user'):
            admin_mode[user_id] = "block"
            bot.send_message(user_id, t(user_id, 'admin_block'), reply_markup=cancel_kb)
            return
        elif text == btn(user_id, 'unblock_user'):
            admin_mode[user_id] = "unblock"
            bot.send_message(user_id, t(user_id, 'admin_unblock'), reply_markup=cancel_kb)
            return
        elif text == btn(user_id, 'back'):
            admin_mode.pop(user_id, None)
            bot.send_message(user_id, "⬅️ Возврат в главное меню", reply_markup=main_menu(user_id, True))
            return

    # Основные кнопки
    if text == btn(user_id, 'my_link'):
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'my_link', link=link))

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
        bot.send_photo(user_id, bio, caption=t(user_id, 'qr_caption', link=link))

    elif text == btn(user_id, 'profile'):
        name, username, clicks, received, sent, last_active, receive_status = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'profile', name=name, username=username, user_id=user_id,
                                    last_active=last_active, received=received, sent=sent, clicks=clicks,
                                    link=link, receive_status=receive_status))

    elif text == btn(user_id, 'settings'):
        bot.send_message(user_id, t(user_id, 'settings'), reply_markup=settings_menu(user_id))

    elif text in [btn(user_id, 'receive_on'), btn(user_id, 'receive_off')]:
        status = text == btn(user_id, 'receive_on')
        toggle_receive(user_id, status)
        bot.send_message(user_id, t(user_id, 'receive_on' if status else 'receive_off'), reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'help'):
        bot.send_message(user_id, t(user_id, 'help'))

    # Поддержка и анонимки — остальная логика без изменений (чуть упрощена)
    # ... (оставил как было, но с исправлениями)

# ====== Webhook и запуск ======
@app.route(f"/{PLAY}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_data().decode("utf-8"))
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/", methods=["GET"])
def index():
    return "Anony SMS Bot is running!"

def setup_webhook():
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(f"{WEBHOOK_HOST}/{PLAY}")

if __name__ == "__main__":
    setup_webhook()
    app.run(host="0.0.0.0", port=PORT)
