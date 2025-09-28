#!/usr/bin/env python3
# main.py — BotPromoter (robust, aiogram 3.22.0 compatible)
# - Inline UI only, max 2 buttons per row
# - Exception middleware: logs + sends traceback to ADMIN_ID
# - Safe sending/editing helpers
# - Polling by default; USE_WEBHOOK=1 enables webhook mode
# - On polling startup: deleteWebhook automatically
# - SQLite single connection, safe usage
#
# Env variables:
# PLAY (required) - bot token
# ADMIN_ID (optional) - admin telegram id (numeric)
# CHANNEL (optional) - channel username or id for publishing
# DB_PATH (optional) - sqlite file path (default botpromoter.db)
# PORT (optional) - web server port (default 8000)
# USE_WEBHOOK (optional) - "1" to use webhook mode
# WEBHOOK_URL (optional) - public url for webhook (if USE_WEBHOOK=1)
# WEBHOOK_PATH (optional) - path for webhook (default /webhook)

import os
import asyncio
import logging
import sqlite3
import traceback
from datetime import datetime
from typing import Optional

import aiohttp
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, Update
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.dispatcher.middlewares.base import BaseMiddleware

# ====== Config ======
BOT_TOKEN = os.getenv("PLAY")
if not BOT_TOKEN:
    raise RuntimeError("PLAY environment variable with bot token is required")

ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
CHANNEL = os.getenv("CHANNEL") or None
DB_PATH = os.getenv("DB_PATH", "botpromoter.db")
PORT = int(os.getenv("PORT", "8000"))
USE_WEBHOOK = os.getenv("USE_WEBHOOK", "0") == "1"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook")

# ====== Logging ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("botpromoter")
logging.getLogger("aiogram").setLevel(logging.INFO)

# ====== Bot / Dispatcher ======
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ====== DB ======
def now_iso():
    return datetime.utcnow().isoformat()

def init_db(path: str = DB_PATH):
    conn = sqlite3.connect(path, check_same_thread=False)
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        tg_id INTEGER UNIQUE,
        username TEXT,
        created_at TEXT,
        ref_code TEXT
    );
    CREATE TABLE IF NOT EXISTS ads (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        title TEXT,
        text TEXT,
        media_json TEXT,
        package TEXT,
        target_channel TEXT,
        scheduled_at TEXT,
        status TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS clicks (
        id INTEGER PRIMARY KEY,
        ad_id INTEGER,
        clicked_at TEXT,
        from_user INTEGER
    );
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY,
        ref_code TEXT UNIQUE,
        owner_user INTEGER,
        clicks INTEGER DEFAULT 0,
        signups INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    return conn

db = init_db()

# DB helper wrapper for safety
def db_execute(query: str, params: tuple = (), fetch: bool = False):
    cur = db.cursor()
    cur.execute(query, params)
    rv = None
    if fetch:
        rv = cur.fetchall()
    else:
        db.commit()
        rv = cur.lastrowid
    return rv

# ====== Utility functions ======
def create_user_if_not_exists(tg_id: int, username: Optional[str] = ""):
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE tg_id=?", (tg_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (tg_id,username,created_at) VALUES (?,?,?)", (tg_id, username or "", now_iso()))
        db.commit()

def get_user_by_tg(tg_id: int):
    cur = db.cursor()
    cur.execute("SELECT id,tg_id,username,ref_code FROM users WHERE tg_id=?", (tg_id,))
    return cur.fetchone()

def set_user_ref(tg_id: int, ref_code: str):
    cur = db.cursor()
    cur.execute("UPDATE users SET ref_code=? WHERE tg_id=?", (ref_code, tg_id))
    cur.execute("INSERT OR IGNORE INTO referrals (ref_code, owner_user) VALUES (?, (SELECT id FROM users WHERE tg_id=?))", (ref_code, tg_id))
    db.commit()

def save_ad(user_id:int, title:str, text:str, media_json:str, package:str, target_channel:Optional[str], scheduled_at:Optional[str]):
    cur = db.cursor()
    cur.execute("""INSERT INTO ads
        (user_id,title,text,media_json,package,target_channel,scheduled_at,status,created_at)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id,title,text,media_json,package,target_channel,scheduled_at,"pending", now_iso()))
    db.commit()
    return cur.lastrowid

def list_pending_ads():
    cur = db.cursor()
    cur.execute("SELECT id, user_id, title, package, created_at FROM ads WHERE status='pending' ORDER BY created_at")
    return cur.fetchall()

def get_ad(ad_id:int):
    cur = db.cursor()
    cur.execute("SELECT id,user_id,title,text,media_json,package,target_channel,scheduled_at,status FROM ads WHERE id=?", (ad_id,))
    return cur.fetchone()

def set_ad_status(ad_id:int, status:str):
    cur = db.cursor()
    cur.execute("UPDATE ads SET status=? WHERE id=?", (status, ad_id))
    db.commit()

def record_click(ad_id:int, from_user:Optional[int]):
    cur = db.cursor()
    cur.execute("INSERT INTO clicks (ad_id, clicked_at, from_user) VALUES (?,?,?)", (ad_id, now_iso(), from_user))
    db.commit()

def list_scheduled_ready():
    cur = db.cursor()
    cur.execute("SELECT id FROM ads WHERE status='approved' AND scheduled_at IS NOT NULL AND scheduled_at<=?", (now_iso(),))
    return [r[0] for r in cur.fetchall()]

# ====== Safe send/edit ======
async def safe_send(chat_id: int, text: str, **kwargs):
    try:
        # Accept both int ids and '@channel' strings
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        logger.exception("safe_send failed for %s", chat_id)
        return None

async def safe_edit(message_obj, text: str, **kwargs):
    try:
        return await message_obj.edit_text(text, **kwargs)
    except Exception:
        logger.exception("safe_edit failed, falling back to send")
        try:
            await safe_send(message_obj.chat.id, text)
        except Exception:
            logger.exception("fallback send also failed")
        return None

# ====== UI builders (2 per row) ======
def mk_row(*btns):
    kb = InlineKeyboardBuilder()
    for b in btns:
        kb.button(**b)
    return kb.as_markup(row_width=2)

def mk_main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Профиль", callback_data="menu:profile")
    kb.button(text="📢 Реклама", callback_data="menu:ads")
    kb.button(text="📊 Статистика", callback_data="menu:stats")
    kb.button(text="ℹ️ О боте", callback_data="menu:about")
    kb.button(text="❓ Помощь", callback_data="menu:help")
    if ADMIN_ID:
        kb.button(text="🔔 Админ", callback_data="menu:admin")
    return kb.as_markup(row_width=2)

def mk_back_kb():
    return mk_row({"text":"Назад🔙","callback_data":"back:main"})

def profile_kb():
    return mk_row({"text":"✏️ Редактировать профиль","callback_data":"profile:edit"},
                  {"text":"📜 Мои объявления","callback_data":"profile:my_ads"})

def ads_kb():
    return mk_row({"text":"➕ Подать рекламу","callback_data":"ads:new"},
                  {"text":"📌 Мои объявления","callback_data":"ads:mine"})

def stats_kb():
    return mk_row({"text":"🔗 Моя реф‑ссылка","callback_data":"stats:ref"},
                  {"text":"📈 Общая статистика","callback_data":"stats:global"})

def admin_kb():
    return mk_row({"text":"🔔 Ожидающие заявки","callback_data":"admin:pending"},
                  {"text":"⚙️ Настройки","callback_data":"admin:settings"})

# ====== Exception middleware (detailed traceback to admin) ======
class ExceptionLoggerMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except Exception as exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            logger.error("Unhandled exception:\n%s", tb)
            if ADMIN_ID:
                try:
                    short = f"⚠️ Ошибка: {type(exc).__name__}: {str(exc)[:200]}"
                    await bot.send_message(ADMIN_ID, short)
                    max_len = 3800
                    for i in range(0, len(tb), max_len):
                        chunk = tb[i:i+max_len]
                        await bot.send_message(ADMIN_ID, f"<pre>{chunk}</pre>", parse_mode="HTML")
                except Exception:
                    logger.exception("Failed to forward traceback to admin")
            raise

dp.update.middleware(ExceptionLoggerMiddleware())

# ====== Simple in-memory wizard state ======
wizard_states = {}  # {tg_id: {"step":..., "fields":{}}}

# ====== Handlers ======
@dp.message(Command("start"))
async def cmd_start(message: Message, command=None):
    # Safe extraction of args
    args = ""
    try:
        if command and hasattr(command, "args"):
            args = (command.args or "").strip()
        else:
            if message.text:
                parts = message.text.split(maxsplit=1)
                args = parts[1].strip() if len(parts) > 1 else ""
    except Exception:
        args = ""
    # user init
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    user = get_user_by_tg(message.from_user.id)
    if args and args.startswith("ref_"):
        try:
            set_user_ref(message.from_user.id, args)
            cur = db.cursor()
            cur.execute("UPDATE referrals SET clicks = clicks+1 WHERE ref_code=?", (args,))
            db.commit()
            await safe_send(message.chat.id, f"🔗 Реф ссылка зарегистрирована: {args}")
        except Exception:
            logger.exception("Failed to register referral")
    uname = user[2] if user and user[2] else message.from_user.first_name or "друг"
    greeting = f"👋 Привет, {uname}!\n\nДобро пожаловать в BotPromoter. Выбери раздел ниже."
    await safe_send(message.chat.id, greeting, reply_markup=mk_main_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def handle_menu(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "profile":
        text = "👤 Профиль\n\nИнформация о вас."
        await safe_edit(callback.message, text, reply_markup=profile_kb())
    elif cmd == "ads":
        text = "📢 Реклама\n\nУправляйте объявлениями."
        await safe_edit(callback.message, text, reply_markup=ads_kb())
    elif cmd == "stats":
        text = "📊 Статистика\n\nРеф‑ссылка и общие метрики."
        await safe_edit(callback.message, text, reply_markup=stats_kb())
    elif cmd == "about":
        text = "ℹ️ О боте\n\nBotPromoter — простой сервис подачи рекламы для Telegram‑ботов."
        await safe_edit(callback.message, text, reply_markup=mk_back_kb())
    elif cmd == "help":
        await safe_edit(callback.message, "❓ Помощь\n\nВсё управляется кнопками. Никаких команд.", reply_markup=mk_back_kb())
    elif cmd == "admin":
        if ADMIN_ID and callback.from_user.id == ADMIN_ID:
            await safe_edit(callback.message, "🔐 Панель администратора", reply_markup=admin_kb())
        else:
            await safe_edit(callback.message, "⛔ У вас нет прав администратора.", reply_markup=mk_back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная опция.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("ads:"))
async def handle_ads(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "new":
        wizard_states[callback.from_user.id] = {"step":"title","fields":{}}
        await safe_edit(callback.message, "📝 Подать рекламу — шаг 1: отправьте заголовок (до 120 символов).", reply_markup=mk_back_kb())
    elif cmd == "mine":
        user = get_user_by_tg(callback.from_user.id)
        if not user:
            await safe_edit(callback.message, "Ошибка: профиль не найден.", reply_markup=mk_back_kb()); return
        cur = db.cursor()
        cur.execute("SELECT id,title,status FROM ads WHERE user_id=? ORDER BY created_at DESC", (user[0],))
        rows = cur.fetchall()
        if not rows:
            await safe_edit(callback.message, "У вас нет заявок.", reply_markup=mk_back_kb()); return
        text = "📦 Ваши объявления:\n\n" + "\n".join([f"#{r[0]} • {r[1]} • {r[2]}" for r in rows])
        kb = InlineKeyboardBuilder()
        kb.button(text="Назад🔙", callback_data="back:main")
        await safe_edit(callback.message, text, reply_markup=kb.as_markup())
    else:
        await safe_edit(callback.message, "Неизвестная опция в Рекламе.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("profile:"))
async def handle_profile(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "edit":
        await safe_edit(callback.message, "✏️ Редактирование профиля — пока недоступно.", reply_markup=mk_back_kb())
    elif cmd == "my_ads":
        await handle_ads(callback)
    else:
        await safe_edit(callback.message, "Неизвестная опция профиля.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("stats:"))
async def handle_stats(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "ref":
        cur = db.cursor()
        cur.execute("SELECT ref_code FROM users WHERE tg_id=?", (callback.from_user.id,))
        r = cur.fetchone()
        ref = r[0] if r else None
        cur.execute("SELECT clicks,signups FROM referrals WHERE ref_code=?", (ref,))
        rr = cur.fetchone()
        text = f"🔗 Ваша реф‑ссылка: {ref or '—'}\n"
        if rr:
            text += f"Клики: {rr[0]}, Регистрации: {rr[1]}"
        else:
            text += "Данных пока нет."
        await safe_edit(callback.message, text, reply_markup=mk_back_kb())
    elif cmd == "global":
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM ads")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clicks")
        clicks = cur.fetchone()[0]
        await safe_edit(callback.message, f"📊 Общая статистика\nОбъявлений: {total}\nКликов: {clicks}", reply_markup=mk_back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная опция статистики.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def handle_admin_actions(callback: CallbackQuery):
    await callback.answer()
    if not (ADMIN_ID and callback.from_user.id == ADMIN_ID):
        await safe_edit(callback.message, "⛔ Это админская зона.", reply_markup=mk_back_kb()); return
    parts = callback.data.split(":",2)
    action = parts[1] if len(parts) > 1 else ""
    if action == "pending":
        rows = list_pending_ads()
        if not rows:
            await safe_edit(callback.message, "Нет ожидающих заявок.", reply_markup=mk_back_kb()); return
        kb = InlineKeyboardBuilder()
        for aid, uid, title, package, created in rows:
            kb.button(text=f"#{aid} {title}", callback_data=f"admin:preview:{aid}")
        kb.button(text="Назад🔙", callback_data="back:main")
        await safe_edit(callback.message, "🔔 Ожидающие заявки:", reply_markup=kb.as_markup(row_width=1))
    elif action == "settings":
        await safe_edit(callback.message, "⚙️ Настройки админа — заглушка.", reply_markup=mk_back_kb())
    elif action == "preview" and len(parts) > 2:
        try:
            aid = int(parts[2])
        except Exception:
            await safe_edit(callback.message, "Неверный id заявки.", reply_markup=mk_back_kb()); return
        ad = get_ad(aid)
        if not ad:
            await safe_edit(callback.message, "Объявление не найдено.", reply_markup=mk_back_kb()); return
        aid, uid, title, text_body, media_json, package, target_channel, scheduled_at, status = ad
        preview = f"🔎 Заявка #{aid}\n\n{title}\n\n{(text_body[:800] + '...') if len(text_body)>800 else text_body}\n\nПакет: {package}\nСтатус: {status}"
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Одобрить", callback_data=f"admin:approve:{aid}")
        kb.button(text="❌ Отклонить", callback_data=f"admin:reject:{aid}")
        kb.button(text="🚀 Опубликовать сейчас", callback_data=f"admin:postnow:{aid}")
        kb.button(text="Назад🔙", callback_data="back:main")
        await safe_edit(callback.message, preview, reply_markup=kb.as_markup(row_width=2))
    elif action in ("approve","reject","postnow") and len(parts) > 2:
        try:
            aid = int(parts[2])
        except Exception:
            await safe_edit(callback.message, "Неверный id заявки.", reply_markup=mk_back_kb()); return
        if action == "approve":
            set_ad_status(aid, "approved")
            cur = db.cursor()
            cur.execute("SELECT tg_id FROM users WHERE id=(SELECT user_id FROM ads WHERE id=?)", (aid,))
            r = cur.fetchone()
            if r and r[0]:
                try:
                    await safe_send(r[0], f"✅ Ваша заявка #{aid} одобрена модератором.")
                except Exception:
                    logger.exception("Notify owner failed")
            await safe_edit(callback.message, f"✅ Заявка #{aid} одобрена.", reply_markup=mk_back_kb())
        elif action == "reject":
            set_ad_status(aid, "rejected")
            cur = db.cursor()
            cur.execute("SELECT tg_id FROM users WHERE id=(SELECT user_id FROM ads WHERE id=?)", (aid,))
            r = cur.fetchone()
            if r and r[0]:
                try:
                    await safe_send(r[0], f"❌ Ваша заявка #{aid} отклонена.")
                except Exception:
                    logger.exception("Notify owner failed")
            await safe_edit(callback.message, f"❌ Заявка #{aid} отклонена.", reply_markup=mk_back_kb())
        elif action == "postnow":
            await safe_edit(callback.message, "🚀 Публикация запускается...")
            ok = await publish_ad(aid)
            if ok:
                await safe_edit(callback.message, f"✅ Объявление #{aid} опубликовано.", reply_markup=mk_back_kb())
            else:
                await safe_edit(callback.message, f"❌ Ошибка при публикации #{aid}.", reply_markup=mk_back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная админская команда.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("back:"))
async def handle_back(callback: CallbackQuery):
    await callback.answer()
    dest = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if dest == "main":
        user = get_user_by_tg(callback.from_user.id)
        uname = user[2] if user and user[2] else callback.from_user.first_name or "друг"
        greeting = f"👋 Привет, {uname}!\n\nВыбери раздел:"
        await safe_edit(callback.message, greeting, reply_markup=mk_main_kb())
    else:
        await safe_edit(callback.message, "🔙 Возврат", reply_markup=mk_main_kb())

# ====== Wizard text flow ======
@dp.message()
async def wizard_messages(message: Message):
    uid = message.from_user.id
    if uid in wizard_states:
        st = wizard_states[uid]
        step = st.get("step")
        try:
            if step == "title":
                st.setdefault("fields", {})["title"] = (message.text or "")[:120]
                st["step"] = "text"
                await safe_send(message.chat.id, "✍️ Шаг 2: Отправьте текст объявления (до 800 символов).", reply_markup=mk_back_kb())
                return
            if step == "text":
                st["fields"]["text"] = (message.text or "")[:800]
                st["step"] = "package"
                kb = InlineKeyboardBuilder()
                kb.button(text="Free (очередь) 🕒", callback_data="pkg:free")
                kb.button(text="Featured (приоритет) ⭐", callback_data="pkg:featured")
                kb.button(text="Назад🔙", callback_data="back:main")
                await safe_send(message.chat.id, "Выберите пакет размещения:", reply_markup=kb.as_markup(row_width=2))
                return
        except Exception:
            logger.exception("wizard_messages error")
            wizard_states.pop(uid, None)
            await safe_send(message.chat.id, "Ошибка процесса. Попробуйте снова.", reply_markup=mk_main_kb())
            return
    # fallback
    await safe_send(message.chat.id, "Используйте меню для действий.", reply_markup=mk_main_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("pkg:"))
async def handle_pkg(callback: CallbackQuery):
    await callback.answer()
    pkg = callback.data.split(":",1)[1] if ":" in callback.data else ""
    uid = callback.from_user.id
    st = wizard_states.get(uid)
    if not st or not st.get("fields"):
        wizard_states.pop(uid, None)
        await safe_edit(callback.message, "Ошибка состояния. Начните заново.", reply_markup=mk_back_kb())
        return
    fields = st["fields"]
    create_user_if_not_exists(uid, callback.from_user.username or "")
    user = get_user_by_tg(uid)
    aid = save_ad(user[0], fields.get("title",""), fields.get("text",""), "", pkg, CHANNEL, None)
    wizard_states.pop(uid, None)
    await safe_edit(callback.message, f"🎉 Готово! Заявка #{aid} отправлена на модерацию.", reply_markup=mk_main_kb())

# ====== Publish logic ======
async def publish_ad(ad_id:int):
    ad = get_ad(ad_id)
    if not ad:
        return False
    aid, uid, title, text_body, media_json, package, target_channel, scheduled_at, status = ad
    try:
        bot_info = await bot.get_me()
        bot_username = bot_info.username
    except Exception:
        bot_username = None
    ref_link = f"https://t.me/{bot_username}?start=ref_ad{aid}" if bot_username else f"ref_ad{aid}"
    post_text = f"✨ {title}\n\n{text_body}\n\n▶ Попробовать: {ref_link}"
    success = False
    publish_target = target_channel or CHANNEL
    try:
        if publish_target:
            await safe_send(publish_target, post_text)
            success = True
            logger.info("Posted ad %s to %s", aid, publish_target)
        else:
            if ADMIN_ID:
                await safe_send(ADMIN_ID, f"🔔 Preview for ad #{aid}:\n\n{post_text}")
            success = True
            logger.info("Preview for ad %s sent to admin", aid)
    except Exception:
        logger.exception("publish_ad send failed")
        success = False
    if success:
        set_ad_status(ad_id, "posted")
        cur = db.cursor()
        cur.execute("SELECT tg_id FROM users WHERE id=?", (uid,))
        r = cur.fetchone()
        if r and r[0]:
            try:
                if publish_target:
                    await safe_send(r[0], f"✅ Ваша реклама #{aid} опубликована в {publish_target}.")
                else:
                    await safe_send(r[0], f"✅ Ваша реклама #{aid} готова. Администратор получил превью.")
            except Exception:
                logger.exception("Failed to notify owner")
    return success

# ====== Scheduler ======
async def scheduled_runner():
    while True:
        try:
            ready = list_scheduled_ready()
            for aid in ready:
                logger.info("Scheduled publish for ad %s", aid)
                await publish_ad(aid)
        except Exception:
            logger.exception("scheduled_runner error")
        await asyncio.sleep(30)

# ====== Web server (health, redirect, webhook receiver) ======
async def start_web():
    app = web.Application()

    async def health(req):
        return web.Response(text="ok")

    async def redirect_ref(req):
        ref = req.match_info.get("ref")
        if ref and ref.startswith("ref_ad"):
            try:
                aid = int(ref.split("ref_ad",1)[1])
                record_click(aid, None)
            except Exception:
                logger.exception("redirect_ref parse error")
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            return web.HTTPFound(f"https://t.me/{bot_username}?start={ref}")
        except Exception:
            return web.Response(text="Redirect unavailable", status=500)

    async def handle_update(request):
        try:
            data = await request.json()
            upd = Update(**data)
            await dp.process_update(upd)
            return web.Response(text="ok")
        except Exception:
            logger.exception("Failed to process webhook update")
            return web.Response(status=500, text="error")

    app.router.add_get("/", health)
    app.router.add_get("/r/{ref}", redirect_ref)
    if USE_WEBHOOK:
        app.router.add_post(WEBHOOK_PATH, handle_update)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Web server started on port %s (webhook=%s)", PORT, USE_WEBHOOK)

# ====== Startup tasks ======
async def on_startup():
    if ADMIN_ID:
        create_user_if_not_exists(ADMIN_ID, "admin")
    asyncio.create_task(start_web())
    asyncio.create_task(scheduled_runner())

    # If polling mode - delete possible webhook to avoid conflicts
    if not USE_WEBHOOK:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook") as resp:
                    txt = await resp.text()
                    logger.info("deleteWebhook result: %s", txt)
        except Exception:
            logger.exception("Failed deleteWebhook")

    # If webhook mode - register webhook if WEBHOOK_URL provided
    if USE_WEBHOOK and WEBHOOK_URL:
        try:
            url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
            async with aiohttp.ClientSession() as s:
                async with s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", data={"url": url}) as resp:
                    txt = await resp.text()
                    logger.info("setWebhook result: %s", txt)
        except Exception:
            logger.exception("Failed setWebhook")

# ====== Entrypoint ======
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(on_startup())
    if USE_WEBHOOK:
        logger.info("Starting in webhook mode")
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            pass
    else:
        logger.info("Starting polling")
        try:
            # run_polling will manage clean shutdown on Ctrl+C; use single instance on Render
            dp.run_polling(bot)
        except Exception:
            logger.exception("Polling stopped with exception")
