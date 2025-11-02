import os
import re
import sqlite3
import telebot
from datetime import datetime, timedelta
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("PLAY")
bot = telebot.TeleBot(TOKEN)
DB_PATH = "data.db"

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

@bot.message_handler(commands=["start"])
def start(msg):
    name = msg.from_user.first_name or msg.from_user.username or "друг"
    bot.send_message(msg.chat.id,
        f"👋 Привет, {name}!\n\n"
        "Я контролирую обязательные подписки.\n\n"
        "Команды:\n"
        "/setup @канал 24h — добавить обязательную подписку\n"
        "/unsetup @канал — удалить\n"
        "/status — список активных проверок"
    )

@bot.message_handler(commands=["setup"])
def setup(msg):
    args = msg.text.split()
    if len(args) < 3:
        return bot.reply_to(msg, "Использование: /setup @канал 24h")
    channel, duration = args[1], args[2]
    delta = parse_duration(duration)
    if not delta:
        return bot.reply_to(msg, "Неверный формат времени. Пример: 24h, 7d")
    expires = datetime.now() + delta
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO required_subs (chat_id, channel, expires) VALUES (?, ?, ?)", (msg.chat.id, channel, expires.isoformat()))
    bot.reply_to(msg, f"✅ Добавлено ОП на {channel} до {fmt_dt(expires)}")

@bot.message_handler(commands=["unsetup"])
def unsetup(msg):
    args = msg.text.split()
    if len(args) < 2:
        return bot.reply_to(msg, "Использование: /unsetup @канал")
    channel = args[1]
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM required_subs WHERE channel=?", (channel,))
    bot.reply_to(msg, f"✅ Убрано ОП с {channel}")

@bot.message_handler(commands=["status"])
def status(msg):
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (msg.chat.id,))
        rows = cur.fetchall()
    if not rows:
        return bot.reply_to(msg, "📋 Активных обязательных подписок нет.")
    text = [f"📋 Активные ОП ({len(rows)}):"]
    for i, (channel, expires) in enumerate(rows, 1):
        dt = fmt_dt(datetime.fromisoformat(expires)) if expires else "∞"
        text.append(f"{i}. {channel} — до {dt}")
    bot.reply_to(msg, "\n".join(text))

@bot.message_handler(func=lambda m: True)
def check(msg):
    user_id = msg.from_user.id
    chat_id = msg.chat.id
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (chat_id,))
        subs = cur.fetchall()
    if not subs:
        return
    not_subscribed = []
    for channel, expires in subs:
        if expires and datetime.fromisoformat(expires) < datetime.now():
            with sqlite3.connect(DB_PATH) as db:
                db.execute("DELETE FROM required_subs WHERE channel=?", (channel,))
            continue
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ["left", "kicked"]:
                not_subscribed.append(channel)
        except:
            not_subscribed.append(channel)
    if not not_subscribed:
        return
    try:
        bot.delete_message(chat_id, msg.message_id)
    except:
        pass
    for channel in not_subscribed:
        link = f"https://t.me/{channel.strip('@')}"
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔗 Подписаться", url=link))
        bot.send_message(
            chat_id,
            f"{msg.from_user.first_name}, чтобы писать в чат, необходимо подписаться на канал(ы): {channel}",
            reply_markup=kb
        )

init_db()
bot.infinity_polling()
