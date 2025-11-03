import os
import re
import sqlite3
import telebot
from datetime import datetime, timedelta
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("PLAY")
CHANNEL = os.getenv("CHANNEL") or "@vzref2"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "7902738665")
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID") or "-1001234567890")

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)
DB_PATH = "data.db"

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                channel TEXT,
                expires TEXT
            )
        """)
        db.commit()

def now_iso():
    return datetime.now().isoformat()

def fmt_dt_iso(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M:%S")
    except:
        return iso

def notify_admin(text):
    try:
        bot.send_message(ADMIN_CHANNEL_ID, text)
    except:
        pass

def channel_normalize(v):
    if not v:
        return None
    v = v.strip()
    if v.startswith("@"):
        v = v[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", v):
        return None
    return "@" + v

def bot_is_admin_in(channel):
    try:
        me = bot.get_me()
        member = bot.get_chat_member(channel, me.id)
        return getattr(member, "status", "") in ("administrator", "creator")
    except:
        return False

def channel_exists(channel):
    try:
        return bot.get_chat(channel) is not None
    except:
        return False

def user_subscribed(user_id, channel):
    try:
        m = bot.get_chat_member(channel, user_id)
        return getattr(m, "status", "") not in ("left", "kicked")
    except:
        return False

def save_user_from_msg(msg):
    user = msg.from_user
    user_id = user.id
    username = getattr(user, "username", None)
    first_name = user.first_name or ""
    registered = now_iso()
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,))
        if not cur.fetchone():
            db.execute("INSERT INTO users (user_id, username, first_name, registered) VALUES (?, ?, ?, ?)",
                       (user_id, username, first_name, registered))
            db.commit()
            name_line = f"👤 Ник: @{username}" if username else f"👤 Имя: {first_name}"
            notify_admin(
                "🆕 Новый пользователь\n"
                f"🆔 ID: {user_id}\n"
                f"{name_line}\n"
                f"📅 Время: {datetime.fromisoformat(registered).strftime('%Y-%m-%d %H:%M:%S')}"
            )

def build_subscribe_keyboard(channels):
    kb = InlineKeyboardMarkup()
    row = []
    for i, ch in enumerate(channels, 1):
        url = f"https://t.me/{ch.strip('@')}"
        btn = InlineKeyboardButton("🔗 Подписаться", url=url)
        row.append(btn)
        if i % 2 == 0 or i == len(channels):
            try:
                kb.row(*row)
            except:
                for b in row:
                    kb.add(b)
            row = []
    return kb

def send_subscribe_request(chat_id, channels, text=None):
    txt = text or ("⚠️ Чтобы писать в чат, необходимо подписаться на канал(ы): " + ", ".join(channels))
    kb = build_subscribe_keyboard(channels)
    bot.send_message(chat_id, txt, reply_markup=kb)

def profile_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="profile_back"))
    return kb

def admin_main_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📤 Сделать рассылку", callback_data="admin_broadcast"),
           InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    kb.row(InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
           InlineKeyboardButton("🧹 Очистить просроченные", callback_data="admin_cleanup"))
    kb.row(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    return kb

@bot.message_handler(commands=["start"])
def start(msg):
    if msg.chat.type in ("group", "supergroup"):
        if any(member.user and member.user.id == bot.get_me().id for member in getattr(msg, "new_chat_members", [])):
            notify_admin(
                "➕ Бот добавлен в чат\n"
                f"📍 Чат: {msg.chat.title}\n"
                f"🆔 Chat ID: {msg.chat.id}\n"
                f"👤 Инициатор: @{msg.from_user.username if getattr(msg.from_user, 'username', None) else msg.from_user.first_name}\n"
                f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        bot.send_message(msg.chat.id,
                         "👋 Я бот‑фильтр. Для настройки используйте /admin в личных сообщениях с админом.",
                         reply_markup=None)
    else:
        save_user_from_msg(msg)
        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute("SELECT DISTINCT channel FROM required_subs").fetchall()
        channels = [ch for (ch,) in rows] or [CHANNEL]
        unsub = [ch for ch in channels if not user_subscribed(msg.from_user.id, ch)]
        if unsub:
            send_subscribe_request(msg.chat.id, unsub, text="⚠️ Чтобы продолжить, подпишитесь на канал(ы): " + ", ".join(unsub))
        else:
            kb = InlineKeyboardMarkup()
            kb.add(InlineKeyboardButton("💳 Профиль", callback_data="show_profile"))
            bot.send_message(msg.chat.id, "*📘 Инструкция:*\n\n"
                             "1) Добавьте бота в группу и дайте права администратора.\n"
                             "2) В группе используйте `/setup @канал 24h` для добавления ОП.\n"
                             "3) В личке нажмите «💳 Профиль» для просмотра данных.",
                             parse_mode="Markdown",
                             reply_markup=kb)

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(msg):
    save_user_from_msg(msg)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💳 Профиль", callback_data="show_profile"))
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("SELECT DISTINCT channel FROM required_subs").fetchall()
    channels = [ch for (ch,) in rows] or [CHANNEL]
    unsub = [ch for ch in channels if not user_subscribed(msg.from_user.id, ch)]
    if unsub:
        send_subscribe_request(msg.chat.id, unsub, text="⚠️ Чтобы продолжить, подпишитесь на канал(ы): " + ", ".join(unsub))
    else:
        bot.send_message(msg.chat.id, "*📘 Главное меню:*\n\nНажмите кнопку ниже для профиля.", parse_mode="Markdown", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: True)
def callback_query(c):
    data = c.data
    uid = c.from_user.id
    if data == "show_profile":
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("SELECT username, first_name, registered FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row:
            bot.answer_callback_query(c.id, "Профиль не найден", show_alert=True)
            return
        username, first_name, reg = row
        name = f"@{username}" if username else first_name
        text = ("*💳 Ваш профиль*\n"
                "━━━━━━━━━━━━━━━\n"
                f"🆔 ID: {uid}\n"
                f"👤 Ник: {name}\n"
                f"📅 Регистрация: {fmt_dt_iso(reg)}\n"
                "━━━━━━━━━━━━━━━")
        bot.edit_message_text(text, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=profile_keyboard())
        bot.answer_callback_query(c.id)
        return
    if data == "profile_back":
        bot.edit_message_text("*📘 Главное меню:*\n\nНажмите кнопку ниже для профиля.", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("💳 Профиль", callback_data="show_profile")))
        bot.answer_callback_query(c.id)
        return
    if data.startswith("admin_"):
        if c.from_user.id != ADMIN_ID:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
            return
        if data == "admin_broadcast":
            bot.send_message(ADMIN_ID, "Отправьте текст рассылки в ответном сообщении.")
            bot.answer_callback_query(c.id)
            return
        if data == "admin_stats":
            with sqlite3.connect(DB_PATH) as db:
                users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                groups = db.execute("SELECT COUNT(DISTINCT chat_id) FROM required_subs").fetchone()[0]
                ops = db.execute("SELECT COUNT(*) FROM required_subs").fetchone()[0]
            text = ("*📊 Статистика*\n"
                    "━━━━━━━━━━━━━━━\n"
                    f"👤 Пользователей: {users}\n"
                    f"💬 Групп: {groups}\n"
                    f"📡 Активных ОП: {ops}\n"
                    "━━━━━━━━━━━━━━━")
            bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=admin_main_keyboard())
            bot.answer_callback_query(c.id)
            return
        if data == "admin_users":
            with sqlite3.connect(DB_PATH) as db:
                rows = db.execute("SELECT user_id, username, first_name, registered FROM users ORDER BY registered DESC LIMIT 10").fetchall()
            kb = InlineKeyboardMarkup()
            for u_id, uname, fname, reg in rows:
                label = f"@{uname}" if uname else (fname or str(u_id))
                kb.add(InlineKeyboardButton(label, callback_data=f"view_user_{u_id}"))
            kb.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
            bot.send_message(ADMIN_ID, "*👥 Последние пользователи:*", parse_mode="Markdown", reply_markup=kb)
            bot.answer_callback_query(c.id)
            return
        if data == "admin_cleanup":
            now = datetime.now().isoformat()
            with sqlite3.connect(DB_PATH) as db:
                db.execute("DELETE FROM required_subs WHERE expires IS NOT NULL AND expires < ?", (now,))
                db.commit()
            bot.send_message(ADMIN_ID, "🧹 Просроченные ОП очищены.", reply_markup=admin_main_keyboard())
            bot.answer_callback_query(c.id)
            return
        if data == "admin_back":
            bot.edit_message_text("*🛠 Меню админа*", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=admin_main_keyboard())
            bot.answer_callback_query(c.id)
            return
    if data.startswith("view_user_"):
        if c.from_user.id != ADMIN_ID:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
            return
        user_id = int(data.split("_", 2)[2])
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("SELECT username, first_name, registered FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            bot.answer_callback_query(c.id, "Пользователь не найден", show_alert=True)
            return
        username, first_name, reg = row
        name = f"@{username}" if username else first_name
        with sqlite3.connect(DB_PATH) as db:
            subs = db.execute("SELECT chat_id, channel, expires FROM required_subs").fetchall()
        user_ops = []
        for chat_id, channel, expires in subs:
            try:
                m = bot.get_chat_member(chat_id, user_id)
                if getattr(m, "status", "") not in ("left", "kicked"):
                    dt = fmt_dt_iso(expires) if expires else "∞"
                    user_ops.append(f"{channel} — до {dt}")
            except:
                continue
        ops_text = "\n".join(user_ops) if user_ops else "Нет активных ОП"
        text = ("*👤 Пользователь:*\n"
                f"🆔 ID: {user_id}\n"
                f"👤 Ник: {name}\n"
                f"📅 Зарегистрирован: {fmt_dt_iso(reg)}\n\n"
                "*📡 Активные ОП:*\n"
                f"{ops_text}")
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_users"))
        bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
        bot.answer_callback_query(c.id)
        return

@bot.message_handler(commands=["admin"])
def admin(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    bot.send_message(ADMIN_ID, "*🛠 Меню админа*", parse_mode="Markdown", reply_markup=admin_main_keyboard())

@bot.message_handler(commands=["setup"])
def setup(msg):
    if msg.chat.type == "private":
        return
    try:
        member = bot.get_chat_member(msg.chat.id, msg.from_user.id)
    except:
        return
    if getattr(member, "status", "") not in ("administrator", "creator"):
        return
    args = msg.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(msg, "Использование: /setup @канал 24h")
        return
    raw_ch, dur = args[1], args[2]
    channel = channel_normalize(raw_ch)
    if not channel or not channel_exists(channel):
        bot.reply_to(msg, f"⛔️ Канал {raw_ch} не найден")
        return
    if not bot_is_admin_in(channel):
        bot.reply_to(msg, f"⛔️ Бот не администратор в {channel}")
        return
    m = re.fullmatch(r"(\d+)\s*([smhd])", dur, re.IGNORECASE)
    if not m:
        bot.reply_to(msg, "⛔️ Неверный формат времени. Примеры: 30s 15m 12h 7d")
        return
    num, unit = int(m.group(1)), m.group(2).lower()
    delta = {"s": timedelta(seconds=num), "m": timedelta(minutes=num), "h": timedelta(hours=num), "d": timedelta(days=num)}[unit]
    expires = (datetime.now() + delta).isoformat()
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel)).fetchone()
        if cur:
            bot.reply_to(msg, f"⚠️ Канал {channel} уже в ОП")
            return
        db.execute("INSERT INTO required_subs (chat_id, channel, expires) VALUES (?, ?, ?)", (msg.chat.id, channel, expires))
        db.commit()
    bot.reply_to(msg, f"✅ Добавлено: {channel} до {fmt_dt_iso(expires)}")

@bot.message_handler(commands=["unsetup"])
def unsetup(msg):
    if msg.chat.type == "private":
        return
    try:
        member = bot.get_chat_member(msg.chat.id, msg.from_user.id)
    except:
        return
    if getattr(member, "status", "") not in ("administrator", "creator"):
        return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(msg, "Использование: /unsetup @канал")
        return
    channel = channel_normalize(args[1])
    if not channel:
        bot.reply_to(msg, "⛔️ Неверный формат канала")
        return
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel)).fetchone()
        if not cur:
            bot.reply_to(msg, f"⛔️ {channel} не добавлен")
            return
        db.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        db.commit()
    bot.reply_to(msg, f"✅ Убрано {channel}")

@bot.message_handler(commands=["status"])
def status(msg):
    if msg.chat.type == "private":
        return
    try:
        member = bot.get_chat_member(msg.chat.id, msg.from_user.id)
    except:
        return
    if getattr(member, "status", "") not in ("administrator", "creator"):
        return
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM required_subs WHERE expires IS NOT NULL AND expires < ?", (now,))
        rows = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (msg.chat.id,)).fetchall()
    if not rows:
        bot.send_message(msg.chat.id, "📋 Активных обязательных подписок нет.")
        return
    lines = ["*📋 Активные проверки:*"]
    for i, (channel, expires) in enumerate(rows, 1):
        dt = fmt_dt_iso(expires) if expires else "∞"
        lines.append(f"{i}. {channel} — до {dt}")
        lines.append(f"Убрать ОП — `/unsetup {channel}`")
        lines.append("———————————————")
    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def check_message(msg):
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires < ?", (chat_id, now))
        subs = db.execute("SELECT channel FROM required_subs WHERE chat_id=?", (chat_id,)).fetchall()
    channels = [ch for (ch,) in subs]
    if not channels:
        return
    valid = []
    for ch in channels:
        if not channel_exists(ch):
            continue
        if not bot_is_admin_in(ch):
            continue
        valid.append(ch)
    if not valid:
        return
    not_subscribed = [ch for ch in valid if not user_subscribed(user_id, ch)]
    if not not_subscribed:
        return
    try:
        bot.delete_message(chat_id, msg.message_id)
    except:
        pass
    name = f"@{msg.from_user.username}" if getattr(msg.from_user, "username", None) else msg.from_user.first_name
    text = f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {', '.join(not_subscribed)}"
    kb = build_subscribe_keyboard(not_subscribed)
    bot.send_message(chat_id, text, reply_markup=kb)
    notify_admin("⚠️ Удалено сообщение пользователя " + str(user_id) + " в чате " + str(chat_id) + " из-за отсутствия подписки.")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.from_user.id == ADMIN_ID, content_types=['text'])
def admin_broadcast_handler(msg):
    if msg.reply_to_message and msg.reply_to_message.text == "Отправьте текст рассылки в ответном сообщении.":
        text = msg.text
        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute("SELECT user_id FROM users").fetchall()
        user_ids = [r[0] for r in rows]
        sent = 0
        for uid in user_ids:
            try:
                bot.send_message(uid, text)
                sent += 1
            except:
                continue
        notify_admin("📤 Рассылка запущена\n" f"👥 Получателей: {len(user_ids)}\n" f"📝 Текст: {text}\n" f"📅 Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        bot.send_message(ADMIN_ID, f"Рассылка отправлена. Отправлено: {sent}/{len(user_ids)}")

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "OK", 200

if __name__ == "__main__":
    init_db()
    bot.remove_webhook()
    webhook_url = os.getenv("RENDER_EXTERNAL_URL")
    if webhook_url:
        bot.set_webhook(url=f"{webhook_url.rstrip('/')}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
