import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("PLAY")
CHANNEL = os.getenv("CHANNEL")  # ID закрытого канала для отчётов, например -1003079638308
SUB_CHANNEL = "@vzref2"
ADMIN_ID = int(os.getenv("ADMIN_ID") or "7902738665")
DB_PATH = "data.db"

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)
last_private_message = {}

def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with db_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                registered TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                channel TEXT,
                expires TEXT
            )
        """)
        c.commit()

def now_iso():
    return datetime.utcnow().isoformat()

def fmt_dt(s):
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except:
        return s

def normalize_channel(v):
    if not v:
        return None
    t = v.strip()
    if t.startswith("@"):
        t = t[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", t):
        return None
    return "@" + t

def parse_duration(spec):
    if not spec:
        return None
    m = re.fullmatch(r"(\d+)\s*([smhd])", spec.strip(), re.IGNORECASE)
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2).lower()
    if u == "s": return timedelta(seconds=n)
    if u == "m": return timedelta(minutes=n)
    if u == "h": return timedelta(hours=n)
    if u == "d": return timedelta(days=n)
    return None

def notify_report(text):
    try:
        if CHANNEL:
            bot.send_message(CHANNEL, text)
    except:
        pass

def send_private_replace(chat_id, text, reply_markup=None):
    old = last_private_message.get(chat_id)
    if old:
        try:
            bot.delete_message(chat_id, old)
        except:
            pass
    m = bot.send_message(chat_id, text, reply_markup=reply_markup)
    last_private_message[chat_id] = m.message_id
    return m

def build_sub_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔗 Подписаться", url=f"https://t.me/{SUB_CHANNEL.strip('@')}"))
    kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
    return kb

def send_subscribe_request(uid):
    text = (
        "⚠️ *Чтобы пользоваться ботом, нужно подписаться на канал:*\n\n"
        f"*{SUB_CHANNEL}*\n\n"
        "Нажми кнопку Подписаться, затем ✅ Проверить."
    )
    return send_private_replace(uid, text, reply_markup=build_sub_kb())

def user_record(user):
    with db_conn() as c:
        c.execute("INSERT OR IGNORE INTO users(user_id, username, first_name, registered) VALUES(?,?,?,?)",
                  (user.id, getattr(user, "username", "") or "", getattr(user, "first_name", "") or "", now_iso()))
        c.commit()

def get_required_subs_for_chat(chat_id):
    with db_conn() as c:
        cur = c.execute("SELECT id, channel, expires FROM required_subs WHERE chat_id = ?", (chat_id,))
        rows = cur.fetchall()
    res = []
    for r in rows:
        res.append({"id": r[0], "channel": r[1], "expires": r[2]})
    return res

def add_required_sub(chat_id, channel, expires_iso):
    with db_conn() as c:
        c.execute("INSERT INTO required_subs(chat_id, channel, expires) VALUES(?,?,?)", (chat_id, channel, expires_iso))
        c.commit()

def remove_required_sub(chat_id, channel):
    with db_conn() as c:
        c.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (chat_id, channel))
        c.commit()

def cleanup_expired():
    with db_conn() as c:
        now = now_iso()
        c.execute("DELETE FROM required_subs WHERE expires IS NOT NULL AND expires <= ?", (now,))
        c.commit()

def channel_check_membership(user_id, channel):
    try:
        m = bot.get_chat_member(channel, user_id)
        return getattr(m, "status", "") not in ("left", "kicked")
    except:
        return False

@bot.message_handler(commands=["start"])
def cmd_start(m):
    user_record(m.from_user)
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🧾 Профиль", callback_data="profile"))
    kb.add(InlineKeyboardButton("ℹ️ Инструкция", callback_data="intro"))
    kb.add(InlineKeyboardButton("🔗 Канал", url=f"https://t.me/{SUB_CHANNEL.strip('@')}"))
    send_private_replace(m.from_user.id,
        "*Привет*\n\n"
        "Этот бот управляет проверками подписки в группах и отправляет отчёты админам.\n\n"
        "Нажми кнопку Профиль, чтобы увидеть данные.",
        reply_markup=kb)
    notify_report(f"Новый пользователь: `{m.from_user.id}` @{getattr(m.from_user, 'username', '')}")

@bot.message_handler(commands=["help"])
def cmd_help(m):
    send_private_replace(m.from_user.id,
        "*Команды:*\n"
        "`/start` — старт\n"
        "`/help` — помощь\n"
        "`/admin` — админ меню (только для админа)")

@bot.message_handler(commands=["setup"])
def cmd_setup(m):
    if m.chat.type == "private":
        send_private_replace(m.from_user.id, "Команда работает только в группах/супергруппах.")
        return
    member = bot.get_chat_member(m.chat.id, m.from_user.id)
    if getattr(member, "status", "") not in ("administrator", "creator"):
        bot.reply_to(m, "Только админы могут настраивать проверки.")
        return
    args = m.text.split()
    if len(args) < 3:
        bot.reply_to(m, "Использование: /setup @канал 24h")
        return
    ch = normalize_channel(args[1])
    dur = parse_duration(args[2])
    if not ch:
        bot.reply_to(m, "Неверный канал. Укажи @username.")
        return
    expires = None
    if dur:
        expires = (datetime.utcnow() + dur).isoformat()
    add_required_sub(m.chat.id, ch, expires)
    bot.reply_to(m, f"Добавлена проверка: {ch} до {fmt_dt(expires) if expires else '∞'}")
    notify_report(f"Добавлена проверка в чате `{m.chat.id}`: {ch}")

@bot.message_handler(commands=["unsetup"])
def cmd_unsetup(m):
    if m.chat.type == "private":
        send_private_replace(m.from_user.id, "Команда работает только в группах/супергруппах.")
        return
    member = bot.get_chat_member(m.chat.id, m.from_user.id)
    if getattr(member, "status", "") not in ("administrator", "creator"):
        bot.reply_to(m, "Только админы могут настраивать проверки.")
        return
    args = m.text.split()
    if len(args) < 2:
        bot.reply_to(m, "Использование: /unsetup @канал")
        return
    ch = normalize_channel(args[1])
    if not ch:
        bot.reply_to(m, "Неверный канал. Укажи @username.")
        return
    remove_required_sub(m.chat.id, ch)
    bot.reply_to(m, f"Удалена проверка: {ch}")
    notify_report(f"Удалена проверка в чате `{m.chat.id}`: {ch}")

@bot.message_handler(commands=["status"])
def cmd_status(m):
    if m.chat.type == "private":
        rows = []
        with db_conn() as c:
            cur = c.execute("SELECT chat_id, channel, expires FROM required_subs")
            rows = cur.fetchall()
        txt = "*Активные проверки:*\n\n"
        for r in rows[-50:]:
            txt += f"`{r[0]}` — {r[1]} до {fmt_dt(r[2]) if r[2] else '∞'}\n"
        send_private_replace(m.from_user.id, txt)
    else:
        subs = get_required_subs_for_chat(m.chat.id)
        if not subs:
            bot.reply_to(m, "Нет активных проверок в этом чате.")
            return
        txt = "*Проверки в этом чате:*\n\n"
        for s in subs:
            txt += f"{s['channel']} до {fmt_dt(s['expires']) if s['expires'] else '∞'}\n"
        bot.reply_to(m, txt)

@bot.message_handler(func=lambda m: m.chat.type != "private")
def group_message_handler(m):
    cleanup_expired()
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        return
    for s in subs:
        ch = s["channel"]
        ok = channel_check_membership(m.from_user.id, ch)
        if not ok:
            try:
                bot.delete_message(m.chat.id, m.message_id)
            except:
                pass
            try:
                bot.send_message(m.from_user.id,
                    "⚠️ Текст удалён. Чтобы писать в чате, подпишись на канал и нажми Проверить.",
                    reply_markup=build_sub_kb())
            except:
                pass
            notify_report(f"Удалено сообщение от `{m.from_user.id}` в `{m.chat.id}` — не подписан на {ch}")
            return

@bot.callback_query_handler(func=lambda c: True)
def cb_handler(c):
    if c.data == "check_sub":
        ok = channel_check_membership(c.from_user.id, SUB_CHANNEL)
        if ok:
            send_private_replace(c.from_user.id, "*Проверка пройдена. Спасибо!*")
        else:
            send_private_replace(c.from_user.id,
                "Ты не подписан на канал. Нажми Подписаться и затем ✅ Проверить.",
                reply_markup=build_sub_kb())
        try:
            bot.answer_callback_query(c.id)
        except:
            pass
    elif c.data == "profile":
        uid = c.from_user.id
        with db_conn() as con:
            cur = con.execute("SELECT user_id, username, first_name, registered FROM users WHERE user_id = ?", (uid,))
            r = cur.fetchone()
        txt = "*Профиль*\n\n"
        txt += f"ID: `{c.from_user.id}`\n"
        txt += f"Ник: @{getattr(c.from_user, 'username','')}\n"
        txt += f"Имя: {getattr(c.from_user,'first_name','')}\n"
        if r:
            txt += f"Зарегистрирован: {fmt_dt(r[3])}\n"
        send_private_replace(c.from_user.id, txt)
        try:
            bot.answer_callback_query(c.id)
        except:
            pass
    elif c.data.startswith("admin_"):
        if c.from_user.id != ADMIN_ID:
            try:
                bot.answer_callback_query(c.id, "Нет доступа", show_alert=True)
            except:
                pass
            return
        if c.data == "admin_broadcast":
            send_private_replace(ADMIN_ID, "Отправь текст для рассылки всем пользователям. После отправки подтвердишь.")
            bot.register_next_step_handler_by_chat_id(ADMIN_ID, admin_broadcast_step)
        elif c.data == "admin_stats":
            with db_conn() as con:
                users = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                groups = con.execute("SELECT COUNT(DISTINCT chat_id) FROM required_subs").fetchone()[0]
                subs = con.execute("SELECT COUNT(*) FROM required_subs").fetchone()[0]
            send_private_replace(ADMIN_ID, f"*Статистика*\n\nПользователей: {users}\nЧатов с проверками: {groups}\nАктивных проверок: {subs}")
        elif c.data == "admin_users":
            with db_conn() as con:
                rows = con.execute("SELECT user_id, username, first_name, registered FROM users ORDER BY registered DESC LIMIT 10").fetchall()
            txt = "*Последние пользователи:*\n\n"
            for r in rows:
                txt += f"`{r[0]}` @{r[1]} {r[2]} {fmt_dt(r[3])}\n"
            send_private_replace(ADMIN_ID, txt)
        elif c.data == "admin_cleanup":
            cleanup_expired()
            send_private_replace(ADMIN_ID, "Очистка завершена.")
            notify_report("Админ запустил очистку просроченных проверок.")
        try:
            bot.answer_callback_query(c.id)
        except:
            pass

def admin_broadcast_step(m):
    text = m.text
    send_private_replace(ADMIN_ID, "Подтверди рассылку: отправить всем пользователей? (да/нет)")
    def confirm_step(msg):
        ans = msg.text.strip().lower()
        if ans in ("да","yes","y"):
            threading.Thread(target=do_broadcast, args=(text,)).start()
            send_private_replace(ADMIN_ID, "Рассылка запущена в фоне.")
            notify_report("Админ запустил рассылку.")
        else:
            send_private_replace(ADMIN_ID, "Рассылка отменена.")
    bot.register_next_step_handler_by_chat_id(ADMIN_ID, confirm_step)

def do_broadcast(text):
    with db_conn() as con:
        rows = con.execute("SELECT user_id FROM users").fetchall()
    for r in rows:
        uid = r[0]
        try:
            bot.send_message(uid, text)
        except:
            pass

@app.route("/" , methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

def run_polling():
    bot.remove_webhook()
    bot.polling(none_stop=True)

if __name__ == "__main__":
    init_db()
    notify_report("Бот запущен.")
    mode = os.getenv("MODE", "poll")
    if mode == "webhook":
        WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
        WEBHOOK_PORT = int(os.getenv("PORT", "5000"))
        WEBHOOK_PATH = f"/{TOKEN}"
        bot.set_webhook(url=WEBHOOK_HOST + WEBHOOK_PATH)
        app.run(host="0.0.0.0", port=WEBHOOK_PORT)
    else:
        run_polling()
