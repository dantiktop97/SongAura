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
import re

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
waiting_message = {}      # Кто куда пишет (анонимно или в поддержку)
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
        bot.send_message(chat_id, 
            "🔥 <b>ТОП-10 ПОКА ПУСТОЙ</b> 😔\n\n"
            "Активность ещё не набрала обороты!\n"
            "Будьте первыми — распространяйте ссылки, получайте анонимки и поднимайтесь на вершину! 🏔️\n\n"
            "Скоро здесь будут настоящие звёзды Anony SMS! ⭐✨")
        return

    text = "🏆 <b>ТОП-10 САМЫХ ПОПУЛЯРНЫХ ПОЛЬЗОВАТЕЛЕЙ ANONY SMS</b> 🔥🔥🔥\n\n"
    text += "Эти легенды получают тонны анонимных сообщений и переходов по ссылке! 🌟💥\n"
    text += "Восхищаемся их активностью и ждём новых чемпионов! 👑\n\n"
    for i, (uid, msgs, clicks) in enumerate(rows, 1):
        name, _, _, _, _, _ = get_user_info(uid)
        medal = ["🥇 ПЕРВОЕ МЕСТО!", "🥈 ВТОРОЕ МЕСТО!", "🥉 ТРЕТЬЕ МЕСТО!"][i-1] if i <= 3 else f"<b>{i}-е место</b>"
        text += f"{medal}\n"
        text += f"<b>{name}</b> 👤\n"
        text += f"💌 Получено анонимок: <b><code>{msgs}</code></b>\n"
        text += f"👀 Переходов по ссылке: <b><code>{clicks}</code></b>\n\n"
    text += "🚀 <i>Хочешь в этот топ? Распространяй ссылку как можно шире — и ты здесь будешь сиять!</i> ✨⭐"
    bot.send_message(chat_id, text, reply_markup=admin_menu if is_admin else get_main_menu(is_admin))

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        bot.send_message(user_id, 
            "🚫 <b>ДОСТУП К БОТУ ОГРАНИЧЕН</b> 🔒\n\n"
            "К сожалению, ваш аккаунт временно заблокирован.\n"
            "Если это ошибка — напиши в поддержку, мы разберёмся! ❤️\n\n"
            "Мы ценим каждого пользователя! 🌟")
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
                f"Чтобы избежать спама, можно отправлять сообщение раз в <code>{ANTISPAM_INTERVAL}</code> секунд.\n"
                "Ещё чуть-чуть — и ты снова в деле! 🚀")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now
        bot.send_message(user_id, 
            "🕶️ <b>ГОТОВ(А) ОТПРАВИТЬ АНОНИМНОЕ СООБЩЕНИЕ?</b> 🔥\n\n"
            "Пиши текст, присылай фото 🎥, видео 📹, голосовое 🎤 или стикер — всё уйдёт <b>полностью анонимно</b>!\n\n"
            "Получатель никогда не узнает, от кого это пришло... Магия Anony SMS в действии! ✨💥",
            reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
                     f"🎉 <b>ДОБРО ПОЖАЛОВАТЬ В ANONY SMS!</b> 🎉\n\n"
                     f"🌟 Это место, где можно получать и отправлять сообщения <b>полностью анонимно</b>!\n\n"
                     f"🔗 <b>ТВОЯ ЛИЧНАЯ АНОНИМНАЯ ССЫЛКА:</b>\n"
                     f"<code>{link}</code>\n\n"
                     f"📢 Распространи её в сторис, био, чатах, среди друзей — и люди начнут писать тебе анонимно!\n"
                     f"💬 Под каждым сообщением — возможность ответить анонимно одним нажатием\n"
                     f"🏆 Чем больше переходов и сообщений — тем выше ты в топе популярности!\n\n"
                     f"Всё просто, безопасно и невероятно захватывающе! Начни прямо сейчас — мир ждёт твоих анонимных историй! 🚀✨❤️",
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

    # === Поддержка (обычный пользователь) ===
    if text == "📩 Поддержка":
        bot.send_message(user_id, 
            "📩 <b>СЛУЖБА ПОДДЕРЖКИ ANONY SMS</b> 👨‍💻✨\n\n"
            "Мы всегда на связи и готовы помочь тебе в любой ситуации! ❤️\n\n"
            "🔥 Напиши свой вопрос\n"
            "📸 Пришли скриншот\n"
            "🎥 Отправь видео\n"
            "🎤 Запиши голосовое сообщение\n\n"
            "Мы разберёмся во всём максимально быстро и подробно!\n"
            "Ты — важная часть нашего сообщества, и мы ценим каждого пользователя! 🌟\n\n"
            "Ждём твоё сообщение! 🚀",
            reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    # Пользователь пишет в поддержку
    if waiting_message.get(user_id) == "support":
        name, username, _, _, _, last = get_user_info(user_id)

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✉️ Ответить", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data=f"sup_ignore_{user_id}")
        )

        info_text = (
            f"📩 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ</b> ❗🔥\n\n"
            f"👤 <b>Имя:</b> {name}\n"
            f"🌀 <b>Username:</b> {username}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"⏰ <b>Последняя активность:</b> {last}\n"
            f"🕐 <b>Время обращения:</b> {time.strftime('%d.%m.%Y в %H:%M')}\n\n"
            f"✨ Пользователь ждёт твоего ответа! Будь на высоте! 🚀"
        )

        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, info_text, reply_to_message_id=forwarded.message_id, reply_markup=markup)

        bot.send_message(user_id, 
            "✅ <b>ОБРАЩЕНИЕ УСПЕШНО ОТПРАВЛЕНО!</b> 🎉\n\n"
            "Мы получили всё: текст, фото, видео, голосовое — всё в порядке! 👍\n"
            "Наша команда уже занимается твоим вопросом 💼\n\n"
            "Ответим максимально быстро и подробно!\n"
            "Спасибо, что ты с нами — ты лучший пользователь! ❤️🌟\n\n"
            "Ожидай ответа — скоро напишем! 🚀✨",
            reply_markup=get_main_menu(is_admin))
        waiting_message.pop(user_id, None)
        return

    # === Остальные команды меню ===
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, 
            "🔗 <b>ТВОЯ ЛИЧНАЯ АНОНИМНАЯ ССЫЛКА</b> 🔥\n\n"
            f"<code>{link}</code>\n\n"
            "📢 Распространяй её везде: сторис, био, чаты, соцсети!\n"
            "Каждый переход — это новая анонимка для тебя! 💌\n"
            "Чем больше людей перейдут — тем выше ты взлетишь в топе! 🏆✨",
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
                       caption="📱 <b>ТВОЙ ЭКСКЛЮЗИВНЫЙ QR-КОД ANONY SMS</b> 🌟\n\n"
                               "Сканируй — и сразу переходи к анонимному общению!\n"
                               "Покажи друзьям, размести в сторис, на визитке или в профиле!\n\n"
                               f"<i>Ссылка внутри: {link}</i>",
                       reply_markup=get_main_menu(is_admin))

    elif text == "📌 Профиль":
        name, username, clicks, received, sent, last = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
                         f"📌 <b>ТВОЙ ПОЛНЫЙ ПРОФИЛЬ В ANONY SMS</b> 👤✨\n\n"
                         f"📛 <b>Имя:</b> {name}\n"
                         f"🌀 <b>Username:</b> {username}\n"
                         f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                         f"⏰ <b>Последняя активность:</b> {last}\n\n"
                         f"📊 <b>ТВОЯ ВНУШИТЕЛЬНАЯ СТАТИСТИКА</b> 📈🔥\n"
                         f"💌 <b>Получено анонимных сообщений:</b> <code>{received}</code>\n"
                         f"📤 <b>Отправлено анонимных сообщений:</b> <code>{sent}</code>\n"
                         f"👀 <b>Переходов по твоей ссылке:</b> <code>{clicks}</code>\n\n"
                         f"🔗 <b>Твоя ссылка:</b> {link}\n\n"
                         f"🚀 <i>Ты — настоящая звезда анонимного общения! Продолжай сиять!</i> ⭐❤️",
                         reply_markup=get_main_menu(is_admin))

    elif text == "🔥 Топ-10":
        show_top10(user_id, is_admin)

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, 
            "⚙️ <b>НАСТРОЙКИ ПРИВАТНОСТИ ANONY SMS</b> 🔒\n\n"
            "Ты полностью контролируешь свою анонимность и приём сообщений!\n\n"
            "🔕 <b>Отключить приём</b> — полная тишина, никто не напишет\n"
            "🔔 <b>Включить приём</b> — открыты для всех анонимок!\n\n"
            "Выбирай то, что тебе комфортно прямо сейчас! 😊",
            reply_markup=settings_menu)

    elif text in ["🔕 Отключить приём", "🔔 Включить приём"]:
        status = "ОТКЛЮЧЁН" if text == "🔕 Отключить приём" else "ВКЛЮЧЁН"
        emoji = "🔕" if text == "🔕 Отключить приём" else "🔔"
        bot.send_message(user_id, 
            f"{emoji} <b>ПРИЁМ АНОНИМНЫХ СООБЩЕНИЙ {status}</b> {'🔒' if status == 'ОТКЛЮЧЁН' else '✅'}\n\n"
            f"{'Теперь ты в полной безопасности и тишине!' if status == 'ОТКЛЮЧЁН' else 'Готов(а) к новым анонимкам? Теперь все смогут писать тебе тайно!'}\n\n"
            f"{'Включи обратно, когда захочешь новых сообщений! 🚀✨' if status == 'ОТКЛЮЧЁН' else 'Жди интересных признаний, вопросов и секретов! 🔥❤️'}",
            reply_markup=get_main_menu(is_admin))

    elif text == "⬅️ Назад в меню":
        bot.send_message(user_id, "🏠 <b>ВОЗВРАЩАЕМСЯ В ГЛАВНОЕ МЕНЮ</b> 🚪", reply_markup=get_main_menu(is_admin))

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id,
                         "ℹ️ <b>КАК РАБОТАЕТ ANONY SMS?</b> ❓\n\n"
                         "1️⃣ Получи свою уникальную ссылку или QR-код\n"
                         "2️⃣ Распространи её где угодно: сторис, био, чаты, соцсети\n"
                         "3️⃣ Люди начнут отправлять тебе анонимные сообщения!\n"
                         "4️⃣ Отвечай анонимно — одним нажатием\n"
                         "5️⃣ Собирай переходы и сообщения — поднимайся в топ-10!\n\n"
                         "🚀 <b>Всё просто, быстро и полностью анонимно!</b>\n\n"
                         "Это место, где можно быть собой, не раскрывая имени 🌟\n"
                         "Тайны, признания, вопросы — всё здесь!\n\n"
                         "По любым вопросам — жми <b>Поддержка</b> 👨‍💻❤️",
                         reply_markup=get_main_menu(is_admin))

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id, 
            "🔍 <b>РУЧНОЙ АНОНИМНЫЙ ОТВЕТ</b> ✉️\n\n"
            "Введи <b>ID пользователя</b>, которому хочешь написать анонимно:\n"
            "(ID можно увидеть в своём профиле или в топ-10)\n\n"
            "После ввода — отправляй любое сообщение: текст, фото, видео — всё уйдёт анонимно! 🔥",
            reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"
        return

    elif text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        bot.send_message(user_id, "❌ <b>ДЕЙСТВИЕ ОТМЕНЕНО</b>\n\nВозвращаемся в главное меню! 🏠", reply_markup=get_main_menu(is_admin))
        return

    # === Анонимная отправка по ссылке ===
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)

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
                bot.send_message(target_id, f"🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ ПРИШЛО!</b> ✨🔥\n\n{content_text}", reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id)
                bot.send_message(target_id, "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ ПРИШЛО!</b> ✨🔥", reply_to_message_id=copied.message_id, reply_markup=markup)
        except Exception as e:
            bot.send_message(user_id, "❌ <b>НЕ УДАЛОСЬ ДОСТАВИТЬ</b>\nПользователь мог заблокировать бота или ограничить сообщения.")

        bot.send_message(user_id, 
            "✅ <b>СООБЩЕНИЕ УСПЕШНО ОТПРАВЛЕНО АНОНИМНО!</b> 🎉\n\n"
            "Получатель уже видит его!\n"
            "Твоя анонимность сохранена на 100% 🕶️\n\n"
            "Продолжай — это невероятно круто! 🔥🚀❤️",
            reply_markup=get_main_menu(is_admin))
        return

# ====== Callback обработка ======
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
        bot.send_message(user_id, 
            "🕶️ <b>НАПИШИ СВОЙ АНОНИМНЫЙ ОТВЕТ</b> 🔥\n\n"
            "Он уйдёт мгновенно — получатель получит его сразу!\n"
            "Текст, фото, видео — всё подойдёт! ✨",
            reply_markup=cancel_menu)
        return

    # === Обработка кнопок поддержки (только админ) ===
    if user_id == ADMIN_ID and data.startswith("sup_"):
        target_id = int(data.split("_")[-1])

        if data.startswith("sup_ignore_"):
            bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
            bot.answer_callback_query(call.id, "Обращение проигнорировано")
            return

        if data.startswith("sup_reply_"):
            bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
            bot.send_message(ADMIN_ID,
                f"✉️ <b>ОТПРАВЬ ОТВЕТ ПОЛЬЗОВАТЕЛЮ</b>\n\n"
                f"🆔 ID: <code>{target_id}</code>\n"
                f"👤 Имя: {get_user_info(target_id)[0]}\n\n"
                "Отправь любое сообщение (текст, фото, видео, голосовое и т.д.)\n"
                "Оно будет отправлено пользователю от имени бота с подписью поддержки 🚀",
                reply_markup=cancel_menu)
            waiting_message[ADMIN_ID] = f"support_reply_to_{target_id}"
            bot.answer_callback_query(call.id, "Режим ответа активирован")
            return

# ====== ОТВЕТ АДМИНА В ПОДДЕРЖКУ (ИСПРАВЛЕННЫЙ И НАДЁЖНЫЙ) ======
@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and str(waiting_message.get(ADMIN_ID, "")).startswith("support_reply_to_"))
def admin_reply_to_support(message):
    try:
        target_str = waiting_message.pop(ADMIN_ID)
        target_id = int(target_str.split("_")[-1])

        # Отправляем сообщение пользователю ОТ ИМЕНИ БОТА
        if message.content_type == 'text':
            sent_msg = bot.send_message(target_id, message.text)
        else:
            sent_msg = bot.copy_message(target_id, ADMIN_ID, message.message_id)

        # Добавляем красивую подпись
        bot.send_message(target_id,
            "✉️ <b>Вам ответил оператор поддержки Anony SMS</b> 👨‍💻✨\n\n"
            "Если это сообщение пришло по ошибке или не относится к вашему вопросу — просто проигнорируйте его.\n"
            "По всем вопросам всегда пишите в раздел «📩 Поддержка» — мы на связи 24/7! ❤️🚀",
            reply_to_message_id=sent_msg.message_id)

        # Подтверждение админу
        bot.send_message(ADMIN_ID,
            "✅ <b>ОТВЕТ УСПЕШНО ОТПРАВЛЕН ПОЛЬЗОВАТЕЛЮ!</b> 🎉\n\n"
            f"Пользователь <code>{target_id}</code> получил сообщение.\n"
            "Ты лучший админ! 🔥❤️",
            reply_markup=admin_menu)

    except Exception as e:
        bot.send_message(ADMIN_ID,
            f"❌ <b>ОШИБКА ПРИ ОТПРАВКЕ ОТВЕТА</b>\n\n"
            f"Пользователь, вероятно, заблокировал бота или ограничил личные сообщения.\n"
            f"ID: <code>{target_id}</code>\n"
            f"Ошибка: {str(e)}")

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
