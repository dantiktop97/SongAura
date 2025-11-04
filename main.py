import os
import re
import sqlite3
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("PLAY")
SUB_CHANNEL = "@vzref2"
DB_PATH = "data.db"
ADMIN_STATUSES = ("administrator", "creator")

bot = telebot.TeleBot(TOKEN, parse_mode="MarkdownV2")
app = Flask(__name__)
_last_private_message = {}

def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with db_conn() as c:
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

def fmt_dt_iso(s):
    try:
        return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M")
    except:
        return s or "∞"

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

def normalize_channel(v):
    if not v:
        return None
    t = v.strip()
    if t.startswith("@"): t = t[1:]
    if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", t): return None
    return "@" + t

def escape_md(text):
    if text is None:
        return ""
    s = str(text)
    return re.sub(r'([_*\[\]\(\)~`>#+=\-|{}.!])', r'\\\1', s)

def channel_exists(channel):
    try:
        bot.get_chat(channel)
        return True
    except:
        return False

def bot_is_admin_in(channel):
    try:
        me = bot.get_me()
        m = bot.get_chat_member(channel, me.id)
        return getattr(m, "status", "") in ADMIN_STATUSES
    except:
        return False

def user_subscribed(user_id, channel):
    try:
        m = bot.get_chat_member(channel, user_id)
        return getattr(m, "status", "") not in ("left", "kicked")
    except:
        return False

def send_private_replace(chat_id, text, reply_markup=None):
    old = _last_private_message.get(chat_id)
    if old:
        try:
            bot.delete_message(chat_id, old)
        except:
            pass
    m = bot.send_message(chat_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
    _last_private_message[chat_id] = m.message_id
    return m

def build_sub_kb(channels):
    kb = InlineKeyboardMarkup()
    btns = []
    for ch in channels:
        url = f"https://t.me/{ch.strip('@')}"
        btns.append(InlineKeyboardButton("🔗 Подписаться", url=url))
    row = []
    for i, b in enumerate(btns, 1):
        row.append(b)
        if i % 2 == 0 or i == len(btns):
            try:
                kb.row(*row)
            except:
                for x in row: kb.add(x)
            row = []
    kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
    return kb

def send_subscribe_request(user_id, channels=None, reply_in_chat=None):
    chs = channels or [SUB_CHANNEL]
    kb = build_sub_kb(chs)
    prompt = "*📌 Чтобы пользоваться ботом, нужно подписаться на канал:*"
    if reply_in_chat:
        try:
            m = bot.send_message(reply_in_chat, prompt, reply_markup=kb, disable_web_page_preview=True)
            return m
        except:
            pass
    return send_private_replace(user_id, prompt, reply_markup=kb)

def add_required_sub(chat_id, channel, expires_iso):
    with db_conn() as c:
        c.execute("INSERT INTO required_subs(chat_id, channel, expires) VALUES(?,?,?)", (chat_id, channel, expires_iso))
        c.commit()

def remove_required_sub(chat_id, channel):
    with db_conn() as c:
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (chat_id, channel))
        c.commit()

def get_required_subs_for_chat(chat_id):
    with db_conn() as c:
        rows = c.execute("SELECT channel, expires FROM required_subs WHERE chat_id=?", (chat_id,)).fetchall()
    return [{"channel": r[0], "expires": r[1]} for r in rows]

def cleanup_expired_for_chat(chat_id):
    now = now_iso()
    with db_conn() as c:
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires <= ?", (chat_id, now))
        c.commit()

INSTRUCTION_TEXT = (
    "*📘 Инструкция по настройке:*\n\n"
    "1️⃣ Добавь меня в группу/чат и сделай админом.\n\n"
    "2️⃣ В группе/чате используй:\n"
    "`/setup @канал 24h` — добавить обязательную подписку.\n"
    "⏱ Время можно указывать так: `30s`, `15m`, `12h`, `7d`.\n\n"
    "`/unsetup @канал` — убрать подписку.\n"
    "`/status` — список активных проверок.\n\n"
    "*ℹ️ Как это работает:*\n"
    "• Пользователь пишет сообщение в чат.\n"
    "• Бот проверяет его подписку.\n"
    "• Если подписка есть — сообщение остаётся.\n"
    "• Если нет — сообщение удаляется, а пользователю отправляется кнопка 🔗 Подписаться.\n\n"
    "———————————————\n\n"
    "💡 Используя этого бота, вы подтверждаете согласие с нашей политикой конфиденциальности."
)

SUB_PROMPT_TEXT = "*📌 Чтобы пользоваться ботом, нужно подписаться на канал:*"

@bot.message_handler(commands=["start"])
def cmd_start(m):
    if m.chat.type in ("group", "supergroup"):
        bot.send_message(m.chat.id,
            "*📌 Привет, я бот‑фильтр.*\n\n`Напиши мне в личку для настройки`"
        )
        return
    if user_subscribed(m.from_user.id, SUB_CHANNEL):
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
    else:
        send_subscribe_request(m.from_user.id, [SUB_CHANNEL])

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(m):
    if user_subscribed(m.from_user.id, SUB_CHANNEL):
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
    else:
        send_subscribe_request(m.from_user.id, [SUB_CHANNEL])

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def cb_check(c):
    user_id = c.from_user.id
    chat = c.message.chat if c.message else None

    if chat and chat.type in ("group", "supergroup"):
        subs = get_required_subs_for_chat(chat.id)
        required = [s["channel"] for s in subs if channel_exists(s["channel"]) and bot_is_admin_in(s["channel"])]
        if not required:
            try:
                bot.answer_callback_query(c.id, "Нет настроенных проверок", show_alert=True)
            except:
                pass
            return
        not_sub = [ch for ch in required if not user_subscribed(user_id, ch)]
        if not not_sub:
            try:
                bot.delete_message(chat.id, c.message.message_id)
            except:
                pass
            try:
                bot.answer_callback_query(c.id, "✅ Подписка проверена", show_alert=False)
            except:
                pass
            return
        name = f"@{c.from_user.username}" if getattr(c.from_user, "username", None) else escape_md(c.from_user.first_name)
        txt = f"*⚠️ {escape_md(name)}, чтобы писать в чат, необходимо подписаться на канал(ы):* `{escape_md(', '.join(not_sub))}`"
        kb = build_sub_kb(not_sub)
        try:
            bot.delete_message(chat.id, c.message.message_id)
        except:
            pass
        bot.send_message(chat.id, txt, reply_markup=kb)
        try:
            bot.answer_callback_query(c.id)
        except:
            pass
        return

    if user_subscribed(user_id, SUB_CHANNEL):
        send_private_replace(user_id, INSTRUCTION_TEXT)
    else:
        send_subscribe_request(user_id, [SUB_CHANNEL])
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

@bot.message_handler(commands=["setup"])
def cmd_setup(m):
    if m.chat.type in ("group", "supergroup"):
        cleanup_expired_for_chat(m.chat.id)
        subs = get_required_subs_for_chat(m.chat.id)
        required = [s["channel"] for s in subs if channel_exists(s["channel"]) and bot_is_admin_in(s["channel"])]
        not_sub = [ch for ch in required if not user_subscribed(m.from_user.id, ch)]
        if not_sub:
            try:
                bot.delete_message(m.chat.id, m.message_id)
            except:
                pass
            name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else escape_md(m.from_user.first_name)
            txt = f"*⚠️ {escape_md(name)}, чтобы писать в чат, необходимо подписаться на канал(ы):* `{escape_md(', '.join(not_sub))}`"
            kb = build_sub_kb(not_sub)
            bot.send_message(m.chat.id, txt, reply_markup=kb)
            return
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "*⛔️ Недостаточно прав. Только админы могут использовать эту команду.*")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES:
            bot.reply_to(m, "*⛔️ Недостаточно прав. Только админы могут использовать эту команду.*")
            return
    else:
        if not user_subscribed(m.from_user.id, SUB_CHANNEL):
            return send_subscribe_request(m.chat.id, [SUB_CHANNEL])
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
        return

    args = m.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(m, "*Использование:* ` /setup @канал 24h`")
        return

    raw_ch, dur = args[1], args[2]
    ch = normalize_channel(raw_ch)
    if not ch:
        bot.reply_to(m, "*⛔️ Неверный формат канала. Пример:* `@example_channel`")
        return
    if not channel_exists(ch):
        bot.reply_to(m, f"*⛔️ Канал {escape_md(ch)} не найден в Telegram.*")
        return
    if not bot_is_admin_in(ch):
        bot.reply_to(m, f"*⛔️ Бот не администратор в канале {escape_md(ch)}. Добавьте бота в админы канала.*")
        return
    delta = parse_duration(dur)
    if not delta:
        bot.reply_to(m, "*⛔️ Неверный формат времени. Примеры:* `30s`, `15m`, `12h`, `7d`")
        return
    expires = (datetime.utcnow() + delta).isoformat()
    with db_conn() as c:
        cur = c.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        if cur.fetchone():
            bot.reply_to(m, f"*⚠️ Канал {escape_md(ch)} уже добавлен в обязательные подписки.*")
            return
        c.execute("INSERT INTO required_subs(chat_id, channel, expires) VALUES(?,?,?)", (m.chat.id, ch, expires))
        c.commit()
    bot.reply_to(m, f"*✅ Добавлено обязательное условие:*\nПодписка на `{escape_md(ch)}` до *{escape_md(fmt_dt_iso(expires))}*")

@bot.message_handler(commands=["unsetup"])
def cmd_unsetup(m):
    if m.chat.type in ("group", "supergroup"):
        cleanup_expired_for_chat(m.chat.id)
        subs = get_required_subs_for_chat(m.chat.id)
        required = [s["channel"] for s in subs if channel_exists(s["channel"]) and bot_is_admin_in(s["channel"])]
        not_sub = [ch for ch in required if not user_subscribed(m.from_user.id, ch)]
        if not_sub:
            try:
                bot.delete_message(m.chat.id, m.message_id)
            except:
                pass
            name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else escape_md(m.from_user.first_name)
            txt = f"*⚠️ {escape_md(name)}, чтобы писать в чат, необходимо подписаться на канал(ы):* `{escape_md(', '.join(not_sub))}`"
            kb = build_sub_kb(not_sub)
            bot.send_message(m.chat.id, txt, reply_markup=kb)
            return
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "*⛔️ Недостаточно прав. Только админы могут использовать эту команду.*")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES:
            bot.reply_to(m, "*⛔️ Недостаточно прав. Только админы могут использовать эту команду.*")
            return
    else:
        if not user_subscribed(m.from_user.id, SUB_CHANNEL):
            return send_subscribe_request(m.chat.id, [SUB_CHANNEL])
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
        return

    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, "*Использование:* ` /unsetup @канал`")
        return
    ch = normalize_channel(args[1])
    if not ch:
        bot.reply_to(m, "*⛔️ Неверный формат канала. Пример:* `@example_channel`")
        return
    with db_conn() as c:
        cur = c.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        if not cur.fetchone():
            bot.reply_to(m, f"*⛔️ Канал {escape_md(ch)} не добавлен в обязательные подписки для этого чата.*")
            return
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        c.commit()
    bot.reply_to(m, f"*✅ Удалена проверка:*\n`{escape_md(ch)}`")

@bot.message_handler(commands=["status"])
def cmd_status(m):
    if m.chat.type in ("group", "supergroup"):
        cleanup_expired_for_chat(m.chat.id)
        subs = get_required_subs_for_chat(m.chat.id)
        required = [s["channel"] for s in subs if channel_exists(s["channel"]) and bot_is_admin_in(s["channel"])]
        not_sub = [ch for ch in required if not user_subscribed(m.from_user.id, ch)]
        if not_sub:
            try:
                bot.delete_message(m.chat.id, m.message_id)
            except:
                pass
            name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else escape_md(m.from_user.first_name)
            txt = f"*⚠️ {escape_md(name)}, чтобы писать в чат, необходимо подписаться на канал(ы):* `{escape_md(', '.join(not_sub))}`"
            kb = build_sub_kb(not_sub)
            bot.send_message(m.chat.id, txt, reply_markup=kb)
            return
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "*⛔️ Недостаточно прав. Только админы могут использовать эту команду.*")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES:
            bot.reply_to(m, "*⛔️ Недостаточно прав. Только админы могут использовать эту команду.*")
            return
    else:
        if not user_subscribed(m.from_user.id, SUB_CHANNEL):
            return send_subscribe_request(m.chat.id, [SUB_CHANNEL])
        return send_private_replace(m.from_user.id, INSTRUCTION_TEXT)

    cleanup_expired_for_chat(m.chat.id)
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        bot.send_message(m.chat.id, "*📋 Активных обязательных подписок нет.*")
        return
    lines = [f"*📋 Активные проверки ({len(subs)}):*"]
    for i, s in enumerate(subs, 1):
        dt = fmt_dt_iso(s.get("expires"))
        lines.append(f"`{i}.` `{escape_md(s['channel'])}` — до *{escape_md(dt)}*")
        lines.append(f"`/unsetup {escape_md(s['channel'])}` — Убрать ОП")
        lines.append("———————————————")
    bot.send_message(m.chat.id, "\n".join(lines))

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def group_message_handler(m):
    cleanup_expired_for_chat(m.chat.id)
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        return
    required = []
    for s in subs:
        ch = s["channel"]
        if not channel_exists(ch):
            try:
                bot.send_message(m.chat.id, f"*⛔️ Канал {escape_md(ch)} не найден. Уберите или исправьте ОП через `/unsetup {escape_md(ch)}`*")
            except:
                pass
            continue
        if not bot_is_admin_in(ch):
            try:
                bot.send_message(m.chat.id, f"*⛔️ Бот не администратор в канале {escape_md(ch)}. Добавьте бота в админы канала.*")
            except:
                pass
            continue
        required.append(ch)
    if not required:
        return
    not_sub = [ch for ch in required if not user_subscribed(m.from_user.id, ch)]
    if not_sub:
        try:
            bot.delete_message(m.chat.id, m.message_id)
        except:
            pass
        name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else escape_md(m.from_user.first_name)
        txt = f"*⚠️ {escape_md(name)}, чтобы писать в чат, необходимо подписаться на канал(ы):* `{escape_md(', '.join(not_sub))}`"
        kb = build_sub_kb(not_sub)
        bot.send_message(m.chat.id, txt, reply_markup=kb)
        return

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "", 200

@app.route("/", methods=["GET"])
def index():
    return "ok", 200

def run_poll():
    bot.remove_webhook()
    bot.polling(none_stop=True)

if __name__ == "__main__":
    init_db()
    mode = os.getenv("MODE", "poll")
    if mode == "webhook":
        WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
        WEBHOOK_PORT = int(os.getenv("PORT", "8000"))
        bot.set_webhook(url=f"{WEBHOOK_HOST.rstrip('/')}/{TOKEN}")
        app.run(host="0.0.0.0", port=WEBHOOK_PORT)
    else:
        run_poll()
