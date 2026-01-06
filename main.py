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
        last_active INTEGER,
        language TEXT DEFAULT 'ru'
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

# ====== Память и язык ======
waiting_message = {}
admin_reply_mode = {}
blocked_users = set()
last_message_time = {}
ANTISPAM_INTERVAL = 30
user_language = {}  # Временное хранение (в проде лучше в БД)

def load_blocked():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM blocked_users")
    for row in c.fetchall():
        blocked_users.add(row[0])
    conn.close()

load_blocked()

# ====== ТЕКСТЫ ======
TEXTS = {
    'ru': {
        'welcome': "🎉 <b>Добро пожаловать в Anony SMS!</b>\n\nПолучай и отправляй сообщения <b>полностью анонимно</b>.\n\n🔗 <b>Твоя ссылка:</b>\n<code>{link}</code>\n\nРаспространи её — и получай анонимные сообщения!",
        'my_link': "🔗 <b>Твоя личная анонимная ссылка</b>\n\n<code>{link}</code>\n\nРаспространяй её среди друзей!",
        'qr_caption': "📱 <b>Твой QR-код Anony SMS</b>\n\nСканируй или покажи друзьям!\n\n<i>Ссылка: {link}</i>",
        'profile': "📌 <b>Твой профиль</b>\n\n👤 Имя: {name}\n🌀 Username: {username}\n🆔 ID: <code>{user_id}</code>\n\n📊 Статистика:\n💌 Получено анонимок: <code>{received}</code>\n📤 Отправлено: <code>{sent}</code>\n👀 Переходов по ссылке: <code>{clicks}</code>\n\n🔗 Твоя ссылка: {link}",
        'support_entry': "📩 <b>Служба поддержки Anony SMS</b>\n\nМы всегда готовы помочь! ❤️\n\nНапиши свой вопрос, пришли скриншот, видео или голосовое сообщение.",
        'support_sent': "✅ <b>Обращение отправлено!</b>\n\nМы получили твоё сообщение и скоро ответим.\nСпасибо, что ты с нами! 🌟",
        'support_reply': "✉️ <b>Ответ от поддержки Anony SMS</b> 👨‍💻\n\nЕсли это пришло по ошибке — просто проигнорируйте.\nПо всем вопросам пишите в «📩 Поддержка»!",
        'anon_msg': "🕶️ <b>Анонимное сообщение пришло!</b>",
        'sent_anon': "✅ <b>Сообщение отправлено анонимно!</b>\nТвоя анонимность сохранена на 100% 🕶️",
        'manual_prompt': "🔍 Введи <b>ID пользователя</b>, которому хочешь написать анонимно.\n\nID можно увидеть в своём профиле.",
        'manual_accepted': "✅ ID принят: <b>{name}</b> (<code>{target_id}</code>)\n\nТеперь отправь любое сообщение — оно уйдёт анонимно!",
        'cant_self': "❌ Нельзя отправлять сообщение самому себе.",
        'help': "ℹ️ <b>Как работает Anony SMS?</b>\n\n1. Получи свою ссылку или QR-код\n2. Распространи её где угодно\n3. Получай анонимные сообщения\n4. Отвечай анонимно одним нажатием\n\nВсё просто, безопасно и полностью анонимно! ❤️",
        'settings': "⚙️ <b>Настройки приватности</b>",
        'receive_on': "🔔 Приём анонимных сообщений <b>включён</b>.",
        'receive_off': "🔕 Приём анонимных сообщений <b>отключён</b>.",
        'cancel': "❌ <b>Действие отменено</b>",
        'lang_menu': "🌍 <b>Выберите язык</b>",
        'lang_changed': "✅ Язык успешно изменён!",
        'back': "⬅️ Назад в меню",
        'admin_top': "🏆 <b>ТОП-10 пользователей (админ)</b>",
    },
    'uk': {
        'welcome': "🎉 <b>Ласкаво просимо до Anony SMS!</b>\n\nОтримуй та надсилай повідомлення <b>повністю анонімно</b>.\n\n🔗 <b>Твоє посилання:</b>\n<code>{link}</code>\n\nПоширюй його — і отримуй анонімки!",
        'my_link': "🔗 <b>Твоє особисте анонімне посилання</b>\n\n<code>{link}</code>\n\nПоширюй серед друзів!",
        'qr_caption': "📱 <b>Твій QR-код Anony SMS</b>\n\nСкануй або покажи друзям!\n\n<i>Посилання: {link}</i>",
        'profile': "📌 <b>Твій профіль</b>\n\n👤 Ім'я: {name}\n🌀 Username: {username}\n🆔 ID: <code>{user_id}</code>\n\n📊 Статистика:\n💌 Отримано анонімок: <code>{received}</code>\n📤 Надіслано: <code>{sent}</code>\n👀 Переходів за посиланням: <code>{clicks}</code>\n\n🔗 Твоє посилання: {link}",
        'support_entry': "📩 <b>Служба підтримки Anony SMS</b>\n\nМи завжди готові допомогти! ❤️\n\nНапиши своє питання, надішли скріншот, відео чи голосове повідомлення.",
        'support_sent': "✅ <b>Звернення надіслано!</b>\n\nМи отримали твоє повідомлення і скоро відповімо.\nДякуємо, що ти з нами! 🌟",
        'support_reply': "✉️ <b>Відповідь від підтримки Anony SMS</b> 👨‍💻\n\nЯкщо це прийшло помилково — просто проігноруйте.\nЗа всіма питаннями пишіть у «📩 Підтримка»!",
        'anon_msg': "🕶️ <b>Анонімне повідомлення прийшло!</b>",
        'sent_anon': "✅ <b>Повідомлення надіслано анонімно!</b>\nТвоя анонімність збережена на 100% 🕶️",
        'manual_prompt': "🔍 Введи <b>ID користувача</b>, якому хочеш написати анонімно.\n\nID видно у своєму профілі.",
        'manual_accepted': "✅ ID прийнято: <b>{name}</b> (<code>{target_id}</code>)\n\nТепер надішли будь-яке повідомлення — воно піде анонімно!",
        'cant_self': "❌ Не можна надсилати повідомлення самому собі.",
        'help': "ℹ️ <b>Як працює Anony SMS?</b>\n\n1. Отримай своє посилання або QR-код\n2. Поширюй його де завгодно\n3. Отримуй анонімні повідомлення\n4. Відповідай анонімно одним натисканням\n\nВсе просто, безпечно та повністю анонімно! ❤️",
        'settings': "⚙️ <b>Налаштування приватності</b>",
        'receive_on': "🔔 Прийом анонімних повідомлень <b>увімкнено</b>.",
        'receive_off': "🔕 Прийом анонімних повідомлень <b>вимкнено</b>.",
        'cancel': "❌ <b>Дію скасовано</b>",
        'lang_menu': "🌍 <b>Оберіть мову</b>",
        'lang_changed': "✅ Мову успішно змінено!",
        'back': "⬅️ Назад у меню",
        'admin_top': "🏆 <b>ТОП-10 користувачів (адмін)</b>",
    },
    'en': {
        'welcome': "🎉 <b>Welcome to Anony SMS!</b>\n\nReceive and send messages <b>completely anonymously</b>.\n\n🔗 <b>Your link:</b>\n<code>{link}</code>\n\nShare it — and get anonymous messages!",
        'my_link': "🔗 <b>Your personal anonymous link</b>\n\n<code>{link}</code>\n\nShare it with friends!",
        'qr_caption': "📱 <b>Your Anony SMS QR code</b>\n\nScan or show to friends!\n\n<i>Link: {link}</i>",
        'profile': "📌 <b>Your profile</b>\n\n👤 Name: {name}\n🌀 Username: {username}\n🆔 ID: <code>{user_id}</code>\n\n📊 Statistics:\n💌 Received: <code>{received}</code>\n📤 Sent: <code>{sent}</code>\n👀 Link clicks: <code>{clicks}</code>\n\n🔗 Your link: {link}",
        'support_entry': "📩 <b>Anony SMS Support</b>\n\nWe are always ready to help! ❤️\n\nWrite your question, send a screenshot, video or voice message.",
        'support_sent': "✅ <b>Message sent to support!</b>\n\nWe received your message and will reply soon.\nThank you for being with us! 🌟",
        'support_reply': "✉️ <b>Reply from Anony SMS support</b> 👨‍💻\n\nIf this came by mistake — just ignore it.\nFor any questions, write to «📩 Support»!",
        'anon_msg': "🕶️ <b>Anonymous message received!</b>",
        'sent_anon': "✅ <b>Message sent anonymously!</b>\nYour anonymity is 100% protected 🕶️",
        'manual_prompt': "🔍 Enter the <b>user ID</b> you want to message anonymously.\n\nYou can see your ID in your profile.",
        'manual_accepted': "✅ ID accepted: <b>{name}</b> (<code>{target_id}</code>)\n\nNow send any message — it will be sent anonymously!",
        'cant_self': "❌ You cannot send a message to yourself.",
        'help': "ℹ️ <b>How Anony SMS works</b>\n\n1. Get your link or QR code\n2. Share it anywhere\n3. Receive anonymous messages\n4. Reply anonymously with one tap\n\nSimple, safe and fully anonymous! ❤️",
        'settings': "⚙️ <b>Privacy settings</b>",
        'receive_on': "🔔 Receiving anonymous messages is <b>enabled</b>.",
        'receive_off': "🔕 Receiving anonymous messages is <b>disabled</b>.",
        'cancel': "❌ <b>Action cancelled</b>",
        'lang_menu': "🌍 <b>Choose language</b>",
        'lang_changed': "✅ Language changed successfully!",
        'back': "⬅️ Back to menu",
        'admin_top': "🏆 <b>TOP-10 users (admin)</b>",
    }
}

def t(user_id, key, **kwargs):
    lang = user_language.get(user_id, 'ru')
    return TEXTS[lang].get(key, TEXTS['ru'][key]).format(**kwargs)

# ====== Клавиатуры ======
def main_menu(user_id, is_admin=False):
    lang = user_language.get(user_id, 'ru')
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(
        KeyboardButton("📩 Моя ссылка" if lang in ['ru', 'uk'] else "My link"),
        KeyboardButton("📱 QR-код" if lang in ['ru', 'uk'] else "QR code")
    )
    markup.row(
        KeyboardButton("✉️ Ответить анонимно" if lang == 'ru' else "✉️ Відповісти анонімно" if lang == 'uk' else "Reply anonymously"),
        KeyboardButton("⚙️ Настройки" if lang in ['ru', 'uk'] else "Settings")
    )
    markup.row(KeyboardButton("📌 Профиль" if lang in ['ru', 'uk'] else "Profile"))
    markup.row(
        KeyboardButton("📩 Поддержка" if lang == 'ru' else "📩 Підтримка" if lang == 'uk' else "Support"),
        KeyboardButton("ℹ️ Помощь" if lang == 'ru' else "ℹ️ Допомога" if lang == 'uk' else "Help")
    )
    markup.row(KeyboardButton("🌍 LANG"))
    if is_admin:
        markup.add(KeyboardButton("🔧 Админ-панель" if lang == 'ru' else "🔧 Адмін-панель" if lang == 'uk' else "Admin panel"))
    return markup

def lang_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(KeyboardButton("🇷🇺 Русский"))
    markup.row(KeyboardButton("🇺🇦 Українська"))
    markup.row(KeyboardButton("🇬🇧 English"))
    markup.add(KeyboardButton("⬅️ Назад" if user_language.get(message.from_user.id, 'ru') != 'en' else "Back"))
    return markup

# ====== Утилиты ======
def update_user(user):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    lang = user_language.get(user.id, 'ru')
    c.execute("""INSERT OR REPLACE INTO users 
                 (user_id, username, first_name, last_active, language) 
                 VALUES (?, ?, ?, ?, ?)""",
              (user.id, user.username or "", user.first_name or "", int(time.time()), lang))
    conn.commit()
    conn.close()

def get_user_info(user_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT username, first_name, link_clicks, messages_received, messages_sent, last_active FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    if row:
        username = f"@{row[0]}" if row[0] else "<i>hidden 😶</i>"
        name = row[1] or "Anonymous 🕶️"
        clicks = row[2] or 0
        received = row[3] or 0
        sent = row[4] or 0
        last = time.strftime("%d.%m.%Y %H:%M", time.localtime(row[5])) if row[5] else "unknown"
        return name, username, clicks, received, sent, last
    return "Anonymous 🕶️", "<i>hidden 😶</i>", 0, 0, 0, "unknown"

# ====== ТОП только для админа ======
def show_top10_admin(chat_id):
    lang = user_language.get(chat_id, 'ru')
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, messages_received, link_clicks FROM users ORDER BY messages_received DESC, link_clicks DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.send_message(chat_id, "ТОП пуст" if lang != 'en' else "TOP is empty")
        return
    text = t(chat_id, 'admin_top') + "\n\n"
    for i, (uid, rec, clk) in enumerate(rows, 1):
        name, _, _, _, _, _ = get_user_info(uid)
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        text += f"{medal} <b>{name}</b>\n💌 {rec} | 👀 {clk}\n\n"
    bot.send_message(chat_id, text, reply_markup=admin_menu)

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        bot.send_message(user_id, "Доступ ограничен / Доступ обмежено / Access restricted")
        return

    update_user(message.from_user)
    is_admin = user_id == ADMIN_ID
    lang = user_language.get(user_id, 'ru')

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")
        if time.time() - last_message_time.get(user_id, 0) < ANTISPAM_INTERVAL:
            bot.send_message(user_id, "⏳ Подожди немного" if lang != 'en' else "Wait a bit")
            return
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.send_message(user_id, "Готов отправить анонимное сообщение?" if lang == 'ru' else "Готовий надіслати анонімне повідомлення?" if lang == 'uk' else "Ready to send anonymous message?", reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id, t(user_id, 'welcome', link=link), reply_markup=main_menu(user_id, is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_all(message):
    user_id = message.from_user.id
    if user_id in blocked_users:
        return

    is_admin = user_id == ADMIN_ID
    lang = user_language.get(user_id, 'ru')
    text = message.text or message.caption or ""

    update_user(message.from_user)

    # Отмена
    if text in ["❌ Отмена", "❌ Скасувати", "❌ Cancel"]:
        waiting_message.pop(user_id, None)
        if is_admin and ADMIN_ID in admin_reply_mode:
            admin_reply_mode.pop(ADMIN_ID)
        bot.send_message(user_id, t(user_id, 'cancel'), reply_markup=main_menu(user_id, is_admin))
        return

    # Язык
    if text == "🌍 LANG":
        bot.send_message(user_id, t(user_id, 'lang_menu'), reply_markup=lang_menu())
        return

    if text in ["🇷🇺 Русский", "🇺🇦 Українська", "🇬🇧 English"]:
        new_lang = 'ru' if "Русский" in text else 'uk' if "Українська" in text else 'en'
        user_language[user_id] = new_lang
        bot.send_message(user_id, t(user_id, 'lang_changed'), reply_markup=main_menu(user_id, is_admin))
        return

    if text in ["⬅️ Назад", "Back"]:
        bot.send_message(user_id, "🏠", reply_markup=main_menu(user_id, is_admin))
        return

    # Поддержка
    if text in ["📩 Поддержка", "📩 Підтримка", "Support"]:
        bot.send_message(user_id, t(user_id, 'support_entry'), reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    if waiting_message.get(user_id) == "support":
        name, username, _, _, _, last = get_user_info(user_id)
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Ответить" if lang != 'en' else "Reply", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор" if lang != 'en' else "Ignore", callback_data=f"sup_ignore_{user_id}")
        )
        info = f"📩 Новое обращение\n👤 {name}\n🌀 {username}\n🆔 <code>{user_id}</code>"
        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, info, reply_to_message_id=forwarded.message_id, reply_markup=kb)
        bot.send_message(user_id, t(user_id, 'support_sent'), reply_markup=main_menu(user_id, is_admin))
        waiting_message.pop(user_id, None)
        return

    # Админ ответ в поддержку
    if is_admin and ADMIN_ID in admin_reply_mode:
        target_id = admin_reply_mode.pop(ADMIN_ID)
        try:
            if message.content_type == 'text':
                sent = bot.send_message(target_id, message.text)
            else:
                sent = bot.copy_message(target_id, ADMIN_ID, message.message_id)
            bot.send_message(target_id, t(target_id, 'support_reply'), reply_to_message_id=sent.message_id)
            bot.send_message(ADMIN_ID, "Ответ отправлен", reply_markup=admin_menu)
        except:
            bot.send_message(ADMIN_ID, "Ошибка доставки")
        return

    # Ручной ответ по ID
    if text in ["✉️ Ответить анонимно", "✉️ Відповісти анонімно", "Reply anonymously"]:
        bot.send_message(user_id, t(user_id, 'manual_prompt'), reply_markup=cancel_menu)
        waiting_message[user_id] = "waiting_manual_id"
        return

    if waiting_message.get(user_id) == "waiting_manual_id" and text.isdigit():
        target_id = int(text)
        if target_id == user_id:
            bot.send_message(user_id, t(user_id, 'cant_self'))
            waiting_message.pop(user_id, None)
            return
        name, _, _, _, _, _ = get_user_info(target_id)
        bot.send_message(user_id, t(user_id, 'manual_accepted', name=name, target_id=target_id), reply_markup=cancel_menu)
        waiting_message[user_id] = target_id
        return

    # Анонимная отправка (по ссылке или ручная)
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)
        increment_stat(target_id, "messages_received")
        increment_stat(user_id, "messages_sent")

        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("✉️ Ответить анонимно" if lang != 'en' else "Reply anonymously", callback_data=f"reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор" if lang != 'en' else "Ignore", callback_data="ignore")
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

    # Команды меню
    if text in ["📩 Моя ссылка", "📩 Моє посилання", "My link"]:
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'my_link', link=link), reply_markup=main_menu(user_id, is_admin))

    elif text in ["📱 QR-код", "QR code"]:
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

    elif text in ["📌 Профиль", "Profile"]:
        name, username, clicks, received, sent, _ = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, t(user_id, 'profile', name=name, username=username, user_id=user_id, received=received, sent=sent, clicks=clicks, link=link), reply_markup=main_menu(user_id, is_admin))

    elif text in ["⚙️ Настройки", "⚙️ Налаштування", "Settings"]:
        bot.send_message(user_id, t(user_id, 'settings'), reply_markup=settings_menu)

    elif text in ["🔕 Отключить приём", "🔕 Вимкнути прийом", "🔔 Enable receiving", "🔕 Disable receiving"]:
        status = 'off' if "Отключить" in text or "Вимкнути" in text or "Disable" in text else 'on'
        bot.send_message(user_id, t(user_id, 'receive_on' if status == 'on' else 'receive_off'), reply_markup=main_menu(user_id, is_admin))

    elif text in ["ℹ️ Помощь", "ℹ️ Допомога", "Help"]:
        bot.send_message(user_id, t(user_id, 'help'), reply_markup=main_menu(user_id, is_admin))

    elif is_admin and text in ["🔥 Топ-10 пользователей", "🔥 Топ-10 користувачів", "TOP-10 users"]:
        show_top10_admin(user_id)

# ====== Callbacks ======
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    lang = user_language.get(user_id, 'ru')
    if user_id in blocked_users:
        return

    if call.data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)

    elif call.data.startswith("reply_"):
        sender_id = int(call.data.split("_")[1])
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "Напиши ответ анонимно:" if lang != 'en' else "Write anonymous reply:", reply_markup=cancel_menu)

    elif call.data.startswith("sup_reply_") and user_id == ADMIN_ID:
        target_id = int(call.data.split("_")[-1])
        admin_reply_mode[ADMIN_ID] = target_id
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        bot.send_message(ADMIN_ID, f"Отправь ответ пользователю {target_id}", reply_markup=cancel_menu)

    elif call.data.startswith("sup_ignore_") and user_id == ADMIN_ID:
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
