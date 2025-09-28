#!/usr/bin/env python3
# main.py — BotPromoter final (robust, aiogram 3.22.0 compatible)
# Features:
# - Inline UI only, max 2 buttons per row
# - Back button everywhere
# - Referral generation and stats
# - Publish to CHANNEL when ad approved (or preview to ADMIN_ID)
# - Safe send/edit, exception middleware sends traceback to ADMIN_ID
# - Polling by default; USE_WEBHOOK=1 enables webhook mode
# - Auto deleteWebhook when starting polling to avoid conflicts
#
# ENV variables:
# PLAY (required) - bot token
# ADMIN_ID (optional) - numeric admin id
# CHANNEL (optional) - channel username or id (e.g. @mychannel or -100123...)
# DB_PATH (optional) - sqlite path (default botpromoter.db)
# PORT (optional) - web server port (default 8000)
# USE_WEBHOOK (optional) - "1" to enable webhook mode
# WEBHOOK_URL (optional) - public URL for webhook (if USE_WEBHOOK=1)
# WEBHOOK_PATH (optional) - path for webhook (default /webhook)

import os
import asyncio
import logging
import sqlite3
import traceback
import random
import string
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
    raise RuntimeError("PLAY env var (bot token) is required")

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

# ====== Database ======
def now_iso():
    return datetime.utcnow().isoformat()

def init_db(path=DB_PATH):
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

# ====== Helpers ======
def gen_ref_code(length=8):
    return "ref_" + "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

def create_user_if_not_exists(tg_id:int, username:Optional[str]=None):
    cur = db.cursor()
    cur.execute("SELECT id, ref_code FROM users WHERE tg_id=?", (tg_id,))
    row = cur.fetchone()
    if not row:
        ref = gen_ref_code()
        cur.execute("INSERT INTO users (tg_id,username,created_at,ref_code) VALUES (?,?,?,?)", (tg_id, username or "", now_iso(), ref))
        cur.execute("INSERT OR IGNORE INTO referrals (ref_code, owner_user) VALUES (?, (SELECT id FROM users WHERE tg_id=?))", (ref, tg_id))
        db.commit()
        return True
    return False

def ensure_user_and_ref(tg_id:int, username:Optional[str]=None):
    create_user_if_not_exists(tg_id, username)
    cur = db.cursor()
    cur.execute("SELECT ref_code FROM users WHERE tg_id=?", (tg_id,))
    r = cur.fetchone()
    if r and r[0]:
        return r[0]
    ref = gen_ref_code()
    cur.execute("UPDATE users SET ref_code=? WHERE tg_id=?", (ref, tg_id))
    cur.execute("INSERT OR IGNORE INTO referrals (ref_code, owner_user) VALUES (?, (SELECT id FROM users WHERE tg_id=?))", (ref, tg_id))
    db.commit()
    return ref

def get_user_by_tg(tg_id:int):
    cur = db.cursor()
    cur.execute("SELECT id,tg_id,username,ref_code FROM users WHERE tg_id=?", (tg_id,))
    return cur.fetchone()

def set_user_ref(tg_id:int, ref_code:str):
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

# ====== Safe send/edit helpers ======
async def safe_send(chat_id: int, text: str, **kwargs):
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception:
        logger.exception("safe_send failed for %s", chat_id)
        return None

async def safe_edit(message_obj, text: str, **kwargs):
    try:
        return await message_obj.edit_text(text, **kwargs)
    except Exception:
        logger.exception("safe_edit failed, fallback to send")
        try:
            await safe_send(message_obj.chat.id, text)
        except Exception:
            logger.exception("fallback send also failed")
        return None

# ====== UI builders: always row_width=2 ======
def mk_kb(buttons):
    kb = InlineKeyboardBuilder()
    for b in buttons:
        kb.button(**b)
    return kb.as_markup(row_width=2)

def main_kb():
    buttons = [
        {"text":"👤 Профиль", "callback_data":"menu:profile"},
        {"text":"📢 Подать рекламу", "callback_data":"menu:ads"},
        {"text":"📊 Статистика", "callback_data":"menu:stats"},
        {"text":"ℹ️ О боте", "callback_data":"menu:about"},
        {"text":"❓ Помощь", "callback_data":"menu:help"},
    ]
    if ADMIN_ID:
        buttons.append({"text":"🔔 Админ", "callback_data":"menu:admin"})
    return mk_kb(buttons)

def back_kb():
    return mk_kb([{"text":"Назад🔙", "callback_data":"back:main"}])

def profile_kb():
    return mk_kb([
        {"text":"✏️ Редактировать профиль", "callback_data":"profile:edit"},
        {"text":"📜 Мои объявления", "callback_data":"profile:my_ads"},
        {"text":"Назад🔙", "callback_data":"back:main"},
    ])

def ads_kb():
    return mk_kb([
        {"text":"➕ Создать заявку", "callback_data":"ads:new"},
        {"text":"📌 Мои заявки", "callback_data":"ads:mine"},
        {"text":"Назад🔙", "callback_data":"back:main"},
    ])

def stats_kb():
    return mk_kb([
        {"text":"🔗 Моя реф‑ссылка", "callback_data":"stats:ref"},
        {"text":"📈 Общая статистика", "callback_data":"stats:global"},
        {"text":"Назад🔙", "callback_data":"back:main"},
    ])

def admin_kb():
    return mk_kb([
        {"text":"🔔 Ожидающие заявки", "callback_data":"admin:pending"},
        {"text":"⚙️ Настройки", "callback_data":"admin:settings"},
        {"text":"Назад🔙", "callback_data":"back:main"},
    ])

# ====== Middleware: detailed exception -> admin ======
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
                    logger.exception("Failed to send traceback to admin")
            raise

dp.update.middleware(ExceptionLoggerMiddleware())

# ====== Wizard in memory ======
wizard_states = {}  # {tg_id: {"step":..., "fields": {...}}}

# ====== Handlers ======
@dp.message(Command("start"))
async def cmd_start(message: Message, command=None):
    # safe args extraction
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
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    ref = ensure_user_and_ref(message.from_user.id, message.from_user.username or "")
    if args and args.startswith("ref_"):
        set_user_ref(message.from_user.id, args)
        cur = db.cursor()
        cur.execute("UPDATE referrals SET clicks = clicks+1 WHERE ref_code=?", (args,))
        db.commit()
        await safe_send(message.chat.id, f"🔗 Ваша реф‑ссылка зарегистрирована: {args}\nСпасибо за поддержку! 👍")
    uname = (get_user_by_tg(message.from_user.id) or (None, None, message.from_user.username, ref))[2] or message.from_user.first_name or "друг"
    greeting = (
        f"👋 Привет, {uname}!\n\n"
        "Добро пожаловать в BotPromoter — удобный инструмент для продвижения Telegram‑ботов. 🚀\n\n"
        "Здесь ты можешь создать объявление, отслеживать статистику по реф‑ссылке и управлять своими заявками. Всё через кнопки ниже: 👇"
    )
    await safe_send(message.chat.id, greeting, reply_markup=main_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def handle_menu(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "profile":
        text = (
            "👤 Профиль\n\n"
            "Здесь хранится информация о вашем аккаунте и реф‑ссылка. "
            "Вы можете редактировать публичные данные и управлять своими объявлениями. 😊"
        )
        await safe_edit(callback.message, text, reply_markup=profile_kb())
    elif cmd == "ads":
        text = (
            "📢 Реклама\n\n"
            "Подайте объявление: опишите заголовок и текст. "
            "После модерации админ сможет одобрить и опубликовать в канал или отправить превью."
        )
        await safe_edit(callback.message, text, reply_markup=ads_kb())
    elif cmd == "stats":
        text = (
            "📊 Статистика\n\n"
            "Здесь показываются ваша реф‑ссылка и базовая аналитика кликов по ней. "
            "Данные обновляются автоматически при переходах по реф‑редиректам."
        )
        await safe_edit(callback.message, text, reply_markup=stats_kb())
    elif cmd == "about":
        text = (
            "ℹ️ О боте\n\n"
            "BotPromoter — минимальный сервис для продвижения ботов: подача объявлений, модерация, и публикация в канал. "
            "Если CHANNEL задан в настройках окружения, одобренные объявления публикуются туда автоматически. 💡"
        )
        await safe_edit(callback.message, text, reply_markup=back_kb())
    elif cmd == "help":
        text = (
            "❓ Помощь\n\n"
            "Используй кнопки для навигации. Не нужно вводить команды вручную. "
            "Если что‑то не работает — напиши админу."
        )
        await safe_edit(callback.message, text, reply_markup=back_kb())
    elif cmd == "admin":
        if ADMIN_ID and callback.from_user.id == ADMIN_ID:
            await safe_edit(callback.message, "🔐 Панель администратора — управление заявками и публикациями.", reply_markup=admin_kb())
        else:
            await safe_edit(callback.message, "⛔ У вас нет прав администратора.", reply_markup=back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная опция. Назад.", reply_markup=back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("profile:"))
async def handle_profile(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":",1)
    cmd = parts[1] if len(parts)>1 else ""
    if cmd == "edit":
        await safe_edit(callback.message, "✏️ Редактирование профиля — в разработке. Назад доступна.", reply_markup=back_kb())
    elif cmd == "my_ads":
        user = get_user_by_tg(callback.from_user.id)
        if not user:
            await safe_edit(callback.message, "Профиль не найден. Назад.", reply_markup=back_kb()); return
        cur = db.cursor()
        cur.execute("SELECT id,title,status FROM ads WHERE user_id=? ORDER BY created_at DESC", (user[0],))
        rows = cur.fetchall()
        if not rows:
            await safe_edit(callback.message, "У вас пока нет заявок. Назад.", reply_markup=back_kb()); return
        text = "📦 Ваши объявления:\n\n" + "\n".join([f"#{r[0]} • {r[1]} • {r[2]}" for r in rows])
        kb = mk_kb([{"text":"Назад🔙","callback_data":"back:main"}])
        await safe_edit(callback.message, text, reply_markup=kb)
    else:
        await safe_edit(callback.message, "Неизвестная опция профиля.", reply_markup=back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("ads:"))
async def handle_ads(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "new":
        wizard_states[callback.from_user.id] = {"step":"title","fields":{}}
        await safe_edit(callback.message, "📝 Шаг 1: отправьте заголовок объявления (макс 120 символов).", reply_markup=back_kb())
    elif cmd == "mine":
        user = get_user_by_tg(callback.from_user.id)
        if not user:
            await safe_edit(callback.message, "Ошибка: профиль не найден.", reply_markup=back_kb()); return
        cur = db.cursor()
        cur.execute("SELECT id,title,status FROM ads WHERE user_id=? ORDER BY created_at DESC", (user[0],))
        rows = cur.fetchall()
        if not rows:
            await safe_edit(callback.message, "У вас нет заявок.", reply_markup=back_kb()); return
        text = "📌 Мои заявки:\n\n" + "\n".join([f"#{r[0]} • {r[1]} • {r[2]}" for r in rows])
        await safe_edit(callback.message, text, reply_markup=back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная опция рекламы.", reply_markup=back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("stats:"))
async def handle_stats(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if cmd == "ref":
        ref = ensure_user_and_ref(callback.from_user.id, callback.from_user.username or "")
        cur = db.cursor()
        cur.execute("SELECT clicks,signups FROM referrals WHERE ref_code=?", (ref,))
        rr = cur.fetchone()
        text = f"🔗 Ваша реф‑ссылка: {ref}\n"
        if rr:
            text += f"Клики: {rr[0]}\nРегистрации: {rr[1]}"
        else:
            text += "Данных пока нет."
        await safe_edit(callback.message, text, reply_markup=back_kb())
    elif cmd == "global":
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM ads")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clicks")
        clicks = cur.fetchone()[0]
        await safe_edit(callback.message, f"📊 Общая статистика\nОбъявлений: {total}\nКликов: {clicks}", reply_markup=back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная опция статистики.", reply_markup=back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def handle_admin(callback: CallbackQuery):
    await callback.answer()
    if not (ADMIN_ID and callback.from_user.id == ADMIN_ID):
        await safe_edit(callback.message, "⛔ Это админская зона.", reply_markup=back_kb()); return
    parts = callback.data.split(":",2)
    action = parts[1] if len(parts)>1 else ""
    if action == "pending":
        rows = list_pending_ads()
        if not rows:
            await safe_edit(callback.message, "Нет ожидающих заявок.", reply_markup=back_kb()); return
        kb_buttons = []
        for aid, uid, title, package, created in rows:
            kb_buttons.append({"text": f"#{aid} {title[:30]}", "callback_data":f"admin:preview:{aid}"})
        kb_buttons.append({"text":"Назад🔙","callback_data":"back:main"})
        await safe_edit(callback.message, "🔔 Ожидающие заявки (нажми для превью):", reply_markup=mk_kb(kb_buttons))
    elif action == "preview" and len(parts)>2:
        try:
            aid = int(parts[2])
        except Exception:
            await safe_edit(callback.message, "Неверный id.", reply_markup=back_kb()); return
        ad = get_ad(aid)
        if not ad:
            await safe_edit(callback.message, "Заявка не найдена.", reply_markup=back_kb()); return
        aid, uid, title, text_body, media_json, package, target_channel, scheduled_at, status = ad
        preview = (
            f"🔎 Заявка #{aid}\n\n"
            f"Заголовок: {title}\n\n"
            f"{text_body[:1000] + ('...' if len(text_body)>1000 else '')}\n\n"
            f"Пакет: {package}\nСтатус: {status}\n"
        )
        kb_buttons = [
            {"text":"✅ Одобрить","callback_data":f"admin:approve:{aid}"},
            {"text":"❌ Отклонить","callback_data":f"admin:reject:{aid}"},
            {"text":"🚀 Опубликовать","callback_data":f"admin:postnow:{aid}"},
            {"text":"Назад🔙","callback_data":"back:main"},
        ]
        await safe_edit(callback.message, preview, reply_markup=mk_kb(kb_buttons))
    elif action in ("approve","reject","postnow") and len(parts)>2:
        try:
            aid = int(parts[2])
        except Exception:
            await safe_edit(callback.message, "Неверный id.", reply_markup=back_kb()); return
        if action == "approve":
            set_ad_status(aid, "approved")
            # notify author
            cur = db.cursor()
            cur.execute("SELECT tg_id FROM users WHERE id=(SELECT user_id FROM ads WHERE id=?)", (aid,))
            r = cur.fetchone()
            if r and r[0]:
                try:
                    await safe_send(r[0], f"✅ Ваша заявка #{aid} одобрена модератором. После публикации вы получите уведомление.")
                except Exception:
                    logger.exception("Notify owner failed")
            await safe_edit(callback.message, f"✅ Заявка #{aid} отмечена как approved.", reply_markup=back_kb())
        elif action == "reject":
            set_ad_status(aid, "rejected")
            cur = db.cursor()
            cur.execute("SELECT tg_id FROM users WHERE id=(SELECT user_id FROM ads WHERE id=?)", (aid,))
            r = cur.fetchone()
            if r and r[0]:
                try:
                    await safe_send(r[0], f"❌ Ваша заявка #{aid} отклонена модератором.")
                except Exception:
                    logger.exception("Notify owner failed")
            await safe_edit(callback.message, f"❌ Заявка #{aid} отклонена.", reply_markup=back_kb())
        elif action == "postnow":
            await safe_edit(callback.message, "🚀 Публикация запускается...")
            ok = await publish_ad(aid)
            if ok:
                await safe_edit(callback.message, f"✅ Объявление #{aid} опубликовано.", reply_markup=back_kb())
            else:
                await safe_edit(callback.message, f"❌ Ошибка при публикации #{aid}.", reply_markup=back_kb())
    else:
        await safe_edit(callback.message, "Неизвестная админская команда.", reply_markup=back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("back:"))
async def handle_back(callback: CallbackQuery):
    await callback.answer()
    dest = callback.data.split(":",1)[1] if ":" in callback.data else ""
    if dest == "main":
        user = get_user_by_tg(callback.from_user.id)
        uname = user[2] if user and user[2] else callback.from_user.first_name or "друг"
        greeting = f"👋 Привет, {uname}!\n\nВыберите раздел:"
        await safe_edit(callback.message, greeting, reply_markup=main_kb())
    else:
        await safe_edit(callback.message, "🔙 Возврат", reply_markup=main_kb())

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
                await safe_send(message.chat.id, "✍️ Шаг 2: отправьте основной текст объявления (до 2000 символов).", reply_markup=back_kb())
                return
            if step == "text":
                st["fields"]["text"] = (message.text or "")[:2000]
                st["step"] = "package"
                kb = mk_kb([
                    {"text":"Free (очередь) 🕒", "callback_data":"pkg:free"},
                    {"text":"Featured (приоритет) ⭐", "callback_data":"pkg:featured"},
                    {"text":"Назад🔙", "callback_data":"back:main"},
                ])
                await safe_send(message.chat.id, "Выберите пакет размещения:", reply_markup=kb)
                return
        except Exception:
            logger.exception("wizard_messages error")
            wizard_states.pop(uid, None)
            await safe_send(message.chat.id, "Ошибка процесса. Попробуйте снова.", reply_markup=main_kb())
            return
    # fallback: don't spam; show main menu
    await safe_send(message.chat.id, "Используйте меню для действий. Нажмите /start для главного меню.", reply_markup=main_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("pkg:"))
async def handle_pkg(callback: CallbackQuery):
    await callback.answer()
    pkg = callback.data.split(":",1)[1] if ":" in callback.data else ""
    uid = callback.from_user.id
    st = wizard_states.get(uid)
    if not st or not st.get("fields"):
        wizard_states.pop(uid, None)
        await safe_edit(callback.message, "Ошибка состояния. Начните заново.", reply_markup=main_kb())
        return
    fields = st["fields"]
    create_user_if_not_exists(uid, callback.from_user.username or "")
    user = get_user_by_tg(uid)
    aid = save_ad(user[0], fields.get("title",""), fields.get("text",""), "", pkg, CHANNEL, None)
    wizard_states.pop(uid, None)
    await safe_edit(callback.message, f"🎉 Готово! Заявка #{aid} отправлена на модерацию. Администратор проверит её в разделе «Ожидающие заявки».", reply_markup=main_kb())

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
    ref = get_user_by_tg(uid)[3] if get_user_by_tg(uid) else None
    ref_link = f"https://t.me/{bot_username}?start={ref}" if bot_username and ref else f"ref_ad{aid}"
    post_text = (
        f"✨ {title}\n\n"
        f"{text_body}\n\n"
        f"▶ Попробовать: {ref_link}\n\n"
        "Если вам понравился бот — поддержите автора кликом по ссылке. ❤️"
    )
    success = False
    publish_target = target_channel or CHANNEL
    try:
        if publish_target:
            # publish to channel (username or id)
            await bot.send_message(publish_target, post_text)
            success = True
            logger.info("Posted ad %s to %s", aid, publish_target)
        else:
            if ADMIN_ID:
                await safe_send(ADMIN_ID, f"🔔 Preview for ad #{aid}:\n\n{post_text}")
            success = True
            logger.info("Preview for ad %s sent to admin", aid)
    except Exception:
        logger.exception("publish_ad failed")
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
                logger.exception("Failed notify owner")
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

# ====== Web server (health, redirect, webhook) ======
async def start_web():
    app = web.Application()

    async def health(req):
        return web.Response(text="ok")

    async def redirect_ref(req):
        ref = req.match_info.get("ref")
        if ref and ref.startswith("ref_"):
            try:
                cur = db.cursor()
                cur.execute("UPDATE referrals SET clicks = clicks+1 WHERE ref_code=?", (ref,))
                db.commit()
            except Exception:
                logger.exception("redirect_ref DB error")
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
            logger.exception("Failed process webhook update")
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
    # remove webhook if polling to avoid conflict
    if not USE_WEBHOOK:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook") as resp:
                    txt = await resp.text()
                    logger.info("deleteWebhook result: %s", txt)
        except Exception:
            logger.exception("deleteWebhook failed")
    # register webhook if desired
    if USE_WEBHOOK and WEBHOOK_URL:
        try:
            url = f"{WEBHOOK_URL.rstrip('/')}{WEBHOOK_PATH}"
            async with aiohttp.ClientSession() as s:
                async with s.post(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook", data={"url": url}) as resp:
                    txt = await resp.text()
                    logger.info("setWebhook result: %s", txt)
        except Exception:
            logger.exception("setWebhook failed")

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
        logger.info("Starting polling (Instances must be 1)")
        try:
            dp.run_polling(bot)
        except Exception:
            logger.exception("Polling stopped with exception")
