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
waiting_message = {}        # для анонимки по ссылке и поддержки
admin_reply_mode = {}       # админ отвечает в поддержку
blocked_users = set()
last_message_time = {}
ANTISPAM_INTERVAL = 30
user_language = {}          # user_id -> 'ru' / 'uk' / 'en'

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
                   "🔗 <b>Твоя личная ссылка:</b>\n"
                   "<code>{link}</code>\n\n"
                   "📢 Распространи её среди друзей, в сторис, био — и получай тайные признания, вопросы и секреты! 💌❤️\n"
                   "Готов к магии анонимности? Жми кнопки ниже и начинай! 🚀✨",
        'my_link': "🔗 <b>Твоя личная анонимная ссылка</b> 🔥\n\n"
                   "<code>{link}</code>\n\n"
                   "Копируй и распространяй везде — чем больше переходов, тем больше анонимок ты получишь! 💥",
        'qr_caption': "📱 <b>Эксклюзивный QR-код Anony SMS</b> 🌟\n\n"
                      "Сканируй сам или покажи друзьям — мгновенный переход к анонимному общению! ⚡\n\n"
                      "<i>Ссылка внутри: {link}</i>",
        'profile': "📌 <b>Твой крутой профиль Anony SMS</b> 👤✨\n\n"
                   "📛 <b>Имя:</b> {name}\n"
                   "🌀 <b>Username:</b> {username}\n"
                   "🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                   "📊 <b>Твоя статистика — огонь!</b> 🔥\n"
                   "💌 Получено анонимок: <b><code>{received}</code></b>\n"
                   "📤 Отправлено анонимок: <b><code>{sent}</code></b>\n"
                   "👀 Переходов по ссылке: <b><code>{clicks}</code></b>\n\n"
                   "🔗 Твоя ссылка: {link}\n\n"
                   "Ты — настоящая звезда анонимного мира! Продолжай сиять! ⭐❤️",
        'support_entry': "📩 <b>Служба поддержки Anony SMS</b> 👨‍💻✨\n\n"
                         "Мы всегда на связи и готовы помочь в любой ситуации! ❤️\n\n"
                         "🔥 Напиши свой вопрос\n"
                         "📸 Пришли скриншот\n"
                         "🎥 Отправь видео\n"
                         "🎤 Запиши голосовое\n\n"
                         "Ответим максимально быстро и подробно! Ты — важная часть нашего сообщества! 🌟",
        'support_sent': "✅ <b>Обращение успешно отправлено!</b> 🎉\n\n"
                        "Мы получили всё: текст, фото, видео, голосовое — всё в порядке! 👍\n"
                        "Наша команда уже занимается твоим вопросом 💼\n\n"
                        "Ответим максимально быстро и подробно! Спасибо, что ты с нами — ты лучший! ❤️🌟",
        'support_reply': "✉️ <b>Ответ от оператора поддержки Anony SMS</b> 👨‍💻✨\n\n"
                         "Если это сообщение пришло по ошибке — просто проигнорируйте его.\n"
                         "По всем вопросам всегда пишите в «📩 Поддержка» — мы на связи 24/7! ❤️🚀",
        'anon_msg': "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ ПРИШЛО!</b> 🔥✨",
        'sent_anon': "✅ <b>Сообщение успешно отправлено анонимно!</b> 🎉\n\n"
                     "Получатель уже видит его! Твоя анонимность сохранена на 100% 🕶️\n"
                     "Продолжай — это невероятно круто! 💥❤️",
        'help': "ℹ️ <b>Как работает Anony SMS?</b> ❓\n\n"
                "1️⃣ Получи свою уникальную ссылку или QR-код\n"
                "2️⃣ Распространи её в сторис, био, чатах, среди друзей\n"
                "3️⃣ Люди начнут отправлять тебе анонимные сообщения!\n"
                "4️⃣ Отвечай анонимно одним нажатием\n\n"
                "🚀 <b>Всё просто, быстро и 100% анонимно!</b>\n\n"
                "Тайны, признания, вопросы — всё здесь! ✨❤️\n"
                "Смена языка: /lang",
        'telegram_info': "🏆 <b>Telegram Messenger — лучший мессенджер в мире!</b> 🚀\n\n"
                         "🔹 <b>Simple</b>\nTelegram is so simple you already know how to use it.\n\n"
                         "🔹 <b>Private</b>\nTelegram messages are heavily encrypted and can self-destruct.\n\n"
                         "🔹 <b>Synced</b>\nTelegram lets you access your chats from multiple devices.\n\n"
                         "🔹 <b>Fast</b>\nTelegram delivers messages faster than any other application.\n\n"
                         "🔹 <b>Powerful</b>\nTelegram has no limits on the size of your media and chats.\n\n"
                         "🔹 <b>Open</b>\nTelegram has an open API and source code free for everyone.\n\n"
                         "🔹 <b>Secure</b>\nTelegram keeps your messages safe from hacker attacks.\n\n"
                         "🔹 <b>Social</b>\nTelegram groups can hold up to 200,000 members.\n\n"
                         "🔹 <b>Expressive</b>\nTelegram lets you completely customize your messenger.\n\n"
                         "❤️ Anony SMS работает на платформе Telegram — твои сообщения в полной безопасности и приватности!",
        'settings': "⚙️ <b>Настройки приватности Anony SMS</b> 🔒\n\n"
                    "Ты полностью контролируешь приём сообщений!",
        'receive_on': "🔔 <b>Приём анонимных сообщений ВКЛЮЧЁН!</b> ✅\n\n"
                      "Теперь ты открыт для всех анонимок! Жди интересных сообщений! 🔥❤️",
        'receive_off': "🔕 <b>Приём анонимных сообщений ОТКЛЮЧЁН!</b> 🔒\n\n"
                       "Полная тишина и безопасность. Включи обратно, когда будешь готов! 😊",
        'cancel': "❌ <b>Действие отменено</b>\n\nВозвращаемся в главное меню! 🏠",
        'lang_changed': "✅ <b>Язык успешно изменён!</b> 🌍✨",
    },
    'uk': {
        'welcome': "🎉 <b>Ласкаво просимо до Anony SMS!</b> 🎉\n\n"
                   "🔥 Тут ти можеш <b>отримувати та надсилати повідомлення повністю анонімно</b>! 🕶️\n\n"
                   "🔗 <b>Твоє особисте посилання:</b>\n"
                   "<code>{link}</code>\n\n"
                   "📢 Поширюй його серед друзів — і отримуй таємні зізнання, питання та секрети! 💌❤️\n"
                   "Готовий до магії анонімності? Тисни кнопки нижче і починай! 🚀✨",
        'my_link': "🔗 <b>Твоє особисте анонімне посилання</b> 🔥\n\n"
                   "<code>{link}</code>\n\n"
                   "Копіюй і поширюй всюди — чим більше переходів, тим більше анонімок ти отримаєш! 💥",
        'qr_caption': "📱 <b>Ексклюзивний QR-код Anony SMS</b> 🌟\n\n"
                      "Скануй сам або покажи друзям — миттєвий доступ до анонімного спілкування! ⚡\n\n"
                      "<i>Посилання всередині: {link}</i>",
        'profile': "📌 <b>Твій крутий профіль Anony SMS</b> 👤✨\n\n"
                   "📛 <b>Ім'я:</b> {name}\n"
                   "🌀 <b>Username:</b> {username}\n"
                   "🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                   "📊 <b>Твоя статистика — вогонь!</b> 🔥\n"
                   "💌 Отримано анонімок: <b><code>{received}</code></b>\n"
                   "📤 Надіслано анонімок: <b><code>{sent}</code></b>\n"
                   "👀 Переходів за посиланням: <b><code>{clicks}</code></b>\n\n"
                   "🔗 Твоє посилання: {link}\n\n"
                   "Ти — справжня зірка анонімного світу! Продовжуй сяяти! ⭐❤️",
        'support_entry': "📩 <b>Служба підтримки Anony SMS</b> 👨‍💻✨\n\n"
                         "Ми завжди на зв'язку і готові допомогти! ❤️\n\n"
                         "🔥 Напиши своє питання\n"
                         "📸 Надішли скріншот\n"
                         "🎥 Відправ відео\n"
                         "🎤 Запиши голосове\n\n"
                         "Відповімо максимально швидко та детально! Ти — важлива частина спільноти! 🌟",
        'support_sent': "✅ <b>Звернення надіслано!</b> 🎉\n\n"
                        "Ми отримали все — текст, фото, відео, голосове! 👍\n"
                        "Команда вже працює над твоїм питанням 💼\n\n"
                        "Відповімо швидко та детально! Дякуємо, що ти з нами — ти найкращий! ❤️🌟",
        'support_reply': "✉️ <b>Відповідь від оператора підтримки Anony SMS</b> 👨‍💻✨\n\n"
                         "Якщо прийшло помилково — просто проігноруйте.\n"
                         "За питаннями — в «📩 Підтримка»! ❤️🚀",
        'anon_msg': "🕶️ <b>АНОНІМНЕ ПОВІДОМЛЕННЯ ПРИЙШЛО!</b> 🔥✨",
        'sent_anon': "✅ <b>Повідомлення надіслано анонімно!</b> 🎉\n\n"
                     "Одержувач вже бачить його! Анонімність 100% 🕶️\n"
                     "Продовжуй — це круто! 💥❤️",
        'help': "ℹ️ <b>Як працює Anony SMS?</b> ❓\n\n"
                "1️⃣ Отримай посилання або QR-код\n"
                "2️⃣ Поширюй його\n"
                "3️⃣ Отримуй анонімні повідомлення\n"
                "4️⃣ Відповідай анонімно одним натисканням\n\n"
                "🚀 <b>Просто, швидко і 100% анонімно!</b>\n\n"
                "Зміна мови: /lang",
        'telegram_info': "🏆 <b>Telegram Messenger — найкращий месенджер у світі!</b> 🚀\n\n"
                         "🔹 <b>Simple</b>\nTelegram is so simple you already know how to use it.\n\n"
                         "🔹 <b>Private</b>\nTelegram messages are heavily encrypted and can self-destruct.\n\n"
                         "🔹 <b>Synced</b>\nTelegram lets you access your chats from multiple devices.\n\n"
                         "🔹 <b>Fast</b>\nTelegram delivers messages faster than any other application.\n\n"
                         "🔹 <b>Powerful</b>\nTelegram has no limits on the size of your media and chats.\n\n"
                         "🔹 <b>Open</b>\nTelegram has an open API and source code free for everyone.\n\n"
                         "🔹 <b>Secure</b>\nTelegram keeps your messages safe from hacker attacks.\n\n"
                         "🔹 <b>Social</b>\nTelegram groups can hold up to 200,000 members.\n\n"
                         "🔹 <b>Expressive</b>\nTelegram lets you completely customize your messenger.\n\n"
                         "❤️ Anony SMS працює на платформі Telegram — твої повідомлення в повній безпеці!",
        'settings': "⚙️ <b>Налаштування приватності</b> 🔒\n\n"
                    "Ти контролюєш прийом повідомлень!",
        'receive_on': "🔔 <b>Прийом анонімних повідомлень УВІМКНЕНО!</b> ✅\n\n"
                      "Чекай на цікаві анонімки! 🔥❤️",
        'receive_off': "🔕 <b>Прийом анонімних повідомлень ВИМКНЕНО!</b> 🔒\n\n"
                       "Тиша і безпека. Увімкни, коли захочеш! 😊",
        'cancel': "❌ <b>Дію скасовано</b>\n\nПовертаємося в меню! 🏠",
        'lang_changed': "✅ <b>Мову змінено!</b> 🌍✨",
    },
    'en': {
        'welcome': "🎉 <b>Welcome to Anony SMS!</b> 🎉\n\n"
                   "🔥 Receive and send messages <b>completely anonymously</b>! 🕶️\n\n"
                   "🔗 <b>Your personal link:</b>\n"
                   "<code>{link}</code>\n\n"
                   "📢 Share it with friends — get secret confessions and questions! 💌❤️\n"
                   "Ready for anonymity magic? Start now! 🚀✨",
        'my_link': "🔗 <b>Your personal anonymous link</b> 🔥\n\n"
                   "<code>{link}</code>\n\n"
                   "Share everywhere — more clicks = more anonymous messages! 💥",
        'qr_caption': "📱 <b>Exclusive Anony SMS QR code</b> 🌟\n\n"
                      "Scan or show to friends — instant anonymous chat! ⚡\n\n"
                      "<i>Link: {link}</i>",
        'profile': "📌 <b>Your awesome profile</b> 👤✨\n\n"
                   "📛 <b>Name:</b> {name}\n"
                   "🌀 <b>Username:</b> {username}\n"
                   "🆔 <b>ID:</b> <code>{user_id}</code>\n\n"
                   "📊 <b>Your stats are fire!</b> 🔥\n"
                   "💌 Received: <b><code>{received}</code></b>\n"
                   "📤 Sent: <b><code>{sent}</code></b>\n"
                   "👀 Clicks: <b><code>{clicks}</code></b>\n\n"
                   "🔗 Your link: {link}\n\n"
                   "You're a star of anonymity! Keep shining! ⭐❤️",
        'support_entry': "📩 <b>Anony SMS Support</b> 👨‍💻✨\n\n"
                         "We're always here to help! ❤️\n\n"
                         "🔥 Write your question\n"
                         "📸 Send screenshot\n"
                         "🎥 Send video\n"
                         "🎤 Record voice\n\n"
                         "Fast and detailed reply! You're important to us! 🌟",
        'support_sent': "✅ <b>Message sent to support!</b> 🎉\n\n"
                        "We got everything — text, photo, video, voice! 👍\n"
                        "Our team is on it 💼\n\n"
                        "Fast reply coming! Thanks for being with us — you're the best! ❤️🌟",
        'support_reply': "✉️ <b>Reply from Anony SMS support</b> 👨‍💻✨\n\n"
                         "If mistaken — ignore. For questions — write to «Support»! ❤️🚀",
        'anon_msg': "🕶️ <b>ANONYMOUS MESSAGE ARRIVED!</b> 🔥✨",
        'sent_anon': "✅ <b>Message sent anonymously!</b> 🎉\n\n"
                     "Recipient sees it! Anonymity 100% 🕶️\n"
                     "Keep going — it's awesome! 💥❤️",
        'help': "ℹ️ <b>How Anony SMS works</b> ❓\n\n"
                "1️⃣ Get your link or QR code\n"
                "2️⃣ Share it\n"
                "3️⃣ Receive anonymous messages\n"
                "4️⃣ Reply anonymously with one tap\n\n"
                "🚀 <b>Simple, fast, 100% anonymous!</b>\n\n"
                "Change language: /lang",
        'telegram_info': "🏆 <b>Telegram Messenger — the best messenger in the world!</b> 🚀\n\n"
                         "🔹 <b>Simple</b>\nTelegram is so simple you already know how to use it.\n\n"
                         "🔹 <b>Private</b>\nTelegram messages are heavily encrypted and can self-destruct.\n\n"
                         "🔹 <b>Synced</b>\nTelegram lets you access your chats from multiple devices.\n\n"
                         "🔹 <b>Fast</b>\nTelegram delivers messages faster than any other application.\n\n"
                         "🔹 <b>Powerful</b>\nTelegram has no limits on the size of your media and chats.\n\n"
                         "🔹 <b>Open</b>\nTelegram has an open API and source code free for everyone.\n\n"
                         "🔹 <b>Secure</b>\nTelegram keeps your messages safe from hacker attacks.\n\n"
                         "🔹 <b>Social</b>\nTelegram groups can hold up to 200,000 members.\n\n"
                         "🔹 <b>Expressive</b>\nTelegram lets you completely customize your messenger.\n\n"
                         "❤️ Anony SMS runs on Telegram platform — your messages are completely safe and private!",
        'settings': "⚙️ <b>Privacy settings</b> 🔒\n\n"
                    "You control message receiving!",
        'receive_on': "🔔 <b>Receiving anonymous messages ENABLED!</b> ✅\n\n"
                      "Open to all anonymous messages! 🔥❤️",
        'receive_off': "🔕 <b>Receiving anonymous messages DISABLED!</b> 🔒\n\n"
                       "Silence and safety. Enable when ready! 😊",
        'cancel': "❌ <b>Action cancelled</b>\n\nBack to main menu! 🏠",
        'lang_changed': "✅ <b>Language changed!</b> 🌍✨",
    }
}

def t(user_id, key, **kwargs):
    lang = user_language.get(user_id, 'ru')
    return TEXTS[lang].get(key, TEXTS['ru'][key]).format(**kwargs)

# ====== Клавиатуры ======
def main_menu(user_id, is_admin=False):
    lang = user_language.get(user_id, 'ru')
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("📩 Моя ссылка" if lang in ['ru', 'uk'] else "📩 My link"),
               KeyboardButton("📱 QR-код" if lang in ['ru', 'uk'] else "📱 QR code"))
    markup.row(KeyboardButton("⚙️ Настройки" if lang in ['ru', 'uk'] else "⚙️ Settings"))
    markup.row(KeyboardButton("📌 Профиль" if lang in ['ru', 'uk'] else "📌 Profile"))
    markup.row(KeyboardButton("📩 Поддержка" if lang == 'ru' else "📩 Підтримка" if lang == 'uk' else "📩 Support"),
               KeyboardButton("ℹ️ Помощь" if lang == 'ru' else "ℹ️ Допомога" if lang == 'uk' else "ℹ️ Help"))
    markup.row(KeyboardButton("ℹ️ О Telegram" if lang == 'ru' else "ℹ️ Про Telegram" if lang == 'uk' else "ℹ️ About Telegram"))
    if is_admin:
        markup.add(KeyboardButton("🔧 Админ-панель" if lang == 'ru' else "🔧 Адмін-панель" if lang == 'uk' else "🔧 Admin panel"))
    return markup

settings_menu = ReplyKeyboardMarkup(resize_keyboard=True)
settings_menu.row(KeyboardButton("🔕 Отключить приём"), KeyboardButton("🔔 Включить приём"))
settings_menu.add(KeyboardButton("⬅️ Назад в меню"))

cancel_menu = ReplyKeyboardMarkup(resize_keyboard=True)
cancel_menu.add(KeyboardButton("❌ Отмена"))

admin_menu = ReplyKeyboardMarkup(resize_keyboard=True)
admin_menu.row(KeyboardButton("📊 Статистика бота"), KeyboardButton("📨 Рассылка"))
admin_menu.row(KeyboardButton("🔥 Топ-10 пользователей"))
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
    c.execute("SELECT username, first_name, link_clicks, messages_received, messages_sent FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        username = f"@{row[0]}" if row[0] else "<i>скрыт 😶</i>"
        name = row[1] or "Аноним 🕶️"
        clicks = row[2] or 0
        received = row[3] or 0
        sent = row[4] or 0
        return name, username, clicks, received, sent
    return "Аноним 🕶️", "<i>скрыт 😶</i>", 0, 0, 0

# ====== Команда смены языка ======
@bot.message_handler(commands=['lang'])
def lang_command(message):
    user_id = message.from_user.id
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇺🇦 Українська", callback_data="lang_uk"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    bot.send_message(user_id, "🌍 <b>Выберите язык / Оберіть мову / Choose language:</b>", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith('lang_'))
def lang_callback(call):
    user_id = call.from_user.id
    lang = call.data.split('_')[1]
    user_language[user_id] = lang
    bot.answer_callback_query(call.id)
    bot.edit_message_text(chat_id=user_id, message_id=call.message.message_id, text=t(user_id, 'lang_changed'))
    bot.send_message(user_id, "🏠 Меню обновлено!", reply_markup=main_menu(user_id, user_id == ADMIN_ID))

# ====== Основные обработчики ======
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        bot.send_message(user_id, "🚫 <b>Доступ ограничен</b> 🔒")
        return

    update_user(message.from_user)
    is_admin = user_id == ADMIN_ID

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        if time.time() - last_message_time.get(user_id, 0) < ANTISPAM_INTERVAL:
            bot.send_message(user_id, "⏳ Подожди немного перед отправкой.")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.send_message(user_id, "🕶️ <b>Готов отправить анонимное сообщение?</b> 🔥", reply_markup=cancel_menu)
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

    # О Telegram
    elif text in ["ℹ️ О Telegram", "ℹ️ Про Telegram", "ℹ️ About Telegram"]:
        bot.send_message(user_id, t(user_id, 'telegram_info'), reply_markup=main_menu(user_id, is_admin))
        return

    # Поддержка
    elif text in ["📩 Поддержка", "📩 Підтримка", "📩 Support"]:
        bot.send_message(user_id, t(user_id, 'support_entry'), reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    if waiting_message.get(user_id) == "support":
        name, username, _, received, sent = get_user_info(user_id)
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Ответить", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data=f"sup_ignore_{user_id}")
        )
        info = f"📩 <b>Новое обращение в поддержку</b>\n\n👤 {name}\n🌀 {username}\n🆔 <code>{user_id}</code>\n💌 Получено: {received} | Отправлено: {sent}"
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
                sent = bot.send_message(target_id, message.text)
            else:
                sent = bot.copy_message(target_id, user_id, message.message_id)
            bot.send_message(target_id, t(target_id, 'support_reply'), reply_to_message_id=sent.message_id)
            bot.send_message(user_id, "✅ Ответ отправлен!", reply_markup=admin_menu)
        except:
            bot.send_message(user_id, "❌ Ошибка доставки", reply_markup=admin_menu)
        return

    # Анонимная отправка по ссылке
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)
        increment_stat(target_id, "messages_received")
        increment_stat(user_id, "messages_sent")

        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Ответить анонимно", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data="ignore")
        )

        try:
            if message.content_type == 'text':
                bot.send_message(target_id, t(target_id, 'anon_msg') + ("\n\n" + text if text else ""), reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id)
                bot.send_message(target_id, t(target_id, 'anon_msg'), reply_to_message_id=copied.message_id, reply_markup=markup)
        except:
            bot.send_message(user_id, "❌ Не удалось доставить")
            return

        bot.send_message(user_id, t(user_id, 'sent_anon'), reply_markup=main_menu(user_id, is_admin))
        return

    # Основные кнопки
    if text in ["📩 Моя ссылка", "📩 My link"]:
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'my_link', link=link), reply_markup=main_menu(user_id, is_admin))

    elif text in ["📱 QR-код", "📱 QR code"]:
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

    elif text in ["📌 Профиль", "📌 Profile"]:
        name, username, clicks, received, sent = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'profile', name=name, username=username, user_id=user_id,
                                    received=received, sent=sent, clicks=clicks, link=link),
                         reply_markup=main_menu(user_id, is_admin))

    elif text in ["⚙️ Настройки", "⚙️ Settings"]:
        bot.send_message(user_id, t(user_id, 'settings'), reply_markup=settings_menu)

    elif text in ["🔕 Отключить приём", "🔔 Включить приём"]:
        status = 'off' if "Отключить" in text else 'on'
        bot.send_message(user_id, t(user_id, 'receive_off' if status == 'off' else 'receive_on'),
                         reply_markup=main_menu(user_id, is_admin))

    elif text in ["ℹ️ Помощь", "ℹ️ Допомога", "ℹ️ Help"]:
        bot.send_message(user_id, t(user_id, 'help'), reply_markup=main_menu(user_id, is_admin))

    elif is_admin and text == "⬅️ Назад в главное меню":
        bot.send_message(user_id, "🏠 Главное меню", reply_markup=main_menu(user_id, True))

    elif is_admin and text == "🔥 Топ-10 пользователей":
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, messages_received, link_clicks FROM users ORDER BY messages_received DESC, link_clicks DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.send_message(user_id, "ТОП-10 пока пуст")
            return
        top_text = "🏆 <b>ТОП-10 пользователей</b>\n\n"
        for i, (uid, rec, clk) in enumerate(rows, 1):
            name, _, _, _, _ = get_user_info(uid)
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            top_text += f"{medal} <b>{name}</b> — 💌 {rec} | 👀 {clk}\n"
        bot.send_message(user_id, top_text, reply_markup=admin_menu)

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
        bot.send_message(user_id, "🕶️ <b>Напиши анонимный ответ</b> 🔥", reply_markup=cancel_menu)

    elif data.startswith("sup_reply_") and user_id == ADMIN_ID:
        target_id = int(data.split("_")[-1])
        admin_reply_mode[ADMIN_ID] = target_id
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        name, _, _, _, _ = get_user_info(target_id)
        bot.send_message(ADMIN_ID, f"✉️ Отправь ответ пользователю <b>{name}</b> (<code>{target_id}</code>)", reply_markup=cancel_menu)

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
