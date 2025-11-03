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
last_private_message = {}
init_done = False

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

def fmt_dt(dt):
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except:
            return dt
    return dt.strftime("%Y-%m-%d %H:%M")

def notify_admin(text):
    try:
        bot.send_message(ADMIN_CHANNEL_ID, text)
    except:
        pass

def normalize_channel(value):
    if not value:
        return None
    v = value.strip()
    if v.startswith("@"):
        v = v[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", v):
        return None
    return "@" + v

def channel_exists(channel):
    try:
        bot.get_chat(channel)
        return True
    except:
        return False

def bot_is_admin_in(channel):
    try:
        me = bot.get_me()
        member = bot.get_chat_member(channel, me.id)
        return getattr(member, "status", "") in ("administrator", "creator")
    except:
        return False

def user_subscribed(user_id, channel):
    try:
        m = bot.get_chat_member(channel, user_id)
        return getattr(m, "status", "") not in ("left", "kicked")
    except:
        return False

def save_user(user):
    uid = user.id
    username = getattr(user, "username", None)
    first_name = getattr(user, "first_name", "") or ""
    reg = now_iso()
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM users WHERE user_id=?", (uid,))
        if not cur.fetchone():
            db.execute("INSERT INTO users (user_id, username, first_name, registered) VALUES (?, ?, ?, ?)",
                       (uid, username, first_name, reg))
            db.commit()
            name_line = f"@{username}" if username else first_name
            notify_admin(
                "🆕 Новый пользователь\n"
                f"🆔 ID: {uid}\n"
                f"👤 {name_line}\n"
                f"📅 Время: {fmt_dt(reg)}"
            )

def build_rowed_keyboard(buttons, per_row=2):
    kb = InlineKeyboardMarkup()
    row = []
    for i, b in enumerate(buttons, 1):
        row.append(b)
        if i % per_row == 0 or i == len(buttons):
            try:
                kb.row(*row)
            except:
                for bb in row:
                    kb.add(bb)
            row = []
    return kb

def send_private_replace(chat_id, text, reply_markup=None, parse_mode=None, disable_preview=True):
    try:
        old_id = last_private_message.get(chat_id)
        if old_id:
            try:
                bot.delete_message(chat_id, old_id)
            except:
                pass
    except:
        pass
    m = bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode, disable_web_page_preview=disable_preview)
    last_private_message[chat_id] = m.message_id
    return m

def send_subscribe_request(chat_id, channels):
    text = "⚠️ *Чтобы пользоваться ботом, нужно подписаться на канал:*"
    buttons = []
    for ch in channels:
        uv = ch.strip("@")
        url = f"https://t.me/{uv}"
        buttons.append(InlineKeyboardButton("🔗 Подписаться", url=url))
    buttons.append(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
    kb = build_rowed_keyboard(buttons, per_row=2)
    return send_private_replace(chat_id, text, reply_markup=kb, parse_mode="Markdown")

def private_intro_text():
    return (
        "*📘 Инструкция по настройке:*\n\n"
        "*1️⃣ Добавь меня в группу/чат и сделай админом.*\n\n"
        "*2️⃣ В группе/чате используй:*\n"
        "`/setup @канал 24h` — добавить обязательную подписку.\n"
        "⏱ *Формат времени:* 30s, 15m, 12h, 7d\n\n"
        "`/unsetup @канал` — убрать подписку.\n"
        "`/status` — список активных проверок.\n\n"
        "*ℹ️ Как это работает:*\n"
        "• Пользователь пишет сообщение в чат.\n"
        "• Бот проверяет его подписку.\n"
        "• Если подписка есть — *сообщение остаётся*.\n"
        "• Если нет — *сообщение удаляется*, а пользователю отправляется кнопка 🔗 Подписаться.\n\n"
        "———————————————\n\n"
        "💡 Используя этого бота, вы подтверждаете согласие с политикой конфиденциальности.\n"
        f"*📎 Наш канал:* https://t.me/{CHANNEL.strip('@')}"
    )

def admin_main_keyboard():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("📤 Сделать рассылку", callback_data="admin_broadcast"),
        InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    )
    kb.row(
        InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        InlineKeyboardButton("🧹 Очистить просроченные", callback_data="admin_cleanup")
    )
    kb.row(InlineKeyboardButton("🔙 Назад", callback_data="admin_back"))
    return kb

def profile_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="profile_back"))
    return kb

@bot.message_handler(commands=["start"])
def start(msg):
    save_user(msg.from_user)
    if msg.chat.type in ("group", "supergroup"):
        bot.send_message(msg.chat.id,
                         "👋 *Привет, я бот‑фильтр.*\n"
                         "Я проверяю обязательные подписки и *удаляю сообщения* тех, кто не подписан.\n\n"
                         "📌 *Для настройки напиши мне в личку.*",
                         parse_mode="Markdown")
        return
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("SELECT DISTINCT channel FROM required_subs").fetchall()
    channels = [ch for (ch,) in rows] or [CHANNEL]
    unsub = [ch for ch in channels if not user_subscribed(msg.from_user.id, ch)]
    if unsub:
        send_subscribe_request(msg.chat.id, unsub)
    else:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💳 Профиль", callback_data="show_profile"))
        send_private_replace(msg.chat.id, private_intro_text(), reply_markup=kb, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(msg):
    save_user(msg.from_user)
    with sqlite3.connect(DB_PATH) as db:
        rows = db.execute("SELECT DISTINCT channel FROM required_subs").fetchall()
    channels = [ch for (ch,) in rows] or [CHANNEL]
    unsub = [ch for ch in channels if not user_subscribed(msg.from_user.id, ch)]
    if unsub:
        send_subscribe_request(msg.chat.id, unsub)
    else:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💳 Профиль", callback_data="show_profile"))
        send_private_replace(msg.chat.id, private_intro_text(), reply_markup=kb, parse_mode="Markdown")

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
        text = (
            "*💳 Ваш профиль*\n"
            "━━━━━━━━━━━━━━━━\n"
            f"🆔 ID: {uid}\n"
            f"👤 Ник: {name}\n"
            f"📅 Регистрация: *{fmt_dt(reg)}*\n"
            "━━━━━━━━━━━━━━━━"
        )
        try:
            bot.edit_message_text(text, c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=profile_keyboard())
        except:
            send_private_replace(c.message.chat.id, text, reply_markup=profile_keyboard(), parse_mode="Markdown")
        bot.answer_callback_query(c.id)
        return
    if data == "profile_back":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("💳 Профиль", callback_data="show_profile"))
        try:
            bot.edit_message_text("*📘 Главное меню:*\n\nНажмите кнопку ниже для профиля.", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=kb)
        except:
            send_private_replace(c.message.chat.id, "*📘 Главное меню:*\n\nНажмите кнопку ниже для профиля.", reply_markup=kb, parse_mode="Markdown")
        bot.answer_callback_query(c.id)
        return
    if data == "check_sub":
        with sqlite3.connect(DB_PATH) as db:
            rows = db.execute("SELECT DISTINCT channel FROM required_subs").fetchall()
        channels = [ch for (ch,) in rows] or [CHANNEL]
        unsub = [ch for ch in channels if not user_subscribed(uid, ch)]
        if not unsub:
            text = "✅ *Спасибо! Подписка подтверждена.*\n\n" + private_intro_text()
            try:
                bot.edit_message_text(text, c.message.chat.id, c.message.message_id, parse_mode="Markdown")
            except:
                send_private_replace(c.message.chat.id, text, parse_mode="Markdown")
            bot.answer_callback_query(c.id)
        else:
            send_subscribe_request(c.message.chat.id, unsub)
            bot.answer_callback_query(c.id, "Ещё не подписаны", show_alert=True)
        return
    if data.startswith("admin_"):
        if c.from_user.id != ADMIN_ID:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
            return
        if data == "admin_back":
            try:
                bot.edit_message_text("*🛠 Меню админа*\n\nВыберите действие:", c.message.chat.id, c.message.message_id, parse_mode="Markdown", reply_markup=admin_main_keyboard())
            except:
                bot.send_message(ADMIN_ID, "*🛠 Меню админа*\n\nВыберите действие:", parse_mode="Markdown", reply_markup=admin_main_keyboard())
            bot.answer_callback_query(c.id)
            return
        if data == "admin_stats":
            with sqlite3.connect(DB_PATH) as db:
                users = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                groups = db.execute("SELECT COUNT(DISTINCT chat_id) FROM required_subs").fetchone()[0]
                ops = db.execute("SELECT COUNT(*) FROM required_subs").fetchone()[0]
            text = (
                "*📊 Статистика*\n"
                "━━━━━━━━━━━━━━━━\n"
                f"👤 Пользователей: *{users}*\n"
                f"💬 Групп: *{groups}*\n"
                f"📡 Активных ОП: *{ops}*\n"
                "━━━━━━━━━━━━━━━━"
            )
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
            bot.send_message(ADMIN_ID, "🧹 *Просроченные ОП очищены.*", parse_mode="Markdown", reply_markup=admin_main_keyboard())
            bot.answer_callback_query(c.id)
            return
    if data.startswith("view_user_"):
        if c.from_user.id != ADMIN_ID:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
            return
        try:
            user_id = int(data.split("_", 2)[2])
        except:
            bot.answer_callback_query(c.id, "Ошибка", show_alert=True)
            return
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute("SELECT username, first_name, registered FROM users WHERE user_id=?", (user_id,)).fetchone()
            subs = db.execute("SELECT chat_id, channel, expires FROM required_subs").fetchall()
        if not row:
            bot.answer_callback_query(c.id, "Пользователь не найден", show_alert=True)
            return
        username, first_name, reg = row
        name = f"@{username}" if username else first_name
        user_ops = []
        for chat_id, channel, expires in subs:
            try:
                m = bot.get_chat_member(chat_id, user_id)
                if getattr(m, "status", "") not in ("left", "kicked"):
                    dt = fmt_dt(expires) if expires else "∞"
                    user_ops.append(f"{channel} — до {dt}")
            except:
                continue
        ops_text = "\n".join(user_ops) if user_ops else "Нет активных ОП"
        text = (
            "*👤 Пользователь:*\n"
            f"🆔 ID: {user_id}\n"
            f"👤 Ник: {name}\n"
            f"📅 Зарегистрирован: *{fmt_dt(reg)}*\n\n"
            "*📡 Активные ОП:*\n"
            f"{ops_text}"
        )
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="admin_users"))
        bot.send_message(ADMIN_ID, text, parse_mode="Markdown", reply_markup=kb)
        bot.answer_callback_query(c.id)
        return
    bot.answer_callback_query(c.id)

@bot.message_handler(commands=["admin"])
def admin_cmd(msg):
    if msg.from_user.id != ADMIN_ID:
        return
    bot.send_message(ADMIN_ID, "*🛠 Меню админа*\n\nВыберите действие:", parse_mode="Markdown", reply_markup=admin_main_keyboard())

def parse_duration(spec):
    if not spec:
        return None
    m = re.fullmatch(r"(\d+)\s*([smhd])", spec.strip(), re.IGNORECASE)
    if not m:
        return None
    num, unit = int(m.group(1)), m.group(2).lower()
    return {"s": timedelta(seconds=num), "m": timedelta(minutes=num), "h": timedelta(hours=num), "d": timedelta(days=num)}.get(unit)

@bot.message_handler(commands=["setup"])
def setup(msg):
    if msg.chat.type == "private":
        send_subscribe_request(msg.chat.id, [CHANNEL])
        return
    try:
        member = bot.get_chat_member(msg.chat.id, msg.from_user.id)
    except:
        return
    if getattr(member, "status", "") not in ("administrator", "creator"):
        return
    args = msg.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(msg, "Использование: `/setup @канал 24h`", parse_mode="Markdown")
        return
    raw_channel, duration = args[1], args[2]
    if raw_channel.startswith("-100"):
        bot.reply_to(msg, "⛔️ *Нельзя использовать ID канала. Укажи @username.*", parse_mode="Markdown")
        return
    channel = normalize_channel(raw_channel)
    if not channel:
        bot.reply_to(msg, "⛔️ *Неверный формат канала.* Пример: `@example_channel`", parse_mode="Markdown")
        return
    if not channel_exists(channel):
        bot.reply_to(msg, f"⛔️ *Канал {channel} не найден в Telegram.*", parse_mode="Markdown")
        return
    if not bot_is_admin_in(channel):
        bot.reply_to(msg, f"⛔️ *Бот не администратор канала {channel}.* Добавьте бота в админы канала.", parse_mode="Markdown")
        return
    delta = parse_duration(duration)
    if not delta:
        bot.reply_to(msg, "⛔️ *Неверный формат времени.* Примеры: `30s`, `15m`, `12h`, `7d`", parse_mode="Markdown")
        return
    expires = (datetime.now() + delta).isoformat()
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        if cur.fetchone():
            bot.reply_to(msg, f"⚠️ *Канал {channel} уже добавлен* в обязательные подписки.", parse_mode="Markdown")
            return
        db.execute("INSERT INTO required_subs (chat_id, channel, expires) VALUES (?, ?, ?)", (msg.chat.id, channel, expires))
        db.commit()
    bot.reply_to(msg, f"✅ *Добавлено обязательное условие:* подписка на {channel} до *{fmt_dt(expires)}*", parse_mode="Markdown")

@bot.message_handler(commands=["unsetup"])
def unsetup(msg):
    if msg.chat.type == "private":
        send_subscribe_request(msg.chat.id, [CHANNEL])
        return
    try:
        member = bot.get_chat_member(msg.chat.id, msg.from_user.id)
    except:
        return
    if getattr(member, "status", "") not in ("administrator", "creator"):
        return
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(msg, "Использование: `/unsetup @канал`", parse_mode="Markdown")
        return
    channel = normalize_channel(args[1])
    if not channel:
        bot.reply_to(msg, "⛔️ *Неверный формат канала.* Пример: `@example_channel`", parse_mode="Markdown")
        return
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        if not cur.fetchone():
            bot.reply_to(msg, f"⛔️ *Канал {channel} не добавлен* в обязательные подписки для этого чата.", parse_mode="Markdown")
            return
        db.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        db.commit()
    bot.reply_to(msg, f"✅ *Убрано обязательное условие* с {channel}", parse_mode="Markdown")

@bot.message_handler(commands=["status"])
def status(msg):
    if msg.chat.type == "private":
        send_subscribe_request(msg.chat.id, [CHANNEL])
        return
    try:
        member = bot.get_chat_member(msg.chat.id, msg.from_user.id)
    except:
        return
    if getattr(member, "status", "") not in ("administrator", "creator"):
        return
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires < ?", (msg.chat.id, now))
        rows = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (msg.chat.id,)).fetchall()
    if not rows:
        bot.send_message(msg.chat.id, "📋 *Активных обязательных подписок нет.*", parse_mode="Markdown")
        return
    lines = [f"*📋 Активные проверки ({len(rows)}):*"]
    for i, (channel, expires) in enumerate(rows, 1):
        dt = fmt_dt(expires) if expires else "∞"
        lines.append(f"{i}. *{channel}* — до *{dt}*")
        lines.append(f"Убрать ОП — `/unsetup {channel}`")
        lines.append("———————————————")
    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def check(msg):
    if getattr(msg, "from_user", None) is None:
        return
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires < ?", (chat_id, now))
        subs = db.execute("SELECT channel FROM required_subs WHERE chat_id=?", (chat_id,)).fetchall()
    if not subs:
        return
    required = []
    for (ch,) in subs:
        if not channel_exists(ch):
            continue
        if not bot_is_admin_in(ch):
            continue
        required.append(ch)
    if not required:
        return
    not_subscribed = [ch for ch in required if not user_subscribed(user_id, ch)]
    if not not_subscribed:
        return
    try:
        bot.delete_message(chat_id, msg.message_id)
    except:
        pass
    name = f"@{msg.from_user.username}" if getattr(msg.from_user, "username", None) else msg.from_user.first_name
    text = f"{name}, *чтобы писать в чат*, необходимо подписаться на канал(ы): {', '.join(not_subscribed)}"
    buttons = []
    for ch in not_subscribed:
        buttons.append(InlineKeyboardButton("🔗 Подписаться", url=f"https://t.me/{ch.strip('@')}"))
    kb = build_rowed_keyboard(buttons, per_row=2)
    bot.send_message(chat_id, text, reply_markup=kb, parse_mode="Markdown")
    notify_admin(f"⚠️ Удалено сообщение пользователя {user_id} в чате {chat_id} — не подписан на {', '.join(not_subscribed)}")

@bot.message_handler(func=lambda m: m.chat.type == "private" and m.from_user.id == ADMIN_ID, content_types=['text'])
def admin_broadcast_handler(msg):
    if msg.reply_to_message and "Отправьте текст рассылки" in (msg.reply_to_message.text or ""):
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
        notify_admin("📤 Рассылка запущена\n" f"👥 Получателей: {len(user_ids)}\n" f"📅 Время: {fmt_dt(now_iso())}")
        bot.send_message(ADMIN_ID, f"✅ Рассылка отправлена. Отправлено: {sent}/{len(user_ids)}")

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = telebot.types.Update.de_json(request.stream.read().decode("utf-8"))
    bot.process_new_updates([update])
    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Бот работает", 200

if __name__ == "__main__":
    init_db()
    bot.remove_webhook()
    webhook_url = os.getenv("RENDER_EXTERNAL_URL")
    if webhook_url:
        bot.set_webhook(url=f"{webhook_url.rstrip('/')}/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
