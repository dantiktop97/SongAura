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
user_language = {}  # user_id -> 'ru' / 'uk' / 'en'

def load_blocked():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM blocked_users")
    for row in c.fetchall():
        blocked_users.add(row[0])
    conn.close()

load_blocked()

# ====== Мультиязычные тексты ======
TEXTS = {
    'ru': {
        'welcome': "🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉\n\n"
                   "🔥 Здесь ты можешь <b>получать и отправлять сообщения полностью анонимно</b>! 🕶️\n\n"
                   "🔗 <b>Твоя личная ссылка:</b>\n<code>{link}</code>\n\n"
                   "📢 Распространи её среди друзей — и получай тайные признания и секреты! 💌❤️\n"
                   "Готов к анонимности? Жми кнопки ниже! 🚀✨",
        'my_link': "🔗 <b>Твоя личная анонимная ссылка</b> 🔥\n\n<code>{link}</code>\n\nКопируй и распространяй — больше переходов = больше анонимок! 💥",
        'qr_caption': "📱 <b>Твой эксклюзивный QR-код</b> 🌟\n\nСканируй или покажи друзьям — мгновенный доступ к анонимности! ⚡\n\n<i>Ссылка: {link}</i>",
        'profile': "📌 <b>Твой профиль Anony SMS</b> 👤✨\n\n"
                   "📛 <b>Имя:</b> {name}\n🌀 <b>Username:</b> {username}\n🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                   "📊 <b>Статистика:</b> 🔥\n💌 Получено: <b><code>{received}</code></b>\n📤 Отправлено: <b><code>{sent}</code></b>\n👀 Переходов: <b><code>{clicks}</code></b>\n\n"
                   "🔗 Ссылка: {link}\n\nТы — звезда анонимности! ⭐❤️",
        'support_entry': "📩 <b>Служба поддержки Anony SMS</b> 👨‍💻✨\n\nМы всегда на связи! ❤️\n\nНапиши вопрос, пришли фото, видео или голосовое — ответим быстро! 🌟",
        'support_sent': "✅ <b>Обращение отправлено!</b> 🎉\n\nМы получили сообщение и скоро ответим. Спасибо, что ты с нами! ❤️",
        'support_reply': "✉️ <b>Ответ от поддержки Anony SMS</b> 👨‍💻\n\nЕсли не по вашему вопросу — проигнорируйте.",
        'anon_msg': "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ!</b> 🔥✨",
        'sent_anon': "✅ <b>Сообщение отправлено анонимно!</b> 🎉\n\nПолучатель видит его. Анонимность 100% 🕶️",
        'help': "ℹ️ <b>Как работает Anony SMS?</b>\n\n"
                "1️⃣ Получи ссылку или QR-код\n2️⃣ Распространи её\n3️⃣ Получай анонимные сообщения\n4️⃣ Отвечай одним нажатием\n\n"
                "🚀 Всё просто и безопасно!\n\nСмена языка: /lang",
        'telegram_info': "🏆 <b>Telegram — лучший мессенджер в мире!</b> 🚀\n\n"
                         "🔹 <b>Simple</b>\nTelegram is so simple you already know how to use it.\n\n"
                         "🔹 <b>Private</b>\nСообщения шифруются и могут самоуничтожаться.\n\n"
                         "🔹 <b>Synced</b>\nДоступ с любых устройств.\n\n"
                         "🔹 <b>Fast</b>\nСамая быстрая доставка.\n\n"
                         "🔹 <b>Powerful</b>\nБез лимитов на медиа и чаты.\n\n"
                         "🔹 <b>Open</b>\nОткрытый API и исходный код.\n\n"
                         "🔹 <b>Secure</b>\nЗащита от хакеров.\n\n"
                         "🔹 <b>Social</b>\nГруппы до 200,000 человек.\n\n"
                         "🔹 <b>Expressive</b>\nПолная кастомизация.\n\n"
                         "❤️ Anony SMS работает на Telegram — твоя приватность под надёжной защитой!",
        'settings': "⚙️ <b>Настройки приватности</b> 🔒\n\nКонтролируй приём анонимных сообщений.",
        'receive_on': "🔔 <b>Приём сообщений включён!</b> ✅\n\nГотов к новым анонимкам! 🔥❤️",
        'receive_off': "🔕 <b>Приём сообщений отключён!</b> 🔒\n\nТишина и покой. Включи, когда захочешь!",
        'cancel': "❌ <b>Действие отменено</b>\n\nВозвращаемся в главное меню 🏠",
        'lang_changed': "✅ <b>Язык успешно изменён!</b> 🌍✨",
        'buttons': {
            'my_link': "📩 Моя ссылка",
            'qr': "📱 QR-код",
            'settings': "⚙️ Настройки",
            'profile': "📌 Профиль",
            'support': "📩 Поддержка",
            'help': "ℹ️ Помощь",
            'telegram': "ℹ️ О Telegram",
            'admin': "🔧 Админ-панель",
            'back': "⬅️ Назад в меню"
        }
    },
    'uk': {
        'welcome': "🎉 <b>Ласкаво просимо в Anony SMS!</b> 🎉\n\n"
                   "🔥 Тут ти можеш <b>отримувати та надсилати повідомлення повністю анонімно</b>! 🕶️\n\n"
                   "🔗 <b>Твоє особисте посилання:</b>\n<code>{link}</code>\n\n"
                   "📢 Поширюй його — і отримуй таємні зізнання та секрети! 💌❤️\n"
                   "Готовий до анонімності? Тисни кнопки! 🚀✨",
        'my_link': "🔗 <b>Твоє анонімне посилання</b> 🔥\n\n<code>{link}</code>\n\nКопіюй і поширюй — більше переходів = більше анонімок! 💥",
        'qr_caption': "📱 <b>Твій ексклюзивний QR-код</b> 🌟\n\nСкануй або покажи друзям — миттєвий доступ! ⚡\n\n<i>Посилання: {link}</i>",
        'profile': "📌 <b>Твій профіль Anony SMS</b> 👤✨\n\n"
                   "📛 <b>Ім'я:</b> {name}\n🌀 <b>Username:</b> {username}\n🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                   "📊 <b>Статистика:</b> 🔥\n💌 Отримано: <b><code>{received}</code></b>\n📤 Надіслано: <b><code>{sent}</code></b>\n👀 Переходів: <b><code>{clicks}</code></b>\n\n"
                   "🔗 Посилання: {link}\n\nТи — зірка анонімності! ⭐❤️",
        'support_entry': "📩 <b>Служба підтримки Anony SMS</b> 👨‍💻✨\n\nМи завжди на зв'язку! ❤️\n\nНапиши питання, надішли фото, відео чи голосове — відповімо швидко! 🌟",
        'support_sent': "✅ <b>Звернення надіслано!</b> 🎉\n\nМи отримали повідомлення і скоро відповімо. Дякуємо, що ти з нами! ❤️",
        'support_reply': "✉️ <b>Відповідь від підтримки Anony SMS</b> 👨‍💻\n\nЯкщо не по вашому питанню — проігноруйте.",
        'anon_msg': "🕶️ <b>АНОНІМНЕ ПОВІДОМЛЕННЯ!</b> 🔥✨",
        'sent_anon': "✅ <b>Повідомлення надіслано анонімно!</b> 🎉\n\nОдержувач бачить його. Анонімність 100% 🕶️",
        'help': "ℹ️ <b>Як працює Anony SMS?</b>\n\n"
                "1️⃣ Отримай посилання або QR-код\n2️⃣ Поширюй його\n3️⃣ Отримуй анонімні повідомлення\n4️⃣ Відповідай одним натисканням\n\n"
                "🚀 Все просто і безпечно!\n\nЗміна мови: /lang",
        'telegram_info': "🏆 <b>Telegram — найкращий месенджер у світі!</b> 🚀\n\n"
                         "🔹 <b>Simple</b>\nTelegram is so simple you already know how to use it.\n\n"
                         "🔹 <b>Private</b>\nПовідомлення шифруються і можуть зникати.\n\n"
                         "🔹 <b>Synced</b>\nДоступ з будь-яких пристроїв.\n\n"
                         "🔹 <b>Fast</b>\nНайшвидша доставка.\n\n"
                         "🔹 <b>Powerful</b>\nБез лімітів на медіа та чати.\n\n"
                         "🔹 <b>Open</b>\nВідкритий API та код.\n\n"
                         "🔹 <b>Secure</b>\nЗахист від хакерів.\n\n"
                         "🔹 <b>Social</b>\nГрупи до 200,000 учасників.\n\n"
                         "🔹 <b>Expressive</b>\nПовна кастомізація.\n\n"
                         "❤️ Anony SMS працює на Telegram — твоя приватність захищена!",
        'settings': "⚙️ <b>Налаштування приватності</b> 🔒\n\nКонтролюй прийом повідомлень.",
        'receive_on': "🔔 <b>Прийом повідомлень увімкнено!</b> ✅\n\nЧекаємо на нові анонімки! 🔥❤️",
        'receive_off': "🔕 <b>Прийом повідомлень вимкнено!</b> 🔒\n\nТиша і спокій. Увімкни, коли захочеш!",
        'cancel': "❌ <b>Дію скасовано</b>\n\nПовертаємося в меню 🏠",
        'lang_changed': "✅ <b>Мову змінено!</b> 🌍✨",
        'buttons': {
            'my_link': "📩 Моє посилання",
            'qr': "📱 QR-код",
            'settings': "⚙️ Налаштування",
            'profile': "📌 Профіль",
            'support': "📩 Підтримка",
            'help': "ℹ️ Допомога",
            'telegram': "ℹ️ Про Telegram",
            'admin': "🔧 Адмін-панель",
            'back': "⬅️ Назад в меню"
        }
    },
    'en': {
        'welcome': "🎉 <b>Welcome to Anony SMS!</b> 🎉\n\n"
                   "🔥 Send & receive messages <b>completely anonymously</b>! 🕶️\n\n"
                   "🔗 <b>Your personal link:</b>\n<code>{link}</code>\n\n"
                   "📢 Share it — get secret confessions and messages! 💌❤️\n"
                   "Ready for anonymity? Tap below! 🚀✨",
        'my_link': "🔗 <b>Your anonymous link</b> 🔥\n\n<code>{link}</code>\n\nShare everywhere — more clicks = more messages! 💥",
        'qr_caption': "📱 <b>Your exclusive QR code</b> 🌟\n\nScan or show friends — instant access! ⚡\n\n<i>Link: {link}</i>",
        'profile': "📌 <b>Your Anony SMS profile</b> 👤✨\n\n"
                   "📛 <b>Name:</b> {name}\n🌀 <b>Username:</b> {username}\n🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                   "📊 <b>Stats:</b> 🔥\n💌 Received: <b><code>{received}</code></b>\n📤 Sent: <b><code>{sent}</code></b>\n👀 Clicks: <b><code>{clicks}</code></b>\n\n"
                   "🔗 Link: {link}\n\nYou're an anonymity star! ⭐❤️",
        'support_entry': "📩 <b>Anony SMS Support</b> 👨‍💻✨\n\nWe're always here! ❤️\n\nSend question, photo, video or voice — fast reply! 🌟",
        'support_sent': "✅ <b>Message sent!</b> 🎉\n\nWe'll reply soon. Thank you for being with us! ❤️",
        'support_reply': "✉️ <b>Reply from Anony SMS support</b> 👨‍💻\n\nIf not related — just ignore.",
        'anon_msg': "🕶️ <b>ANONYMOUS MESSAGE!</b> 🔥✨",
        'sent_anon': "✅ <b>Message sent anonymously!</b> 🎉\n\nRecipient sees it. 100% anonymous 🕶️",
        'help': "ℹ️ <b>How Anony SMS works</b>\n\n"
                "1️⃣ Get your link or QR\n2️⃣ Share it\n3️⃣ Receive anonymous messages\n4️⃣ Reply with one tap\n\n"
                "🚀 Simple & secure!\n\nChange language: /lang",
        'telegram_info': "🏆 <b>Telegram — the best messenger ever!</b> 🚀\n\n"
                         "🔹 <b>Simple</b>\nTelegram is so simple you already know how to use it.\n\n"
                         "🔹 <b>Private</b>\nHeavily encrypted, self-destructing messages.\n\n"
                         "🔹 <b>Synced</b>\nAccess from any device.\n\n"
                         "🔹 <b>Fast</b>\nFastest delivery.\n\n"
                         "🔹 <b>Powerful</b>\nNo limits on media or chats.\n\n"
                         "🔹 <b>Open</b>\nOpen API and source code.\n\n"
                         "🔹 <b>Secure</b>\nProtected from hackers.\n\n"
                         "🔹 <b>Social</b>\nGroups up to 200,000 members.\n\n"
                         "🔹 <b>Expressive</b>\nFully customizable.\n\n"
                         "❤️ Anony SMS runs on Telegram — your privacy is safe!",
        'settings': "⚙️ <b>Privacy settings</b> 🔒\n\nControl anonymous message receiving.",
        'receive_on': "🔔 <b>Receiving enabled!</b> ✅\n\nReady for new anonymous messages! 🔥❤️",
        'receive_off': "🔕 <b>Receiving disabled!</b> 🔒\n\nPeace and quiet. Enable when ready!",
        'cancel': "❌ <b>Action cancelled</b>\n\nBack to main menu 🏠",
        'lang_changed': "✅ <b>Language changed!</b> 🌍✨",
        'buttons': {
            'my_link': "📩 My link",
            'qr': "📱 QR code",
            'settings': "⚙️ Settings",
            'profile': "📌 Profile",
            'support': "📩 Support",
            'help': "ℹ️ Help",
            'telegram': "ℹ️ About Telegram",
            'admin': "🔧 Admin panel",
            'back': "⬅️ Back to menu"
        }
    }
}

def t(user_id, key, **kwargs):
    lang = user_language.get(user_id, 'ru')
    return TEXTS[lang].get(key, TEXTS['ru'][key]).format(**kwargs)

def btn(user_id, key):
    lang = user_language.get(user_id, 'ru')
    return TEXTS[lang]['buttons'][key]

# ====== Клавиатуры ======
def main_menu(user_id, is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(btn(user_id, 'my_link'), btn(user_id, 'qr'))
    markup.add(btn(user_id, 'settings'))
    markup.add(btn(user_id, 'profile'))
    markup.add(btn(user_id, 'support'), btn(user_id, 'help'))
    markup.add(btn(user_id, 'telegram'))
    if is_admin:
        markup.add(btn(user_id, 'admin'))
    return markup

settings_menu = ReplyKeyboardMarkup(resize_keyboard=True)
settings_menu.add(KeyboardButton("🔔 Включить приём"), KeyboardButton("🔕 Отключить приём"))
settings_menu.add(KeyboardButton(btn(0, 'back')))  # btn(0, ...) — всегда ru для универсальной кнопки

cancel_menu = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_menu.add(KeyboardButton("❌ Отмена"))

admin_menu = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
admin_menu.add(KeyboardButton("📊 Статистика бота"), KeyboardButton("📨 Рассылка"))
admin_menu.add(KeyboardButton("🔥 Топ-10 пользователей"))
admin_menu.add(KeyboardButton("🚫 Заблокировать"), KeyboardButton("✅ Разблокировать"))
admin_menu.add(KeyboardButton("⬅️ Назад в главное меню"))

# ====== Утилиты ======
def update_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT OR REPLACE INTO users (user_id, username, first_name, last_active) VALUES (?, ?, ?, ?)""",
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
    c.execute("SELECT username, first_name, link_clicks, messages_received, messages_sent FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        username = f"@{row[0]}" if row[0] else "<i>hidden 😶</i>"
        name = row[1] or "Anonymous 🕶️"
        clicks, received, sent = row[2] or 0, row[3] or 0, row[4] or 0
        return name, username, clicks, received, sent
    return "Anonymous 🕶️", "<i>hidden 😶</i>", 0, 0, 0

# ====== Обработчики ======
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        bot.send_message(user_id, "🚫 <b>Access restricted</b> 🔒")
        return

    update_user(message.from_user)
    is_admin = user_id == ADMIN_ID

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")
        if time.time() - last_message_time.get(user_id, 0) < ANTISPAM_INTERVAL:
            bot.send_message(user_id, "⏳ Please wait a bit before sending.")
            return
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.send_message(user_id, "🕶️ <b>Ready to send anonymous message?</b> 🔥", reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id, t(user_id, 'welcome', link=link), reply_markup=main_menu(user_id, is_admin))

@bot.message_handler(commands=['lang'])
def lang_command(message):
    user_id = message.from_user.id
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    bot.send_message(user_id, "🌍 <b>Choose language:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def lang_callback(call):
    user_id = call.from_user.id
    lang = call.data.split('_')[1]
    user_language[user_id] = lang
    bot.answer_callback_query(call.id)
    bot.edit_message_text(chat_id=user_id, message_id=call.message.message_id, text=t(user_id, 'lang_changed'))
    bot.send_message(user_id, "🏠 Menu updated!", reply_markup=main_menu(user_id, user_id == ADMIN_ID))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_all(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return

    is_admin = user_id == ADMIN_ID
    text = message.text or message.caption or ""

    update_user(message.from_user)

    # Отмена
    if text == "❌ Отмена" or text == "❌ Cancel":
        waiting_message.pop(user_id, None)
        admin_reply_mode.pop(user_id, None)
        bot.send_message(user_id, t(user_id, 'cancel'), reply_markup=main_menu(user_id, is_admin))
        return

    # О Telegram
    if text in [btn(user_id, 'telegram') for _ in ['']]:  # динамическая проверка
        if text == btn(user_id, 'telegram'):
            bot.send_message(user_id, t(user_id, 'telegram_info'), reply_markup=main_menu(user_id, is_admin))
            return

    # Поддержка
    if text == btn(user_id, 'support'):
        bot.send_message(user_id, t(user_id, 'support_entry'), reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    if waiting_message.get(user_id) == "support":
        name, username, _, received, sent = get_user_info(user_id)
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Reply", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Ignore", callback_data=f"sup_ignore_{user_id}")
        )
        info = f"📩 <b>New support request</b>\n\n👤 {name}\n🌀 {username}\n🆔 <code>{user_id}</code>\n💌 Rec: {received} | Sent: {sent}"
        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, info, reply_to_message_id=forwarded.message_id, reply_markup=kb)
        bot.send_message(user_id, t(user_id, 'support_sent'), reply_markup=main_menu(user_id, is_admin))
        waiting_message.pop(user_id, None)
        return

    # Админ: ответ в поддержку
    if is_admin and user_id in admin_reply_mode:
        target_id = admin_reply_mode.pop(user_id)
        try:
            if message.content_type == 'text':
                bot.send_message(target_id, message.text)
            else:
                bot.copy_message(target_id, user_id, message.message_id)
            bot.send_message(target_id, t(target_id, 'support_reply'))
            bot.send_message(user_id, "✅ Reply sent!", reply_markup=admin_menu)
        except:
            bot.send_message(user_id, "❌ Delivery error", reply_markup=admin_menu)
        return

    # Анонимная отправка по ссылке
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)
        increment_stat(target_id, "messages_received")
        increment_stat(user_id, "messages_sent")

        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Reply anonymously", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🚫 Ignore", callback_data="ignore")
        )

        try:
            if message.content_type == 'text':
                bot.send_message(target_id, t(target_id, 'anon_msg') + ("\n\n" + text if text else ""), reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id)
                bot.send_message(target_id, t(target_id, 'anon_msg'), reply_to_message_id=copied.message_id, reply_markup=markup)
        except:
            bot.send_message(user_id, "❌ Delivery failed")
            return

        bot.send_message(user_id, t(user_id, 'sent_anon'), reply_markup=main_menu(user_id, is_admin))
        return

    # Основные команды
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
        name, username, clicks, received, sent = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'profile', name=name, username=username, user_id=user_id, received=received, sent=sent, clicks=clicks, link=link),
                         reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'settings'):
        bot.send_message(user_id, t(user_id, 'settings'), reply_markup=settings_menu)

    elif text in ["🔔 Включить приём", "🔕 Отключить приём"]:
        status_on = "Включить" in text
        bot.send_message(user_id, t(user_id, 'receive_on' if status_on else 'receive_off'), reply_markup=main_menu(user_id, is_admin))

    elif text == btn(user_id, 'help'):
        bot.send_message(user_id, t(user_id, 'help'), reply_markup=main_menu(user_id, is_admin))

    # Админ команды
    elif is_admin and text == "⬅️ Назад в главное меню":
        bot.send_message(user_id, "🏠 Main menu", reply_markup=main_menu(user_id, True))

    elif is_admin and text == "🔥 Топ-10 пользователей":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, messages_received, link_clicks FROM users ORDER BY messages_received DESC, link_clicks DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.send_message(user_id, "Top-10 is empty")
            return
        top = "🏆 <b>Top-10 Users</b>\n\n"
        for i, (uid, rec, clk) in enumerate(rows, 1):
            name, _, _, _, _ = get_user_info(uid)
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            top += f"{medal} <b>{name}</b> — 💌 {rec} | 👀 {clk}\n"
        bot.send_message(user_id, top, reply_markup=admin_menu)

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
        bot.send_message(user_id, "🕶️ <b>Write anonymous reply</b> 🔥", reply_markup=cancel_menu)

    elif data.startswith("sup_reply_") and user_id == ADMIN_ID:
        target_id = int(data.split("_")[-1])
        admin_reply_mode[ADMIN_ID] = target_id
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        name, _, _, _, _ = get_user_info(target_id)
        bot.send_message(ADMIN_ID, f"✉️ Send reply to <b>{name}</b> (<code>{target_id}</code>)", reply_markup=cancel_menu)

    elif data.startswith("sup_ignore_") and user_id == ADMIN_ID:
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)

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
