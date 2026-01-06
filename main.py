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
        username = f"@{row[0]}" if row[0] else "<i>скрыт</i>"
        name = row[1] or "Аноним"
        clicks = row[2] or 0
        received = row[3] or 0
        sent = row[4] or 0
        last = time.strftime("%d.%m.%Y в %H:%M", time.localtime(row[5])) if row[5] else "давно не был(а)"
        return name, username, clicks, received, sent, last
    return "Неизвестный пользователь", "<i>скрыт</i>", 0, 0, 0, "неизвестно"

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
        return "😶 <i>Текстовой активности пока нет</i>"
    
    counter = Counter(all_words)
    top = counter.most_common(limit)
    return "\n".join([f"🔹 <b>{word}</b> — <code>{count}</code> раз(а)" for word, count in top])

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
        bot.send_message(chat_id, "🔥 <b>Топ-10 пока пуст</b> 😔\n\nАктивнее распространяйте свои ссылки — и вы здесь будете! 🚀")
        return

    text = "🏆 <b>ТОП-10 САМЫХ ПОПУЛЯРНЫХ ПОЛЬЗОВАТЕЛЕЙ</b> 🔥\n\n"
    text += "Эти люди получают больше всего анонимных сообщений и переходов по ссылке! 🌟\n\n"
    for i, (uid, msgs, clicks) in enumerate(rows, 1):
        name, username, _, _, _, _ = get_user_info(uid)
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"<b>{i}</b>."
        text += f"{medal} <b>{name}</b> ({username})\n"
        text += f"   🆔 ID: <code>{uid}</code>\n"
        text += f"   💌 Получено анонимок: <b><code>{msgs}</code></b>\n"
        text += f"   👀 Переходов по ссылке: <b><code>{clicks}</code></b>\n\n"
    text += "🔥 <i>Хочешь в топ? Распространяй свою ссылку активнее!</i> ✨"
    bot.send_message(chat_id, text, reply_markup=admin_menu if is_admin else get_main_menu(is_admin))

def show_user_profile(admin_id, target_id):
    name, username, clicks, received, sent, last = get_user_info(target_id)
    top_words = get_top_words(target_id)
    blocked = "✅ Да, заблокирован" if is_blocked(target_id) else "❌ Нет"

    text = f"🔍 <b>ДЕТАЛЬНЫЙ ПРОФИЛЬ ПОЛЬЗОВАТЕЛЯ</b> 👤\n\n"
    text += f"📛 <b>Имя:</b> <i>{name}</i>\n"
    text += f"🌀 <b>Username:</b> {username}\n"
    text += f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
    text += f"⏰ <b>Последняя активность:</b> {last}\n"
    text += f"🚫 <b>Статус блокировки:</b> {blocked}\n\n"
    text += f"📊 <b>СТАТИСТИКА АКТИВНОСТИ</b> 📈\n"
    text += f"💌 <b>Получено анонимных сообщений:</b> <code>{received}</code>\n"
    text += f"📤 <b>Отправлено анонимных сообщений:</b> <code>{sent}</code>\n"
    text += f"👀 <b>Переходов по личной ссылке:</b> <code>{clicks}</code>\n\n"
    text += f"🧠 <b>ТОП-5 ЧАСТЫХ СЛОВ В АНОНИМКАХ</b> 💬\n{top_words}\n\n"
    text += "✨ <i>Полный контроль над пользователем в твоих руках</i> 🔥"

    bot.send_message(admin_id, text, reply_markup=admin_menu)

# ====== Обработчики ======
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        bot.send_message(user_id, "🚫 <b>Доступ к боту ограничен</b>\n\nОбратитесь к администратору, если считаете это ошибкой.")
        return

    update_user(message.from_user)
    is_admin = (user_id == ADMIN_ID)

    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        sender_id = int(args[1])
        increment_stat(sender_id, "link_clicks")

        now = time.time()
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > now:
            bot.send_message(user_id, f"⏳ <b>Слишком быстро!</b>\nПодожди <code>{ANTISPAM_INTERVAL}</code> секунд перед следующим сообщением 😊")
            return

        waiting_message[user_id] = sender_id
        last_message_time[user_id] = now
        bot.send_message(user_id, 
            "🕶️ <b>Готов(а) отправить анонимное сообщение?</b> ✨\n\n"
            "Пиши текст, присылай фото, видео, голосовое или стикер — всё уйдёт <b>полностью анонимно</b>! 🔥",
            reply_markup=cancel_menu)
        return

    link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    bot.send_message(user_id,
                     f"🎉 <b>Приветствуем в {BOT_NAME}!</b> 🎉\n\n"
                     f"🔥 Это самый мощный анонимный чат в Telegram!\n\n"
                     f"🔗 <b>Твоя личная анонимная ссылка:</b>\n<code>{link}</code>\n\n"
                     f"📢 Распространи её в сторис, био, чатах — и получай сообщения от кого угодно!\n"
                     f"💬 Под каждым сообщением — возможность ответить анонимно одним касанием 🚀\n\n"
                     f"Начни прямо сейчас — и мир заговорит с тобой анонимно! 🌍✨",
                     reply_markup=get_main_menu(is_admin))

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'document', 'sticker', 'voice', 'animation', 'video_note'])
def handle_all(message):
    user_id = message.from_user.id
    if is_blocked(user_id):
        bot.send_message(user_id, "🚫 <b>Доступ к боту ограничен</b>\n\nОбратитесь к администратору.")
        return

    is_admin = (user_id == ADMIN_ID)
    text = message.text or message.caption or ""

    update_user(message.from_user)

    # === Поддержка ===
    if text == "📩 Поддержка":
        bot.send_message(user_id, 
            "📩 <b>Служба поддержки {BOT_NAME}</b> 👨‍💻\n\n"
            "Мы всегда на связи! 🚀\n"
            "Напиши свой вопрос, пришли скриншот, видео или голосовое сообщение — всё рассмотрим в ближайшее время!\n\n"
            "<i>Ответим максимально быстро и подробно</i> ✨",
            reply_markup=cancel_menu)
        waiting_message[user_id] = "support"
        return

    if waiting_message.get(user_id) == "support":
        name, username, _, _, _, last = get_user_info(user_id)

        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✉️ Ответить", callback_data=f"sup_reply_{user_id}"),
            InlineKeyboardButton("🚫 Игнор", callback_data=f"sup_ignore_{user_id}")
        )

        info_text = (
            f"📩 <b>НОВОЕ ОБРАЩЕНИЕ В ПОДДЕРЖКУ</b> ❗\n\n"
            f"👤 <b>Пользователь:</b> {name}\n"
            f"🌀 <b>Username:</b> {username}\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"⏰ <b>Последняя активность:</b> {last}\n"
            f"🕐 <b>Время обращения:</b> {time.strftime('%d.%m.%Y в %H:%M')}\n\n"
            f"✨ <i>Ожидает вашего ответа...</i>"
        )

        # Форвардим оригинал — сохраняется всё: фото, видео, голосовое и т.д.
        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, info_text, reply_to_message_id=forwarded.message_id, reply_markup=markup)

        bot.send_message(user_id, 
            "✅ <b>Ваше обращение успешно отправлено!</b>\n\n"
            "Мы получили ваше сообщение и уже работаем над ответом 💼\n"
            "Ожидайте — скоро напишем! 🚀\n\n"
            "<i>Спасибо, что вы с нами!</i> ❤️",
            reply_markup=get_main_menu(is_admin))
        waiting_message.pop(user_id, None)
        return

    # === Меню ===
    if text == "📩 Моя ссылка":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id, 
            f"🔗 <b>Твоя личная анонимная ссылка</b> ✨\n\n"
            f"<code>{link}</code>\n\n"
            f"📢 Распространяй её везде — и получай сообщения от всего мира! 🌍\n"
            f"Чем больше переходов — тем выше ты в топе! 🏆",
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
                       caption=f"📱 <b>Твой QR-код для анонимных сообщений</b> 🔥\n\n"
                               f"Покажи его друзьям, размести в сторис или на визитке!\n\n"
                               f"<i>Ссылка: {link}</i>",
                       reply_markup=get_main_menu(is_admin))

    elif text == "📌 Профиль":
        name, username, clicks, received, sent, last = get_user_info(user_id)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        bot.send_message(user_id,
                         f"📌 <b>ТВОЙ ЛИЧНЫЙ ПРОФИЛЬ В {BOT_NAME}</b> 👤\n\n"
                         f"📛 <b>Имя:</b> {name}\n"
                         f"🌀 <b>Username:</b> {username}\n"
                         f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                         f"⏰ <b>Последняя активность:</b> {last}\n\n"
                         f"📊 <b>ТВОЯ СТАТИСТИКА ЗА ВСЁ ВРЕМЯ</b> 📈\n"
                         f"💌 <b>Получено анонимных сообщений:</b> <code>{received}</code>\n"
                         f"📤 <b>Отправлено анонимных сообщений:</b> <code>{sent}</code>\n"
                         f"👀 <b>Переходов по твоей ссылке:</b> <code>{clicks}</code>\n\n"
                         f"🔗 <b>Твоя ссылка:</b> {link}\n\n"
                         f"🚀 <i>Чем больше активности — тем выше в топе!</i> ✨",
                         reply_markup=get_main_menu(is_admin))

    elif text == "🔥 Топ-10":
        show_top10(user_id, is_admin)

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, 
            "⚙️ <b>Настройки приватности</b>\n\n"
            "Управляй приёмом анонимных сообщений:\n\n"
            "🔕 Отключить — никто не сможет написать\n"
            "🔔 Включить — все смогут отправлять анонимки",
            reply_markup=settings_menu)

    elif text == "🔕 Отключить приём":
        bot.send_message(user_id, "🔕 <b>Приём анонимных сообщений отключён</b>\n\nТеперь никто не сможет тебе написать анонимно 🔒", reply_markup=get_main_menu(is_admin))

    elif text == "🔔 Включить приём":
        bot.send_message(user_id, "🔔 <b>Приём анонимных сообщений включён</b>\n\nТеперь все смогут отправлять тебе анонимки! ✨", reply_markup=get_main_menu(is_admin))

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id, 
            "ℹ️ <b>Как работает {BOT_NAME}?</b>\n\n"
            "1️⃣ Получи свою ссылку или QR-код\n"
            "2️⃣ Распространи её где угодно (сторис, био, чаты)\n"
            "3️⃣ Получай анонимные сообщения от всех!\n"
            "4️⃣ Отвечай анонимно одним нажатием\n"
            "5️⃣ Поднимайся в топ по активности!\n\n"
            "🚀 Всё просто, быстро и полностью анонимно!\n\n"
            "По всем вопросам — жми <b>Поддержка</b> 👨‍💻",
            reply_markup=get_main_menu(is_admin))

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id, "🔍 <b>Ручной анонимный ответ</b>\n\nВведи <b>ID пользователя</b>, которому хочешь написать:", reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"
        return

    elif text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        bot.send_message(user_id, "❌ <b>Действие отменено</b>", reply_markup=get_main_menu(is_admin))
        return

    # === Админ-панель ===
    if is_admin:
        if text == "🔧 Админ-панель":
            bot.send_message(user_id, "🔧 <b>Админ-панель открыта</b> ⚡\n\nПолный контроль над ботом в твоих руках!", reply_markup=admin_menu)
            return

        if text == "📊 Статистика бота":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users"); total = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM anon_messages"); msgs = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM blocked_users"); blocked = c.fetchone()[0]
            conn.close()
            bot.send_message(user_id, 
                f"📊 <b>ГЛОБАЛЬНАЯ СТАТИСТИКА БОТА</b> 📈\n\n"
                f"👥 <b>Всего пользователей:</b> <code>{total}</code>\n"
                f"💬 <b>Всего анонимных сообщений:</b> <code>{msgs}</code>\n"
                f"🚫 <b>Заблокированных:</b> <code>{blocked}</code>\n\n"
                f"🔥 <i>Бот живёт и развивается!</i> ✨",
                reply_markup=admin_menu)
            return

        if text == "📨 Рассылка":
            bot.send_message(user_id, "📨 <b>Рассылка по всем пользователям</b>\n\nОтправь сообщение — оно уйдёт каждому!", reply_markup=cancel_menu)
            waiting_message[user_id] = "broadcast"
            return

        if text in ["🔥 Топ-10 пользователей", "🔥 Топ-10"]:
            show_top10(user_id, True)
            return

        if text == "🔍 Проверка пользователя":
            bot.send_message(user_id, "🔍 <b>Проверка пользователя</b>\n\nВведи <b>ID</b> или <b>@username</b>:", reply_markup=cancel_menu)
            waiting_message[user_id] = "check_user"
            return

        if text == "🚫 Заблокировать":
            bot.send_message(user_id, "🚫 <b>Блокировка пользователя</b>\n\nВведи <b>ID</b>:", reply_markup=cancel_menu)
            waiting_message[user_id] = "block_user"
            return

        if text == "✅ Разблокировать":
            bot.send_message(user_id, "✅ <b>Разблокировка пользователя</b>\n\nВведи <b>ID</b>:", reply_markup=cancel_menu)
            waiting_message[user_id] = "unblock_user"
            return

        if text == "⬅️ Назад в главное меню":
            bot.send_message(user_id, "🏠 Возвращаемся в главное меню", reply_markup=get_main_menu(True))
            return

        # Админ действия
        if waiting_message.get(user_id) == "check_user":
            target = resolve_user_id(text)
            if target:
                show_user_profile(user_id, target)
            else:
                bot.send_message(user_id, "❌ <b>Пользователь не найден</b>\nПроверь ID или username")
            waiting_message.pop(user_id, None)
            return

        if waiting_message.get(user_id) == "block_user":
            if text.isdigit():
                block_user(int(text))
                bot.send_message(user_id, f"🚫 <b>Пользователь заблокирован</b>\n<code>{text}</code>", reply_markup=admin_menu)
            else:
                bot.send_message(user_id, "❌ Введи только цифры ID")
            waiting_message.pop(user_id, None)
            return

        if waiting_message.get(user_id) == "unblock_user":
            if text.isdigit():
                unblock_user(int(text))
                bot.send_message(user_id, f"✅ <b>Пользователь разблокирован</b>\n<code>{text}</code>", reply_markup=admin_menu)
            else:
                bot.send_message(user_id, "❌ Введи только цифры ID")
            waiting_message.pop(user_id, None)
            return

        if waiting_message.get(user_id) == "broadcast":
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("SELECT user_id FROM users")
            users = [r[0] for r in c.fetchall()]
            conn.close()
            sent = failed = 0
            for uid in users:
                try:
                    bot.copy_message(uid, user_id, message.message_id)
                    sent += 1
                except:
                    failed += 1
                time.sleep(0.05)
            bot.send_message(user_id, 
                f"📨 <b>РАССЫЛКА ЗАВЕРШЕНА</b>\n\n"
                f"✅ Успешно доставлено: <code>{sent}</code>\n"
                f"❌ Не доставлено: <code>{failed}</code>\n\n"
                f"🔥 <i>Все уведомлены!</i>",
                reply_markup=admin_menu)
            waiting_message.pop(user_id, None)
            return

    # === Ручной анонимный ответ ===
    if waiting_message.get(user_id) == "manual_reply":
        if text.isdigit():
            target = int(text)
            waiting_message[user_id] = target
            bot.send_message(user_id, "🕶 <b>Пиши анонимное сообщение</b> — текст, фото, видео, всё подойдёт!", reply_markup=cancel_menu)
        else:
            bot.send_message(user_id, "❌ <b>Ошибка:</b> введи только цифры ID")
        return

    # === Отправка анонимки ===
    if user_id in waiting_message and isinstance(waiting_message[user_id], int):
        target_id = waiting_message.pop(user_id)
        if is_blocked(target_id):
            bot.send_message(user_id, "🚫 <b>Этот пользователь заблокирован</b>")
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
                bot.send_message(target_id, f"🕶️ <b>Анонимное сообщение</b> ✨\n\n{content_text}", reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id, reply_markup=markup)
                if content_type != 'sticker':
                    bot.send_message(target_id, "🕶️ <b>Анонимное сообщение</b> ✨", reply_to_message_id=copied.message_id)
        except:
            bot.send_message(user_id, "❌ <b>Не удалось доставить</b>\nПользователь заблокировал бота или удалил аккаунт")

        bot.send_message(user_id, "✅ <b>Сообщение успешно отправлено анонимно!</b> 🔥", reply_markup=get_main_menu(is_admin))
        return

# ====== Callback обработка ======
@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    user_id = call.from_user.id
    if is_blocked(user_id):
        bot.answer_callback_query(call.id, "🚫 Доступ ограничен")
        return

    if call.data == "ignore":
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Игнорировано")

    elif call.data.startswith("reply_"):
        sender_id = int(call.data.split("_")[1])
        if last_message_time.get(user_id, 0) + ANTISPAM_INTERVAL > time.time():
            bot.answer_callback_query(call.id, "⏱ Подожди немного")
            return
        waiting_message[user_id] = sender_id
        last_message_time[user_id] = time.time()
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        bot.send_message(user_id, "🕶️ <b>Напиши ответ анонимно</b> — он уйдёт мгновенно!", reply_markup=cancel_menu)

    elif call.data.startswith("sup_") and user_id == ADMIN_ID:
        target = int(call.data.split("_")[-1])
        if call.data.startswith("sup_ignore_"):
            bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
            bot.answer_callback_query(call.id, "Игнорировано")
        elif call.data.startswith("sup_reply_"):
            bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
            bot.send_message(ADMIN_ID, 
                             f"✉️ <b>ОТВЕТ ПОЛЬЗОВАТЕЛЮ</b>\n\n"
                             f"ID: <code>{target}</code>\n\n"
                             f"Отправь любое сообщение (текст, фото, видео, голосовое...) — оно уйдёт от имени бота!",
                             reply_markup=cancel_menu)
            waiting_message[ADMIN_ID] = f"admin_reply_{target}"

@bot.message_handler(func=lambda m: m.from_user.id == ADMIN_ID and str(waiting_message.get(ADMIN_ID, "")).startswith("admin_reply_"))
def admin_support_reply(message):
    target_id = int(waiting_message.pop(ADMIN_ID).split("_")[2])
    try:
        bot.copy_message(target_id, ADMIN_ID, message.message_id)
        bot.send_message(ADMIN_ID, "✅ <b>Ответ успешно отправлен пользователю!</b> 🚀", reply_markup=admin_menu)
    except Exception as e:
        bot.send_message(ADMIN_ID, "❌ <b>Не удалось отправить</b>\nВозможно, пользователь заблокировал бота.")

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
