import os
import re
import sqlite3
import telebot
from datetime import datetime, timedelta
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("PLAY")
bot = telebot.TeleBot(TOKEN)
DB_PATH = "data.db"
app = Flask(__name__)

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                channel TEXT,
                expires TEXT
            )
        """)

def parse_duration(spec):
    if not spec:
        return None
    m = re.fullmatch(r"(\d+)\s*([smhd])", spec.strip(), re.IGNORECASE)
    if not m:
        return None
    num, unit = int(m.group(1)), m.group(2).lower()
    return {
        "s": timedelta(seconds=num),
        "m": timedelta(minutes=num),
        "h": timedelta(hours=num),
        "d": timedelta(days=num),
    }.get(unit)

def fmt_dt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")

def normalize_channel(value):
    if not value:
        return None
    v = value.strip()
    if v.startswith("@"):
        v = v[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", v):
        return None
    return f"@{v}"

def channel_exists(channel):
    try:
        chat = bot.get_chat(channel)
        return chat is not None
    except Exception:
        return False

def bot_is_admin_in(channel):
    try:
        me = bot.get_me()
        member = bot.get_chat_member(channel, me.id)
        return getattr(member, "status", "") in ("administrator", "creator")
    except Exception:
        return False

def user_subscribed(user_id, channel):
    try:
        m = bot.get_chat_member(channel, user_id)
        return getattr(m, "status", "") not in ("left", "kicked")
    except Exception:
        return False

def send_subscribe_request(chat_id, channel_hint="@vzref2"):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔗 Подписаться", url=f"https://t.me/{channel_hint.strip('@')}"))
    kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
    bot.send_message(chat_id, "⚠️ Чтобы пользоваться ботом, нужно подписаться на канал:", reply_markup=kb)

def send_private_intro(msg):
    text = (
        "📘 Инструкция по настройке:\n\n"
        "1️⃣ Добавь меня в группу/чат и сделай админом.\n\n"
        "2️⃣ В группе/чате используй:\n"
        "`/setup @канал 24h` — добавить обязательную подписку.\n"
        "⏱ Время можно указывать так: `30s`, `15m`, `12h`, `7d`.\n\n"
        "3️⃣ `/unsetup @канал` — убрать подписку.\n\n"
        "4️⃣ `/status` — список активных проверок.\n\n"
        "ℹ️ Как это работает:\n"
        "• Пользователь пишет сообщение в чат.\n"
        "• Бот проверяет его подписку.\n"
        "• Если подписка есть — сообщение остаётся.\n"
        "• Если нет — сообщение удаляется, а пользователю отправляется кнопка `🔗 Подписаться`.\n\n"
        "———————————————\n\n"
        "💡 Используя этого бота, вы подтверждаете согласие с нашей политикой конфиденциальности.\n"
        "📎 Наш канал: https://t.me/vzref2"
    )
    bot.send_message(msg.chat.id, text, parse_mode="Markdown", disable_web_page_preview=True)

@bot.message_handler(commands=["start"])
def start(msg):
    if msg.chat.type in ("group", "supergroup"):
        bot.send_message(
            msg.chat.id,
            "👋 Привет, я бот‑фильтр.\n"
            "Я проверяю обязательные подписки и удаляю сообщения тех, кто не подписан.\n\n"
            "📌 Для настройки напиши мне в личку."
        )
    else:
        if user_subscribed(msg.from_user.id, "@vzref2"):
            send_private_intro(msg)
        else:
            send_subscribe_request(msg.chat.id)

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(msg):
    if user_subscribed(msg.from_user.id, "@vzref2"):
        send_private_intro(msg)
    else:
        send_subscribe_request(msg.chat.id)

@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def callback_check(call):
    try:
        if user_subscribed(call.from_user.id, "@vzref2"):
            send_private_intro(call.message)
        else:
            send_subscribe_request(call.message.chat.id)
    finally:
        try:
            bot.answer_callback_query(call.id)
        except Exception:
            pass

@bot.message_handler(commands=["setup"])
def setup(msg):
    if msg.chat.type == "private":
        return send_subscribe_request(msg.chat.id)
    args = msg.text.split(maxsplit=2)
    if len(args) < 3:
        return bot.reply_to(msg, "Использование: `/setup @канал 24h`", parse_mode="Markdown")
    raw_channel, duration = args[1], args[2]
    channel = normalize_channel(raw_channel)
    if not channel:
        return bot.reply_to(msg, "⛔️ Неверный формат канала. Пример: `@example_channel`", parse_mode="Markdown")
    if not channel_exists(channel):
        return bot.reply_to(msg, f"⛔️ Канал {channel} не найден в Telegram.")
    if not bot_is_admin_in(channel):
        return bot.reply_to(msg, f"⛔️ Бот не администратор канала {channel}. Добавьте бота в админы канала.")
    delta = parse_duration(duration)
    if not delta:
        return bot.reply_to(msg, "⛔️ Неверный формат времени. Примеры: `30s`, `15m`, `12h`, `7d`", parse_mode="Markdown")
    expires = datetime.now() + delta
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        if cur.fetchone():
            return bot.reply_to(msg, f"⚠️ Канал {channel} уже добавлен в обязательные подписки.")
        db.execute("INSERT INTO required_subs (chat_id, channel, expires) VALUES (?, ?, ?)", (msg.chat.id, channel, expires.isoformat()))
        db.commit()
    bot.reply_to(msg, f"✅ Добавлено обязательное условие: подписка на {channel} до {fmt_dt(expires)}")

@bot.message_handler(commands=["unsetup"])
def unsetup(msg):
    if msg.chat.type == "private":
        return send_subscribe_request(msg.chat.id)
    args = msg.text.split(maxsplit=1)
    if len(args) < 2:
        return bot.reply_to(msg, "Использование: `/unsetup @канал`", parse_mode="Markdown")
    channel = normalize_channel(args[1])
    if not channel:
        return bot.reply_to(msg, "⛔️ Неверный формат канала. Пример: `@example_channel`", parse_mode="Markdown")
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        if not cur.fetchone():
            return bot.reply_to(msg, f"⛔️ Канал {channel} не добавлен в обязательные подписки для этого чата.")
        if not channel_exists(channel):
            return bot.reply_to(msg, f"⛔️ Канал {channel} не найден в Telegram. Удаление ОП возможно только для реальных каналов.")
        if not bot_is_admin_in(channel):
            return bot.reply_to(msg, f"⛔️ Бот не администратор в {channel}. Убедитесь, что бот добавлен в админы, затем повторите.")
        db.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (msg.chat.id, channel))
        db.commit()
    bot.reply_to(msg, f"✅ Убрано обязательное условие с {channel}")

@bot.message_handler(commands=["status"])
def status(msg):
    if msg.chat.type == "private":
        return send_subscribe_request(msg.chat.id)
    now = datetime.now()
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires < ?",
            (msg.chat.id, now.isoformat())
        )
        rows = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (msg.chat.id,)).fetchall()
    if not rows:
        return bot.send_message(msg.chat.id, "📋 Активных обязательных подписок нет.")
    lines = [f"📋 Активные проверки ({len(rows)}):"]
    for i, (channel, expires) in enumerate(rows, 1):
        dt = fmt_dt(datetime.fromisoformat(expires)) if expires else "∞"
        lines.append(f"{i}. {channel} — до {dt}")
        lines.append(f"Убрать ОП — `/unsetup {channel}`")
    lines.append("———————————————")
    bot.send_message(msg.chat.id, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def check(msg):
    chat_id = msg.chat.id
    user_id = msg.from_user.id
    now = datetime.now()
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires < ?",
            (chat_id, now.isoformat())
        )
        subs = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (chat_id,)).fetchall()
    if not subs:
        return
    required = []
    for channel, expires in subs:
        if not channel_exists(channel):
            continue
        if not bot_is_admin_in(channel):
            continue
        required.append(channel)
    if not required:
        return
    not_subscribed = []
    for channel in required:
        if not user_subscribed(user_id, channel):
            not_subscribed.append(channel)
    if not not_subscribed:
        return
    try:
        bot.delete_message(chat_id, msg.message_id)
    except Exception:
        pass
    name = f"@{msg.from_user.username}" if getattr(msg.from_user, "username", None) else msg.from_user.first_name
    channels_text = ", ".join(not_subscribed)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔗 Подписаться", url=f"https://t.me/{not_subscribed[0].strip('@')}"))
    bot.send_message(chat_id, f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {channels_text}", reply_markup=kb)

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
