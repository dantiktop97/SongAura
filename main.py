import os
import re
import json
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# -------- config --------
TOKEN = os.getenv("PLAY")  # keep empty in repo / CI
SUB_CHANNEL = os.getenv("SUB_CHANNEL", "@vzref2")
DB_PATH = os.getenv("DB_PATH", "data.db")      # sqlite for required_subs and chat_meta
USERS_PATH = os.getenv("USERS_PATH", "users.json")  # JSON file for user list
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or 0)
REPORT_CHANNEL = int(os.getenv("CHANNEL", "0") or 0)
ADMIN_STATUSES = ("administrator", "creator")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")
app = Flask(__name__)

# runtime state
_last_private_message = {}   # chat_id -> message_id
_broadcast_waiting = {}      # admin_id -> True

# -------- db (sqlite) helpers --------
def db_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    with db_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                channel TEXT,
                expires TEXT,
                created_at TEXT,
                added_by INTEGER
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS chat_meta (
                chat_id INTEGER PRIMARY KEY,
                title TEXT,
                added_by INTEGER
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

# -------- users.json helpers --------
def load_users():
    try:
        with open(USERS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(int(x) for x in data)
    except Exception:
        return set()

def save_users(users_set):
    try:
        with open(USERS_PATH, "w", encoding="utf-8") as f:
            json.dump(sorted(list(users_set)), f)
    except Exception as e:
        print("Failed to save users.json:", e)

def save_user_json(user_id):
    users = load_users()
    if int(user_id) not in users:
        users.add(int(user_id))
        save_users(users)

# -------- validation / utils --------
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
    except Exception:
        return False

def bot_is_admin_in(channel):
    try:
        me = bot.get_me()
        m = bot.get_chat_member(channel, me.id)
        return getattr(m, "status", "") in ADMIN_STATUSES
    except Exception:
        return False

def user_subscribed(user_id, channel):
    try:
        m = bot.get_chat_member(channel, user_id)
        return getattr(m, "status", "") not in ("left", "kicked")
    except Exception:
        return False

# -------- storage helpers (sqlite) --------
def save_chat_meta(chat, user_id=None):
    try:
        with db_conn() as c:
            c.execute("INSERT OR REPLACE INTO chat_meta(chat_id, title, added_by) VALUES(?,?,?)",
                      (chat.id, chat.title or "", user_id))
            c.commit()
    except:
        pass

def add_required_sub(chat_id, channel, expires_iso, added_by):
    created = now_iso()
    with db_conn() as c:
        c.execute("INSERT INTO required_subs(chat_id, channel, expires, created_at, added_by) VALUES(?,?,?,?,?)",
                  (chat_id, channel, expires_iso, created, added_by))
        c.commit()

def remove_required_sub(chat_id, channel):
    with db_conn() as c:
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (chat_id, channel))
        c.commit()

def get_required_subs_for_chat(chat_id):
    with db_conn() as c:
        rows = c.execute("SELECT channel, expires, created_at, added_by FROM required_subs WHERE chat_id=?", (chat_id,)).fetchall()
    return [{"channel": r[0], "expires": r[1], "created_at": r[2], "added_by": r[3]} for r in rows]

def cleanup_expired_for_chat(chat_id):
    now = now_iso()
    with db_conn() as c:
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND expires IS NOT NULL AND expires <= ?", (chat_id, now))
        c.commit()

# -------- keyboards / UI --------
def build_sub_kb(channels):
    kb = InlineKeyboardMarkup()
    for ch in channels:
        url = f"https://t.me/{ch.strip('@')}"
        kb.add(InlineKeyboardButton("🔗 Подписаться", url=url))
    kb.add(InlineKeyboardButton("✅ Проверить", callback_data="check_sub"))
    return kb

def build_admin_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 Рассылка всем пользователям", callback_data="admin_broadcast"))
    kb.add(InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"))
    kb.add(InlineKeyboardButton("🏆 Топ‑10 по ОП", callback_data="admin_top"))
    return kb

def send_private_replace(chat_id, text, reply_markup=None):
    save_user_json(chat_id)
    old = _last_private_message.get(chat_id)
    if old:
        try:
            bot.delete_message(chat_id, old)
        except:
            pass
    m = bot.send_message(chat_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
    _last_private_message[chat_id] = m.message_id
    return m

# -------- texts --------
INSTRUCTION_TEXT = (
    "📘 *Инструкция по настройке:*\n\n"
    "1️⃣ *Добавь меня в группу/чат и сделай админом.*\n\n"
    "2️⃣ В группе/чате используй:\n"
    "`/setup @канал 24h` — добавить обязательную подписку.\n"
    "⏱ *Время:* `30s`, `15m`, `12h`, `7d`.\n\n"
    "3️⃣ */unsetup @канал* — убрать подписку.\n\n"
    "4️⃣ */status* — список активных проверок.\n\n"
    "ℹ️ *Как это работает:*\n"
    "• Пользователь пишет сообщение в чат.\n"
    "• Бот проверяет его подписку.\n"
    "• Если подписка есть — сообщение остаётся.\n"
    "• Если нет — сообщение удаляется, а пользователю отправляется кнопка 🔗 Подписаться.\n\n"
    "———————————————\n\n"
    "💡 *Используя бота, вы подтверждаете согласие с политикой конфиденциальности.*"
)

SUB_PROMPT_TEXT = "*Чтобы пользоваться ботом, нужно подписаться на канал:*"

# -------- handlers --------
@bot.message_handler(commands=["start"])
def cmd_start(m):
    save_user_json(m.from_user.id)
    if m.chat.type in ("group", "supergroup"):
        bot.send_message(m.chat.id,
            "👋 Привет, я бот‑фильтр.\nЯ проверяю обязательные подписки и удаляю сообщения тех, кто не подписан.\n\n📌 Для настройки напиши мне в личку.")
        return

    if user_subscribed(m.from_user.id, SUB_CHANNEL):
        send_private_replace(m.from_user.id, INSTRUCTION_TEXT)
    else:
        send_private_replace(m.from_user.id, SUB_PROMPT_TEXT, reply_markup=build_sub_kb([SUB_CHANNEL]))

    if ADMIN_ID and m.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Меню админа", callback_data="admin_menu"))
        bot.send_message(m.from_user.id, "Меню админа:", reply_markup=kb)

@bot.message_handler(commands=["admin"])
def cmd_admin(m):
    if m.chat.type != "private":
        return
    if m.from_user.id != ADMIN_ID:
        return
    kb = build_admin_menu()
    bot.send_message(m.chat.id, "Меню админа:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.chat.type == "private")
def private_any(m):
    save_user_json(m.from_user.id)
    return

@bot.callback_query_handler(func=lambda c: c.data == "check_sub")
def cb_check(c):
    user_id = c.from_user.id
    chat = c.message.chat if c.message else None

    # group-level check
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

    # private check
    if user_subscribed(user_id, SUB_CHANNEL):
        send_private_replace(user_id, INSTRUCTION_TEXT)
    else:
        send_private_replace(user_id, SUB_PROMPT_TEXT, reply_markup=build_sub_kb([SUB_CHANNEL]))
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

# -------- admin callbacks & broadcast --------
@bot.callback_query_handler(func=lambda c: c.data == "admin_menu")
def cb_admin_menu(c):
    if c.from_user.id != ADMIN_ID:
        try:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
        except:
            pass
        return
    kb = build_admin_menu()
    bot.send_message(c.from_user.id, "Меню админа:", reply_markup=kb)
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "admin_broadcast")
def cb_admin_broadcast(c):
    if c.from_user.id != ADMIN_ID:
        try:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
        except:
            pass
        return
    bot.send_message(c.from_user.id, "✏️ Введите текст рассылки.\nТекст будет отправлен всем пользователям и всем группам из базы.")
    _broadcast_waiting[c.from_user.id] = True
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

@bot.message_handler(func=lambda m: _broadcast_waiting.get(m.from_user.id, False) and m.chat.type == "private")
def handle_broadcast_text(m):
    if m.from_user.id != ADMIN_ID:
        return
    text = (m.text or "").strip()
    _broadcast_waiting.pop(m.from_user.id, None)
    if not text:
        bot.send_message(m.chat.id, "⛔️ Текст пустой. Рассылка отменена.")
        return

    threading.Thread(target=mass_send, args=(text,), daemon=True).start()
    bot.send_message(m.chat.id, "📤 Рассылка запущена.")

# -------- mass send (background) --------
def mass_send(text):
    users = load_users()
    with db_conn() as c:
        chats = [row[0] for row in c.execute("SELECT chat_id FROM chat_meta").fetchall()]

    total = len(users)
    sent = 0
    deleted = 0
    sent_chats = 0
    failed_chats = 0

    print(f"📤 mass_send started: {total} users, {len(chats)} chats")

    # send to users (personal chats)
    for uid in list(users):
        try:
            bot.send_message(uid, text, parse_mode="Markdown", disable_web_page_preview=True)
            sent += 1
            time.sleep(0.05)
        except telebot.apihelper.ApiTelegramException as e:
            err = str(e)
            if any(x in err for x in [
                "bot was blocked by the user",
                "user is deactivated",
                "chat not found",
                "Forbidden"
            ]):
                users.remove(uid)
                save_users(users)
                deleted += 1
            else:
                print(f"⚠️ Ошибка при отправке {uid}: {e}")
        except Exception as e:
            print(f"⚠️ Неизвестная ошибка при отправке {uid}: {e}")

    # send to chats (groups/supergroups)
    for cid in chats:
        try:
            bot.send_message(cid, text, parse_mode="Markdown", disable_web_page_preview=True)
            sent_chats += 1
            time.sleep(0.05)
        except Exception as e:
            failed_chats += 1
            print(f"⚠️ Ошибка при отправке в чат {cid}: {e}")

    report_text = (
        f"✅ Рассылка завершена\n"
        f"📬 Отправлено ЛС: {sent}\n"
        f"🗑 Удалено неактивных из ЛС: {deleted}\n"
        f"👥 Было всего в users.json: {total}\n"
        f"📉 Сейчас в users.json: {len(users)}\n"
        f"📨 Отправлено в чаты: {sent_chats}\n"
        f"❗️Не доставлено в чаты: {failed_chats}"
    )
    try:
        if ADMIN_ID:
            bot.send_message(ADMIN_ID, report_text)
        else:
            print(report_text)
    except Exception:
        print("Failed to send broadcast report to admin.")

# -------- admin stats / top callbacks --------
@bot.callback_query_handler(func=lambda c: c.data == "admin_stats")
def cb_admin_stats(c):
    if c.from_user.id != ADMIN_ID:
        try:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
        except:
            pass
        return
    with db_conn() as conn:
        chats_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM required_subs").fetchone()[0]
        total_ops = conn.execute("SELECT COUNT(*) FROM required_subs").fetchone()[0]
        users_count = len(load_users())
        last_active = conn.execute("SELECT last_active FROM users ORDER BY last_active DESC LIMIT 1").fetchone() if False else None
        last_active = "—"
    lines = [
        f"📊 Статистика:",
        f"• Чатов с активными ОП: {chats_count}",
        f"• Всего ОП: {total_ops}",
        f"• Уникальных пользователей в users.json: {users_count}",
        f"• Последняя активность: {last_active}"
    ]
    bot.send_message(c.from_user.id, "\n".join(lines), disable_web_page_preview=True)
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

@bot.callback_query_handler(func=lambda c: c.data == "admin_top")
def cb_admin_top(c):
    if c.from_user.id != ADMIN_ID:
        try:
            bot.answer_callback_query(c.id, "Доступ запрещён", show_alert=True)
        except:
            pass
        return
    with db_conn() as conn:
        rows = conn.execute("""
            SELECT rs.chat_id, rs.channel, rs.expires, rs.created_at, rs.added_by, cm.title
            FROM required_subs rs
            LEFT JOIN chat_meta cm ON rs.chat_id = cm.chat_id
            ORDER BY rs.chat_id, rs.created_at ASC
        """).fetchall()

    if not rows:
        bot.send_message(c.from_user.id, "🏆 Пока нет активных ОП.")
        try:
            bot.answer_callback_query(c.id)
        except:
            pass
        return

    from collections import defaultdict
    grouped = defaultdict(list)
    for r in rows:
        grouped[r[0]].append(r)

    items = sorted(grouped.items(), key=lambda x: -len(x[1]))[:10]

    lines = ["🏆 Топ‑10 чатов по количеству ОП:"]
    for i, (chat_id, subs) in enumerate(items, 1):
        title = subs[0][5] or ""
        added_by = subs[0][4]
        chat_link = f"https://t.me/c/{str(chat_id)[4:]}" if str(chat_id).startswith("-100") else f"https://t.me/{chat_id}"
        name = f"[{title}]({chat_link})" if title else f"`{chat_id}`"
        lines.append(f"{i}. {name} — {len(subs)} ОП")
        if added_by:
            lines.append(f"  Добавил: [профиль](tg://user?id={added_by})")
        for s in subs:
            ch = s[1]
            expires = s[2]
            created = s[3]
            try:
                dt1 = datetime.fromisoformat(created)
                dt2 = datetime.fromisoformat(expires)
                delta = dt2 - dt1
                hours = round(delta.total_seconds() / 3600)
                lines.append(f"  • {ch} — {hours}ч до {dt2.strftime('%Y-%m-%d %H:%M')}")
            except:
                lines.append(f"  • {ch} — до {expires}")
        lines.append("")
    bot.send_message(c.from_user.id, "\n".join(lines), disable_web_page_preview=True)
    try:
        bot.answer_callback_query(c.id)
    except:
        pass

# -------- setup / unsetup / status / group handler --------
@bot.message_handler(commands=["setup"])
def cmd_setup(m):
    save_user_json(m.from_user.id)
    if m.chat.type not in ("group", "supergroup"):
        return
    cleanup_expired_for_chat(m.chat.id)
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES:
        bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
        return

    args = m.text.split(maxsplit=2)
    if len(args) < 3:
        bot.reply_to(m, "Использование: /setup @канал 24h")
        return
    raw_ch, dur = args[1], args[2]
    ch = normalize_channel(raw_ch)
    if not ch:
        bot.reply_to(m, "⛔️ Неверный формат канала. Пример: @example_channel")
        return
    if not channel_exists(ch):
        bot.reply_to(m, f"⛔️ Канал {ch} не найден в Telegram.")
        return
    if not bot_is_admin_in(ch):
        bot.reply_to(m, f"⛔️ Бот не администратор в канале {ch}. Добавьте бота в админы канала.")
        return
    delta = parse_duration(dur)
    if not delta:
        bot.reply_to(m, "⛔️ Неверный формат времени. Примеры: 30s, 15m, 12h, 7d")
        return
    expires = (datetime.utcnow() + delta).isoformat()

    with db_conn() as c:
        cur = c.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        if cur.fetchone():
            bot.reply_to(m, f"⚠️ Канал {ch} уже добавлен в обязательные подписки.")
            return
        c.execute("INSERT INTO required_subs(chat_id, channel, expires, created_at, added_by) VALUES(?,?,?,?,?)",
                  (m.chat.id, ch, expires, now_iso(), m.from_user.id))
        c.commit()

    save_chat_meta(m.chat, m.from_user.id)
    bot.reply_to(m, f"✅ Добавлено обязательное условие: подписка на {ch} до {fmt_dt_iso(expires)}")

    try:
        if REPORT_CHANNEL:
            dt2 = datetime.fromisoformat(expires)
            hours = round((dt2 - datetime.utcnow()).total_seconds() / 3600)
            chat_link = f"https://t.me/c/{str(m.chat.id)[4:]}" if str(m.chat.id).startswith("-100") else f"https://t.me/{m.chat.id}"
            who = f"[{m.from_user.first_name}](tg://user?id={m.from_user.id})"
            report = (
                "📥 *Добавлена ОП*\n\n"
                f"👤 {who}\n"
                f"💬 [{m.chat.title}]({chat_link})\n"
                f"📎 {ch}\n"
                f"⏱ *{hours}ч* до {dt2.strftime('%Y-%m-%d %H:%M')}"
            )
            bot.send_message(REPORT_CHANNEL, report, disable_web_page_preview=True)
    except:
        pass

@bot.message_handler(commands=["unsetup"])
def cmd_unsetup(m):
    save_user_json(m.from_user.id)
    if m.chat.type not in ("group", "supergroup"):
        return
    try:
        member = bot.get_chat_member(m.chat.id, m.from_user.id)
    except:
        bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
        return
    if getattr(member, "status", "") not in ADMIN_STATUSES:
        bot.reply_to(m, "⛔️ Недостаточно прав. Только админы могут использовать эту команду.")
        return

    args = m.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(m, "Использование: /unsetup @канал")
        return
    ch = normalize_channel(args[1])
    if not ch:
        bot.reply_to(m, "⛔️ Неверный формат канала. Пример: @example_channel")
        return
    with db_conn() as c:
        cur = c.execute("SELECT 1 FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        if not cur.fetchone():
            bot.reply_to(m, f"⛔️ Канал {ch} не добавлен в обязательные подписки для этого чата.")
            return
        c.execute("DELETE FROM required_subs WHERE chat_id=? AND channel=?", (m.chat.id, ch))
        c.commit()
    bot.reply_to(m, f"✅ Удалена проверка: {ch}")

@bot.message_handler(commands=["status"])
def cmd_status(m):
    save_user_json(m.from_user.id)
    if m.chat.type not in ("group", "supergroup"):
        return
    cleanup_expired_for_chat(m.chat.id)
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        bot.send_message(m.chat.id, "📋 Активных обязательных подписок нет.")
        return
    lines = [f"📋 Активные проверки ({len(subs)}):"]
    for i, s in enumerate(subs, 1):
        dt = fmt_dt_iso(s.get("expires"))
        lines.append(f"{i}. {s['channel']} — до {dt}")
        lines.append(f"/unsetup {s['channel']} — Убрать ОП")
        lines.append("———————————————")
    bot.send_message(m.chat.id, "\n".join(lines))

@bot.message_handler(func=lambda m: m.chat.type in ("group", "supergroup"))
def group_message_handler(m):
    save_user_json(m.from_user.id)
    save_chat_meta(m.chat, m.from_user.id)
    cleanup_expired_for_chat(m.chat.id)
    subs = get_required_subs_for_chat(m.chat.id)
    if not subs:
        return
    required = []
    for s in subs:
        ch = s["channel"]
        if not channel_exists(ch):
            try:
                bot.send_message(m.chat.id, f"⛔️ Канал {ch} не найден. Уберите или исправьте ОП через /unsetup {ch}")
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

# -------- webhook / run --------
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
