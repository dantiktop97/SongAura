import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
SUB_CHANNEL = os.getenv("SUB_CHANNEL", "@vzref2")
DB_PATH = "data.db"
ADMIN_STATUSES = ("administrator", "creator")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)
_last_private_message = {}
_RATE = {}
RATE_LIMIT_COUNT = 5
RATE_LIMIT_WINDOW = 7

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
        c.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                messages_count INTEGER DEFAULT 0,
                last_seen TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                admin_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                expires_at TEXT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                action TEXT,
                details TEXT,
                created_at TEXT
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
    if reply_in_chat:
        try:
            m = bot.send_message(reply_in_chat, SUB_PROMPT_TEXT, reply_markup=kb, disable_web_page_preview=True)
            return m
        except:
            pass
    return send_private_replace(user_id, SUB_PROMPT_TEXT, reply_markup=kb)

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

def upsert_member(user, chat_id):
    with db_conn() as c:
        cur = c.execute("SELECT id FROM members WHERE user_id=? AND chat_id=?", (user.id, chat_id)).fetchone()
        if cur:
            c.execute("UPDATE members SET username=?, first_name=?, last_name=?, messages_count=messages_count+1, last_seen=? WHERE id=?", (
                getattr(user, "username", None),
                getattr(user, "first_name", None),
                getattr(user, "last_name", None),
                now_iso(),
                cur[0]
            ))
        else:
            c.execute("INSERT INTO members (user_id, chat_id, username, first_name, last_name, messages_count, last_seen) VALUES(?,?,?,?,?,?,?)", (
                user.id, chat_id, getattr(user, "username", None), getattr(user, "first_name", None),
                getattr(user, "last_name", None), 1, now_iso()
            ))
        c.commit()

def get_members_by_chat(chat_id):
    with db_conn() as c:
        rows = c.execute("SELECT user_id FROM members WHERE chat_id=?", (chat_id,)).fetchall()
    return [r[0] for r in rows]

def add_warn(chat_id, user_id, admin_id, reason):
    with db_conn() as c:
        c.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES(?,?,?,?,?)",
                  (chat_id, user_id, admin_id, reason, now_iso()))
        c.commit()

def get_warns_count(chat_id, user_id):
    with db_conn() as c:
        return c.execute("SELECT COUNT(*) FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id)).fetchone()[0]

def clear_warns(chat_id, user_id):
    with db_conn() as c:
        c.execute("DELETE FROM warns WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        c.commit()

def add_mute(chat_id, user_id, expires_at):
    with db_conn() as c:
        c.execute("INSERT INTO mutes (chat_id, user_id, expires_at) VALUES(?,?,?)", (chat_id, user_id, expires_at))
        c.commit()

def remove_mute(chat_id, user_id):
    with db_conn() as c:
        c.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        c.commit()

def check_and_release_mutes():
    while True:
        with db_conn() as c:
            rows = c.execute("SELECT id, chat_id, user_id, expires_at FROM mutes WHERE expires_at IS NOT NULL").fetchall()
            now = datetime.utcnow()
            for r in rows:
                try:
                    expires = datetime.fromisoformat(r[3])
                except:
                    continue
                if expires <= now:
                    try:
                        bot.restrict_chat_member(r[1], r[2], until_date=0, can_send_messages=True)
                    except:
                        pass
                    c.execute("DELETE FROM mutes WHERE id=?", (r[0],))
            c.commit()
        time.sleep(10)

def log_action(chat_id, action, details=""):
    with db_conn() as c:
        c.execute("INSERT INTO logs (chat_id, action, details, created_at) VALUES(?,?,?,?)", (chat_id, action, details, now_iso()))
        c.commit()

INSTRUCTION_TEXT = (
    "*📘 Инструкция по настройке*\n\n"
    "*1.* Добавьте бота в группу и назначьте админом.\n\n"
    "*2.* В группе используйте команды:\n"
    "`/setup @канал 24h` — добавить обязательную подписку\n"
    "`/unsetup @канал` — убрать подписку\n"
    "`/status` — показать настройки\n\n"
    "*3.* Для личной настройки отправьте `/adminmenu` в личке.*\n\n"
    "*ℹ️ Как это работает:*\n"
    "• Бот проверяет подписки и удаляет сообщения тех, кто не подписан.\n"
    "• Админ может настроить проверки и модули через меню.\n\n"
    "————————————\n"
    "Используя бота, вы соглашаетесь с политикой конфиденциальности."
)

SUB_PROMPT_TEXT = "Чтобы пользоваться ботом, нужно подписаться на канал:"

@bot.message_handler(content_types=[
    "new_chat_members",
    "left_chat_member",
    "pinned_message",
    "new_chat_title",
    "new_chat_photo",
    "delete_chat_photo",
    "group_chat_created",
    "supergroup_chat_created",
    "channel_chat_created",
    "migrate_to_chat_id",
    "migrate_from_chat_id"
])
def delete_system_messages(m):
    try:
        bot.delete_message(m.chat.id, m.message_id)
    except:
        pass

@bot.message_handler(commands=["start"])
def cmd_start(m):
    if m.chat.type in ("group", "supergroup"):
        bot.send_message(m.chat.id, "👋 *Привет!* Я бот-фильтр. Для настройки напишите мне в личку.", parse_mode="Markdown")
        return
    if user_subscribed(m.from_user.id, SUB_CHANNEL):
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
    else:
        send_subscribe_request(m.from_user.id, [SUB_CHANNEL])

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(m):
    if user_subscribed(m.from_user.id, SUB_CHANNEL):
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("⚙️ Настройки", callback_data="open_admin_menu"))
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT, reply_markup=kb)
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
        name = f"@{c.from_user.username}" if getattr(c.from_user, "username", None) else c.from_user.first_name
        txt = f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {', '.join(not_sub)}"
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

def is_group_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return getattr(member, "status", "") in ADMIN_STATUSES
    except:
        return False

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
            name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else m.from_user.first_name
            txt = f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {', '.join(not_sub)}"
            kb = build_sub_kb(not_sub)
            bot.send_message(m.chat.id, txt, reply_markup=kb)
            return
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES:
            bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
            return
    else:
        if not user_subscribed(m.from_user.id, SUB_CHANNEL):
            return send_subscribe_request(m.chat.id, [SUB_CHANNEL])
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
        return
    args = m.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(m, "Использование: `/setup @канал 24h`")
        return
    raw_ch, dur = args[1], args[2]
    ch = normalize_channel(raw_ch)
    if not ch:
        bot.reply_to(m, "⛔️ Неверный формат канала. Пример: `@example_channel`")
        return
    if not channel_exists(ch):
        bot.reply_to(m, f"⛔️ Канал {ch} не найден в Telegram.")
        return
    if not bot_is_admin_in(ch):
        bot.reply_to(m, f"⛔️ Бот не администратор в канале {ch}. Добавьте бота в админы канала.")
        return
    delta = parse_duration(dur)
    if not delta:
        bot.reply_to(m, "⛔️ Неверный формат времени. Примеры: `30s`, `15m`, `12h`, `7d`")
        return
    expires = (datetime.utcnow() + delta).isoformat()
    with db_conn() as c:
        cur = c.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        if cur.fetchone():
            bot.reply_to(m, f"⚠️ Канал {ch} уже добавлен в обязательные подписки.")
            return
        c.execute("INSERT INTO required_subs(chat_id, channel, expires) VALUES(?,?,?)", (m.chat.id, ch, expires))
        c.commit()
    bot.reply_to(m, f"✅ Добавлено обязательное условие: подписка на {ch} до {fmt_dt_iso(expires)}")
    log_action(m.chat.id, "setup_add", f"{ch} until {expires}")

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
            name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else m.from_user.first_name
            txt = f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {', '.join(not_sub)}"
            kb = build_sub_kb(not_sub)
            bot.send_message(m.chat.id, txt, reply_markup=kb)
            return
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES:
            bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
            return
    else:
        if not user_subscribed(m.from_user.id, SUB_CHANNEL):
            return send_subscribe_request(m.chat.id, [SUB_CHANNEL])
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
        return
    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, "Использование: `/unsetup @канал`")
        return
    ch = normalize_channel(args[1])
    if not ch:
        bot.reply_to(m, "⛔️ Неверный формат канала. Пример: `@example_channel`")
        return
    with db_conn() as c:
        cur = c.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        if not cur.fetchone():
            bot.reply_to(m, f"⛔️ Канал {ch} не добавлен в обязательные подписки для этого чата.")
            return
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        c.commit()
    bot.reply_to(m, f"✅ Удалена проверка: {ch}")
    log_action(m.chat.id, "setup_remove", ch)

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
            name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else m.from_user.first_name
            txt = f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {', '.join(not_sub)}"
            kb = build_sub_kb(not_sub)
            bot.send_message(m.chat.id, txt, reply_markup=kb)
            return
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES:
            bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
            return
    else:
        if not user_subscribed(m.from_user.id, SUB_CHANNEL):
            return send_subscribe_request(m.chat.id, [SUB_CHANNEL])
        return send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
    cleanup_expired_for_chat(m.chat.id)
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        bot.send_message(m.chat.id, "📋 *Активных обязательных подписок нет.*", parse_mode="Markdown")
        return
    lines = [f"*📋 Активные проверки ({len(subs)}):*"]
    for i, s in enumerate(subs, 1):
        dt = fmt_dt_iso(s.get("expires"))
        lines.append(f"`{i}.` {s['channel']} — до {dt}")
        lines.append(f"`/unsetup {s['channel']}` — Убрать ОП")
        lines.append("———————————————")
    bot.send_message(m.chat.id, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def group_message_handler(m):
    try:
        upsert_member(m.from_user, m.chat.id)
    except:
        pass
    cleanup_expired_for_chat(m.chat.id)
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        return
    required = []
    for s in subs:
        ch = s["channel"]
        if not channel_exists(ch):
            try:
                bot.send_message(m.chat.id, f"⛔️ Канал {ch} не найден. Уберите или исправьте ОП через `/unsetup {ch}`")
            except:
                pass
            continue
        if not bot_is_admin_in(ch):
            try:
                bot.send_message(m.chat.id, f"⛔️ Бот не администратор в канале {ch}. Добавьте бота в админы канала.")
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
        name = f"@{m.from_user.username}" if getattr(m.from_user, "username", None) else m.from_user.first_name
        txt = f"{name}, чтобы писать в чат, необходимо подписаться на канал(ы): {', '.join(not_sub)}"
        kb = build_sub_kb(not_sub)
        bot.send_message(m.chat.id, txt, reply_markup=kb)
        return

def build_admin_menu(chat_id=None):
    kb = InlineKeyboardMarkup()
    kb.row(InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"), InlineKeyboardButton("✉️ Рассылка", callback_data="admin_broadcast"))
    kb.row(InlineKeyboardButton("🛠 Настройки групп", callback_data="admin_groups"), InlineKeyboardButton("⚙️ Модули", callback_data="admin_modules"))
    kb.row(InlineKeyboardButton("📜 Логи", callback_data="admin_logs"), InlineKeyboardButton("🔄 Перезагрузить", callback_data="admin_reload"))
    return kb

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("admin_"))
def admin_cb(c):
    uid = c.from_user.id
    if uid != ADMIN_ID:
        try:
            bot.answer_callback_query(c.id, "Доступ только для владельца", show_alert=True)
        except:
            pass
        return
    cmd = c.data.split("_", 1)[1]
    if cmd == "stats":
        with db_conn() as con:
            total_chats = con.execute("SELECT COUNT(DISTINCT chat_id) FROM members").fetchone()[0]
            total_users = con.execute("SELECT COUNT(DISTINCT user_id) FROM members").fetchone()[0]
        txt = f"*📊 Статистика*\n\n*Чатов с активными записями:* {total_chats}\n*Пользователей в базе:* {total_users}"
        try:
            bot.answer_callback_query(c.id)
        except:
            pass
        bot.send_message(c.from_user.id, txt, parse_mode="Markdown")
    elif cmd == "broadcast":
        try:
            bot.answer_callback_query(c.id)
        except:
            pass
        bot.send_message(c.from_user.id, "*✉️ Рассылка*\nОтправь сообщение, и оно будет отправлено всем пользователям базы.", parse_mode="Markdown")
        @bot.message_handler(func=lambda m: m.chat.id == c.from_user.id, content_types=["text"])
        def capture_broadcast(m2):
            text = m2.text
            bot.send_message(m2.chat.id, "Запуск рассылки...")
            with db_conn() as con:
                rows = con.execute("SELECT DISTINCT user_id FROM members").fetchall()
            total = 0
            for r in rows:
                uid2 = r[0]
                try:
                    bot.send_message(uid2, text, disable_web_page_preview=True)
                    total += 1
                except:
                    pass
            bot.send_message(m2.chat.id, f"Рассылка завершена. Отправлено: {total}")
    elif cmd == "groups":
        with db_conn() as con:
            rows = con.execute("SELECT DISTINCT chat_id FROM members").fetchall()
        txt = "*📂 Список чатов:*\n\n" + "\n".join(str(r[0]) for r in rows)
        bot.send_message(c.from_user.id, txt, parse_mode="Markdown")
    elif cmd == "modules":
        bot.send_message(c.from_user.id, "*⚙️ Модули*\nЗдесь можно включать/выключать модули (реализация базовая).", parse_mode="Markdown")
    elif cmd == "logs":
        with db_conn() as con:
            rows = con.execute("SELECT created_at, action, details FROM logs ORDER BY id DESC LIMIT 30").fetchall()
        txt = "*📜 Логи (последние 30):*\n\n" + "\n".join(f"{r[0]} | {r[1]} | {r[2]}" for r in rows)
        bot.send_message(c.from_user.id, txt, parse_mode="Markdown")
    elif cmd == "reload":
        bot.send_message(c.from_user.id, "Перезагрузка команд не реализована в Poll режиме.", parse_mode="Markdown")

@bot.message_handler(commands=["adminmenu"])
def cmd_adminmenu(m):
    if m.chat.type in ("group", "supergroup"):
        try:
            member = bot.get_chat_member(m.chat.id, m.from_user.id)
        except:
            bot.reply_to(m, "⛔️ Недостаточно прав.")
            return
        if getattr(member, "status", "") not in ADMIN_STATUSES and m.from_user.id != ADMIN_ID:
            bot.reply_to(m, "⛔️ Только админы могут открыть меню.")
            return
    else:
        if m.from_user.id != ADMIN_ID:
            if not user_subscribed(m.from_user.id, SUB_CHANNEL):
                return send_subscribe_request(m.from_user.id, [SUB_CHANNEL])
    kb = build_admin_menu()
    txt = "*🔐 Админ-меню*\n\nВыберите действие. Доступно владельцу бота и администраторам групп."
    bot.send_message(m.from_user.id, txt, parse_mode="Markdown", reply_markup=kb)

def parse_mention_or_id(text):
    parts = text.strip().split()
    if not parts:
        return None
    target = parts[0]
    if target.startswith("@"):
        return target
    try:
        return int(target)
    except:
        return None

@bot.message_handler(commands=["ban"])
def cmd_ban(m):
    if m.chat.type not in ("group", "supergroup"):
        bot.reply_to(m, "Команда работает в группе.")
        return
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES and m.from_user.id != ADMIN_ID:
        bot.reply_to(m, "⛔️ Только админы могут использовать эту команду.")
        return
    args = m.text.split(maxsplit=2)
    if len(args) < 2 and not m.reply_to_message:
        bot.reply_to(m, "Использование: /ban @user или ответ на сообщение")
        return
    target = None
    reason = ""
    if m.reply_to_message:
        target = m.reply_to_message.from_user.id
        reason = " ".join(args[1:]) if len(args) > 1 else ""
    else:
        target = parse_mention_or_id(args[1])
        reason = " ".join(args[2:]) if len(args) > 2 else ""
    try:
        bot.kick_chat_member(m.chat.id, int(target))
        bot.send_message(m.chat.id, f"🔨 Пользователь забанен. {reason}")
        log_action(m.chat.id, "ban", f"{target} by {m.from_user.id} reason:{reason}")
    except Exception as e:
        bot.reply_to(m, f"Ошибка: {e}")

@bot.message_handler(commands=["kick"])
def cmd_kick(m):
    if m.chat.type not in ("group", "supergroup"):
        bot.reply_to(m, "Команда работает в группе.")
        return
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES and m.from_user.id != ADMIN_ID:
        bot.reply_to(m, "⛔️ Только админы могут использовать эту команду.")
        return
    if m.reply_to_message:
        target = m.reply_to_message.from_user.id
    else:
        args = m.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(m, "Использование: /kick @user")
            return
        target = parse_mention_or_id(args[1])
    try:
        bot.kick_chat_member(m.chat.id, int(target))
        bot.unban_chat_member(m.chat.id, int(target))
        bot.send_message(m.chat.id, "👢 Пользователь кикнут.")
        log_action(m.chat.id, "kick", f"{target} by {m.from_user.id}")
    except Exception as e:
        bot.reply_to(m, f"Ошибка: {e}")

@bot.message_handler(commands=["mute"])
def cmd_mute(m):
    if m.chat.type not in ("group", "supergroup"):
        bot.reply_to(m, "Команда работает в группе.")
        return
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES and m.from_user.id != ADMIN_ID:
        bot.reply_to(m, "⛔️ Только админы могут использовать эту команду.")
        return
    args = m.text.split(maxsplit=2)
    if m.reply_to_message:
        target = m.reply_to_message.from_user.id
        dur = args[1] if len(args) > 1 else "10m"
    else:
        if len(args) < 2:
            bot.reply_to(m, "Использование: /mute 10m (или ответ на сообщение)")
            return
        target = parse_mention_or_id(args[1])
        dur = args[2] if len(args) > 2 else "10m"
    delta = parse_duration(dur)
    until = int((datetime.utcnow() + delta).timestamp()) if delta else 0
    try:
        bot.restrict_chat_member(m.chat.id, int(target), until_date=until, can_send_messages=False)
        expires_at = (datetime.utcnow() + delta).isoformat() if delta else None
        add_mute(m.chat.id, int(target), expires_at)
        bot.send_message(m.chat.id, f"🔇 Пользователь замьючен на {dur}")
        log_action(m.chat.id, "mute", f"{target} by {m.from_user.id} until {expires_at}")
    except Exception as e:
        bot.reply_to(m, f"Ошибка: {e}")

@bot.message_handler(commands=["unmute"])
def cmd_unmute(m):
    if m.chat.type not in ("group", "supergroup"):
        bot.reply_to(m, "Команда работает в группе.")
        return
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES and m.from_user.id != ADMIN_ID:
        bot.reply_to(m, "⛔️ Только админы могут использовать эту команду.")
        return
    if m.reply_to_message:
        target = m.reply_to_message.from_user.id
    else:
        args = m.text.split(maxsplit=1)
        if len(args) < 2:
            bot.reply_to(m, "Использование: /unmute @user")
            return
        target = parse_mention_or_id(args[1])
    try:
        bot.restrict_chat_member(m.chat.id, int(target), until_date=0, can_send_messages=True)
        remove_mute(m.chat.id, int(target))
        bot.send_message(m.chat.id, "🔊 Пользователь размучен.")
        log_action(m.chat.id, "unmute", f"{target} by {m.from_user.id}")
    except Exception as e:
        bot.reply_to(m, f"Ошибка: {e}")

@bot.message_handler(commands=["warn"])
def cmd_warn(m):
    if m.chat.type not in ("group", "supergroup"):
        bot.reply_to(m, "Команда работает в группе.")
        return
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES and m.from_user.id != ADMIN_ID:
        bot.reply_to(m, "⛔️ Только админы могут использовать эту команду.")
        return
    if m.reply_to_message:
        target = m.reply_to_message.from_user.id
        args = m.text.split(maxsplit=1)
        reason = args[1] if len(args) > 1 else "Без причины"
    else:
        args = m.text.split(maxsplit=2)
        if len(args) < 2:
            bot.reply_to(m, "Использование: /warn @user причина")
            return
        target = parse_mention_or_id(args[1])
        reason = args[2] if len(args) > 2 else "Без причины"
    try:
        add_warn(m.chat.id, int(target), m.from_user.id, reason)
        cnt = get_warns_count(m.chat.id, int(target))
        bot.send_message(m.chat.id, f"⚠️ Пользователю выдано предупреждение. Сейчас: {cnt}")
        log_action(m.chat.id, "warn", f"{target} by {m.from_user.id} reason:{reason}")
        if cnt >= 3:
            try:
                bot.kick_chat_member(m.chat.id, int(target))
                bot.send_message(m.chat.id, f"🔨 Пользователь авто-бан за {cnt} warn.")
                clear_warns(m.chat.id, int(target))
                log_action(m.chat.id, "auto_ban_warns", f"{target}")
            except:
                pass
    except Exception as e:
        bot.reply_to(m, f"Ошибка: {e}")

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
    t = threading.Thread(target=check_and_release_mutes, daemon=True)
    t.start()
    mode = os.getenv("MODE", "poll")
    if mode == "webhook":
        WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "")
        WEBHOOK_PORT = int(os.getenv("PORT", "8000"))
        bot.set_webhook(url=f"{WEBHOOK_HOST.rstrip('/')}/{TOKEN}")
        app.run(host="0.0.0.0", port=WEBHOOK_PORT)
    else:
        run_poll()
