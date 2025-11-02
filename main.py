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

def is_subscribed(user_id, channel="@vzref2"):
    try:
        member = bot.get_chat_member(channel, user_id)
        return member.status not in ["left", "kicked"]
    except:
        return False

def send_private_intro(msg):
    if not is_subscribed(msg.from_user.id, "@vzref2"):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔗 Подписаться", url="https://t.me/vzref2"))
        bot.send_message(msg.chat.id, "⚠️ Чтобы пользоваться ботом, нужно подписаться на канал:", reply_markup=kb)
        return
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔗 Подписаться", url="https://t.me/vzref2"))
    bot.send_message(msg.chat.id, "⚠️ Чтобы пользоваться ботом, нужно быть подписанным на канал:", reply_markup=kb)
    bot.send_message(msg.chat.id, f"👋 Привет, <b>{msg.from_user.first_name}</b>! Я <b>бот‑фильтр</b>.\nЯ проверяю <b>обязательные подписки</b> и удаляю сообщения тех, кто не подписан.", parse_mode="HTML")
    bot.send_message(msg.chat.id, "📘 <b>Инструкция по настройке</b>:\n\n1️⃣ Добавь меня в <b>группу/чат</b> и сделай <b>админом</b>.\n2️⃣ В группе/чате используй:\n/setup @канал 24h — добавить обязательную подписку.\n⏱ Время можно указывать так: <b>30s</b>, <b>15m</b>, <b>12h</b>, <b>7d</b>.\n3️⃣ /unsetup @канал — убрать подписку.\n4️⃣ /status — список активных проверок.\n\nℹ️ <b>Как это работает</b>:\n• Пользователь пишет сообщение в чат.\n• Бот проверяет его подписку.\n• Если подписка есть — сообщение остаётся.\n• Если нет — сообщение удаляется, а пользователю отправляется кнопка «Подписаться».", parse_mode="HTML")

@bot.message_handler(commands=["start"])
def start(msg):
    if msg.chat.type in ["group", "supergroup"]:
        bot.send_message(msg.chat.id, "👋 Привет, я <b>бот‑фильтр</b>.\nЯ проверяю <b>обязательные подписки</b> и удаляю сообщения тех, кто не подписан.\n\n📌 Для <b>настройки</b> напиши мне в личку.", parse_mode="HTML")
    elif msg.chat.type == "private":
        send_private_intro(msg)

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(msg):
    send_private_intro(msg)

@bot.message_handler(commands=["setup"])
def setup(msg):
    if msg.chat.type == "private":
        return send_private_intro(msg)
    args = msg.text.split()
    if len(args) < 3:
        return bot.reply_to(msg, "Использование: /setup @канал 24h")
    channel, duration = args[1], args[2]
    delta = parse_duration(duration)
    if not delta:
        return bot.reply_to(msg, "Неверный формат времени. Пример: 24h, 7d (s=сек, m=мин, h=час, d=день)")
    expires = datetime.now() + delta
    with sqlite3.connect(DB_PATH) as db:
        db.execute("INSERT INTO required_subs (chat_id, channel, expires) VALUES (?, ?, ?)", (msg.chat.id, channel, expires.isoformat()))
    bot.reply_to(msg, f"✅ Добавлено обязательное условие: подписка на {channel} до {fmt_dt(expires)}")

@bot.message_handler(commands=["unsetup"])
def unsetup(msg):
    if msg.chat.type == "private":
        return send_private_intro(msg)
    args = msg.text.split()
    if len(args) < 2:
        return bot.reply_to(msg, "Использование: /unsetup @канал")
    channel = args[1]
    with sqlite3.connect(DB_PATH) as db:
        db.execute("DELETE FROM required_subs WHERE channel=?", (channel,))
    bot.reply_to(msg, f"✅ Убрано обязательное условие с {channel}")

@bot.message_handler(commands=["status"])
def status(msg):
    if msg.chat.type == "private":
        return send_private_intro(msg)
    with sqlite3.connect(DB_PATH) as db:
        cur = db.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (msg.chat.id,))
        rows = cur.fetchall()
    if not rows:
        return bot.reply_to(msg, "📋 Активных обязательных подписок нет.")
    text = [f"📋 Активные проверки ({len(rows)}):"]
    for i, (channel, expires) in enumerate(rows, 1):
        dt = fmt_dt(datetime.fromisoformat(expires)) if expires else "∞"
        text.append(f"{i}. {channel} — до {dt}")
    bot.reply_to(msg, "\n".join(text))

@bot.message_handler(func=lambda m: m.chat.type in ["group", "supergroup"])
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
        bot.send_message(chat_id, f"{msg.from_user.first_name}, чтобы писать в чат, необходимо подписаться на канал(ы): {channel}", reply_markup=kb)

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
    bot.set_webhook(url=f"{os.getenv('RENDER_EXTERNAL_URL')}/{TOKEN}")
    app.run(host="0.0.0.0", port=8000)
