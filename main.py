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
waiting_message = {}        # Для анонимных сообщений и ручного ответа
admin_reply_mode = {}       # Новый: для ответа в поддержку (ADMIN_ID -> target_user_id)
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

    # === Отмена в любом режиме ===
    if text == "❌ Отмена":
        waiting_message.pop(user_id, None)
        if user_id == ADMIN_ID and ADMIN_ID in admin_reply_mode:
            admin_reply_mode.pop(ADMIN_ID)
            bot.send_message(user_id, "❌ <b>ДЕЙСТВИЕ ОТМЕНЕНО</b>\n\nРежим ответа в поддержку завершён.", reply_markup=admin_menu)
        else:
            bot.send_message(user_id, "❌ <b>ДЕЙСТВИЕ ОТМЕНЕНО</b>\n\nВозвращаемся в главное меню! 🏠", reply_markup=get_main_menu(is_admin))
        return

    # === ПОДДЕРЖКА: Вход ===
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

    # === ПОДДЕРЖКА: Отправка сообщения админу ===
    if waiting_message.get(user_id) == "support":
        name, username, _, _, _, last = get_user_info(user_id)

        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
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
            f"✨ Пользователь ждёт ответа! Будь на высоте! 🚀"
        )

        forwarded = bot.forward_message(ADMIN_ID, user_id, message.message_id)
        bot.send_message(ADMIN_ID, info_text, reply_to_message_id=forwarded.message_id, reply_markup=kb)

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

    # === АДМИН: Ответ в поддержку ===
    if user_id == ADMIN_ID and ADMIN_ID in admin_reply_mode:
        target_id = admin_reply_mode.pop(ADMIN_ID)

        try:
            if message.content_type == 'text':
                sent = bot.send_message(target_id, message.text)
            else:
                sent = bot.copy_message(target_id, ADMIN_ID, message.message_id)

            bot.send_message(target_id,
                             "✉️ <b>Вам ответил оператор поддержки Anony SMS</b> 👨‍💻✨\n\n"
                             "Если это сообщение пришло по ошибке или не относится к вашему вопросу — просто проигнорируйте.\n"
                             "По всем вопросам всегда пишите в раздел «📩 Поддержка» — мы на связи 24/7! ❤️🚀",
                             reply_to_message_id=sent.message_id)

            bot.send_message(ADMIN_ID,
                             "✅ <b>ОТВЕТ УСПЕШНО ОТПРАВЛЕН!</b> 🎉\n\n"
                             f"Пользователь <code>{target_id}</code> получил сообщение.\n"
                             "Ты — лучший админ! 🔥❤️",
                             reply_markup=admin_menu)
        except Exception as e:
            bot.send_message(ADMIN_ID,
                             f"❌ <b>НЕ УДАЛОСЬ ОТПРАВИТЬ ОТВЕТ</b>\n\n"
                             f"Пользователь {target_id} вероятно заблокировал бота.\n"
                             "Попробуй позже.",
                             reply_markup=admin_menu)
        return

    # === Остальные команды ===
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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""SELECT user_id, messages_received, link_clicks 
                     FROM users 
                     ORDER BY messages_received DESC, link_clicks DESC 
                     LIMIT 10""")
        rows = c.fetchall()
        conn.close()

        if not rows:
            bot.send_message(user_id, "🔥 <b>ТОП-10 ПОКА ПУСТОЙ</b> 😔\n\nАктивность ещё не набрала обороты!")
            return

        text = "🏆 <b>ТОП-10 САМЫХ ПОПУЛЯРНЫХ ПОЛЬЗОВАТЕЛЕЙ ANONY SMS</b> 🔥🔥🔥\n\n"
        for i, (uid, msgs, clicks) in enumerate(rows, 1):
            name, _, _, _, _, _ = get_user_info(uid)
            medal = ["🥇 ПЕРВОЕ МЕСТО!", "🥈 ВТОРОЕ МЕСТО!", "🥉 ТРЕТЬЕ МЕСТО!"][i-1] if i <= 3 else f"<b>{i}-е место</b>"
            text += f"{medal}\n<b>{name}</b> 👤\n💌 Анонимок: <code>{msgs}</code>\n👀 Кликов: <code>{clicks}</code>\n\n"
        text += "🚀 <i>Хочешь в топ? Распространяй ссылку!</i> ✨⭐"
        bot.send_message(user_id, text, reply_markup=get_main_menu(is_admin))

    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ <b>НАСТРОЙКИ ПРИВАТНОСТИ</b> 🔒\n\nВыбери действие:", reply_markup=settings_menu)

    elif text in ["🔕 Отключить приём", "🔔 Включить приём"]:
        status = "ОТКЛЮЧЁН" if "Отключить" in text else "ВКЛЮЧЁН"
        bot.send_message(user_id, f"<b>Приём анонимок {status}!</b>", reply_markup=get_main_menu(is_admin))

    elif text == "⬅️ Назад в меню":
        bot.send_message(user_id, "🏠 Возвращаемся в главное меню!", reply_markup=get_main_menu(is_admin))

    elif text == "ℹ️ Помощь":
        bot.send_message(user_id, "ℹ️ <b>КАК РАБОТАЕТ ANONY SMS?</b>\n\n1. Получи ссылку\n2. Распространи\n3. Получай анонимки\n4. Отвечай анонимно\n5. Поднимайся в топ!\n\nВсё анонимно и безопасно ❤️", reply_markup=get_main_menu(is_admin))

    elif text == "✉️ Ответить анонимно":
        bot.send_message(user_id, "🔍 Введи <b>ID пользователя</b> для ручного ответа (из профиля или топа):", reply_markup=cancel_menu)
        waiting_message[user_id] = "manual_reply"
        return

    # === Анонимная отправка по ссылке ===
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
                bot.send_message(target_id, f"🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ ПРИШЛО!</b> ✨🔥\n\n{text}", reply_markup=markup)
            else:
                copied = bot.copy_message(target_id, user_id, message.message_id)
                bot.send_message(target_id, "🕶️ <b>АНОНИМНОЕ СООБЩЕНИЕ ПРИШЛО!</b> ✨🔥", reply_to_message_id=copied.message_id, reply_markup=markup)
        except:
            bot.send_message(user_id, "❌ Не удалось доставить (пользователь заблокировал бота)")

        bot.send_message(user_id, "✅ <b>СООБЩЕНИЕ ОТПРАВЛЕНО АНОНИМНО!</b> 🎉\nАнонимность 100% 🕶️", reply_markup=get_main_menu(is_admin))
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
        bot.send_message(user_id, "🕶️ <b>НАПИШИ АНОНИМНЫЙ ОТВЕТ</b> 🔥", reply_markup=cancel_menu)
        return

    # Поддержка: Ответить
    if data.startswith("sup_reply_") and user_id == ADMIN_ID:
        target_id = int(data.split("_")[-1])
        admin_reply_mode[ADMIN_ID] = target_id
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)

        name, _, _, _, _, _ = get_user_info(target_id)
        bot.send_message(ADMIN_ID,
                         f"✉️ <b>ОТПРАВЬ ОТВЕТ ПОЛЬЗОВАТЕЛЮ</b>\n\n"
                         f"👤 <b>Имя:</b> {name}\n"
                         f"🆔 <b>ID:</b> <code>{target_id}</code>\n\n"
                         "Любой контент будет отправлен от имени бота с подписью поддержки.",
                         reply_markup=cancel_menu)
        return

    # Поддержка: Игнор
    if data.startswith("sup_ignore_") and user_id == ADMIN_ID:
        bot.edit_message_reply_markup(ADMIN_ID, call.message.message_id, reply_markup=None)
        bot.answer_callback_query(call.id, "Обращение проигнорировано")
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
