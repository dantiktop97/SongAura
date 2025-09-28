#!/usr/bin/env python3
# main.py — BotPromoter (ad submission + moderation + scheduled posting + referral tracking)
# - aiogram polling + aiohttp web for Render (web service)
# - SQLite storage created automatically
# - All UI via inline buttons, universal "Назад🔙" navigation back to /start greeting
# - If CHANNEL env is empty, bot sends post preview to ADMIN_ID instead of posting to channel
# - Friendly texts and emojis, greeting with username, "О боте" page, everywhere "Назад🔙" returns to /start
#
# ENV:
# PLAY (required) — Telegram bot token
# ADMIN_ID (recommended) — telegram numeric id of admin (for approvals & previews)
# CHANNEL (optional) — target channel for auto posting (e.g. "@mychannel" or "-100123...")
# DB_PATH (optional) — path to sqlite file (default botpromoter.db)
# PORT (optional) — port for web health server (default 8000)
#
# Notes:
# - Test the bot with a throwaway bot first.
# - If CHANNEL is set, bot must be added to that channel and have posting rights.

import os
import asyncio
import logging
import sqlite3
import random
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ====== Config ======
BOT_TOKEN = os.getenv("PLAY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
CHANNEL = os.getenv("CHANNEL", "")  # if empty, publish previews to ADMIN_ID
DB_PATH = os.getenv("DB_PATH", "botpromoter.db")
PORT = int(os.getenv("PORT", "8000"))

if not BOT_TOKEN:
    raise RuntimeError("Set PLAY env var with bot token")

# ====== Logging ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("botpromoter")

# ====== Bot / Dispatcher ======
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ====== DB init ======
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
def create_user_if_not_exists(tg_id:int, username:Optional[str]=None):
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE tg_id=?", (tg_id,))
    if not cur.fetchone():
        cur.execute("INSERT INTO users (tg_id,username,created_at) VALUES (?,?,?)", (tg_id, username or "", now_iso()))
        db.commit()

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

# ====== UI builders (all back buttons use text "Назад🔙" and callback "back:main") ======
def main_greeting_text(user):
    uname = user[2] if user and user[2] else "друг"
    text = (
        f"👋 Привет, {uname}!\n\n"
        "Добро пожаловать в BotPromoter — место, где ты можешь продвигать своего Telegram‑бота, "
        "отправлять заявки, отслеживать статус и получать реф‑клики. 🚀\n\n"
        "Нажми кнопку ниже, чтобы начать. Все шаги простые, быстрые и управляются кнопками. 🔘"
    )
    return text

def mk_main_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="📝 Подать рекламу", callback_data="flow:new_ad")
    kb.button(text="📦 Мои объявления", callback_data="flow:my_ads")
    kb.button(text="🔗 Моя реф‑ссылка / Статистика", callback_data="flow:ref")
    kb.button(text="🧾 О боте", callback_data="flow:about")
    kb.button(text="❓ Помощь", callback_data="flow:help")
    if ADMIN_ID:
        kb.button(text="🔔 Ожидающие (админ)", callback_data="admin:pending")
    return kb.as_markup(row_width=2)

def mk_back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup()

def ad_preview_kb(ad_id:int):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"admin:approve:{ad_id}")
    kb.button(text="❌ Отклонить", callback_data=f"admin:reject:{ad_id}")
    kb.button(text="🚀 Опубликовать сейчас", callback_data=f"admin:postnow:{ad_id}")
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup(row_width=2)

def my_ads_kb(user_id:int):
    kb = InlineKeyboardBuilder()
    cur = db.cursor()
    cur.execute("SELECT id,title,status FROM ads WHERE user_id=? ORDER BY created_at DESC", (user_id,))
    rows = cur.fetchall()
    if not rows:
        kb.button(text="Назад🔙", callback_data="back:main")
        return kb.as_markup()
    for aid, title, status in rows:
        kb.button(text=f"{title} [{status}]", callback_data=f"flow:my_ad:{aid}")
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup(row_width=1)

# ====== Wizard state in memory (simple) ======
wizard_states = {}  # {tg_id: {"step":..., "fields": {...}}}

# ====== Handlers ======
@dp.message(Command("start"))
async def cmd_start(message:Message):
    args = (message.get_args() or "").strip()
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    user = get_user_by_tg(message.from_user.id)
    if args:
        # treat as referral param (e.g., t.me/BOT?start=ref_ad123)
        if args.startswith("ref_"):
            ref = args
            set_user_ref(message.from_user.id, ref)
            cur = db.cursor()
            cur.execute("UPDATE referrals SET clicks = clicks+1 WHERE ref_code=?", (ref,))
            db.commit()
            await message.answer(f"🔗 Спасибо! Реф ссылка зарегистрирована: {ref}")
    greeting = main_greeting_text(user)
    extra = (
        "\n\n📌 Кратко — как работает бот:\n"
        "• Подашь рекламу — она попадёт в очередь модерации. ✅\n"
        "• Админ одобрит — объявление можно опубликовать в канал или получить превью. 📣\n"
        "• В конце поста будет твоя реф‑ссылка, клики по ней учитываются. 🔎\n\n"
        "Нажми кнопку ниже, чтобы продолжить."
    )
    await message.answer(greeting + extra, reply_markup=mk_main_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("flow:"))
async def handle_flow(callback:CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":", 2)
    cmd = parts[1]
    user = get_user_by_tg(callback.from_user.id)
    if cmd == "new_ad":
        await callback.message.edit_text(
            "📝 Отлично! Давай создадим объявление.\n\n"
            "Шаг 1: Введите заголовок объявления (коротко, 80 символов максимум).",
            reply_markup=mk_back_kb()
        )
        wizard_states[callback.from_user.id] = {"step":"title", "fields":{}}
    elif cmd == "my_ads":
        if not user:
            await callback.message.edit_text("Ошибка: пользователь не найден.", reply_markup=mk_back_kb())
            return
        uid = user[0]
        await callback.message.edit_text("📦 Ваши объявления:", reply_markup=my_ads_kb(uid))
    elif cmd == "ref":
        cur = db.cursor()
        cur.execute("SELECT ref_code FROM users WHERE tg_id=?", (callback.from_user.id,))
        r = cur.fetchone()
        ref = r[0] if r else None
        cur.execute("SELECT ref_code,clicks,signups FROM referrals WHERE ref_code=?", (ref,))
        rr = cur.fetchone()
        text = "🔗 Ваша реф‑ссылка и статистика:\n\n"
        text += f"Реф: {ref or '—'}\n"
        if rr:
            text += f"Клики: {rr[1]}, Регистрации: {rr[2]}"
        else:
            text += "Клики и регистрации пока отсутствуют."
        text += "\n\nНазад — возвращает в главное меню."
        await callback.message.edit_text(text, reply_markup=mk_back_kb())
    elif cmd == "help":
        await callback.message.edit_text(
            "❓ Помощь и подсказки:\n\n"
            "• Подать рекламу — через кнопку 'Подать рекламу'.\n"
            "• Мои объявления — посмотреть статус и отозвать.\n"
            "• Админ видит список ожидающих и может одобрять/публиковать.\n\n"
            "Все экраны содержат кнопку 'Назад🔙', которая возвращает в меню /start.",
            reply_markup=mk_back_kb()
        )
    elif cmd == "about":
        about_text = (
            "🤖 О боте — BotPromoter\n\n"
            "Этот бот помогает размещать рекламу Telegram‑ботов и отслеживать рекламу через реф‑ссылки. "
            "Ключевые возможности:\n"
            "• Подача объявления через удобный wizard; 📝\n"
            "• Модерация заявок админом с превью и одобрением; ✅\n"
            "• Автопубликация в канал (если указан CHANNEL) или превью админу; 📣\n"
            "• Трекер кликов по реф‑ссылкам и простая статистика; 📊\n\n"
            "Правила: модерация обязательна, не размещаем спам или запрещённый контент. "
            "Если у тебя вопрос — пиши администратору. Удачи и больших кликов! 🚀"
        )
        await callback.message.edit_text(about_text, reply_markup=mk_back_kb())
    else:
        await callback.message.edit_text("Неизвестная опция. Назад🔙", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def handle_admin(callback:CallbackQuery):
    await callback.answer()
    if not (ADMIN_ID and callback.from_user.id == ADMIN_ID):
        await callback.message.edit_text("⛔ Доступ запрещён. Только админ может это делать.", reply_markup=mk_back_kb())
        return
    parts = callback.data.split(":",2)
    action = parts[1]
    arg = parts[2] if len(parts)>2 else None
    if action == "pending":
        rows = list_pending_ads()
        if not rows:
            await callback.message.edit_text("Нет ожидающих заявок. Назад🔙", reply_markup=mk_back_kb())
            return
        text = "🔔 Ожидающие заявки:\n\n" + "\n".join([f"#{r[0]} • {r[2]} • {r[3]} • {r[4]}" for r in rows])
        kb = InlineKeyboardBuilder()
        for aid, uid, title, package, created in rows:
            kb.button(text=f"#{aid} {title}", callback_data=f"admin:preview:{aid}")
        kb.button(text="Назад🔙", callback_data="back:main")
        await callback.message.edit_text(text, reply_markup=kb.as_markup(row_width=1))
    elif action == "preview" and arg:
        ad = get_ad(int(arg))
        if not ad:
            await callback.message.edit_text("Объявление не найдено. Назад🔙", reply_markup=mk_back_kb()); return
        aid, uid, title, text_body, media_json, package, target_channel, scheduled_at, status = ad
        preview = f"🔎 Заявка #{aid}\n\n{title}\n\n{(text_body[:800] + '...') if len(text_body)>800 else text_body}\n\nПакет: {package}\nСтатус: {status}\n"
        await callback.message.edit_text(preview, reply_markup=ad_preview_kb(aid))
    elif action == "approve" and arg:
        aid = int(arg)
        set_ad_status(aid, "approved")
        cur = db.cursor()
        cur.execute("SELECT tg_id FROM users WHERE id=(SELECT user_id FROM ads WHERE id=?)", (aid,))
        r = cur.fetchone()
        if r and r[0]:
            try:
                asyncio.create_task(bot.send_message(r[0], f"✅ Ваша заявка #{aid} одобрена модератором."))
            except Exception:
                pass
        await callback.message.edit_text(f"✅ Заявка #{aid} одобрена. Назад🔙", reply_markup=mk_back_kb())
    elif action == "reject" and arg:
        aid = int(arg)
        set_ad_status(aid, "rejected")
        cur = db.cursor()
        cur.execute("SELECT tg_id FROM users WHERE id=(SELECT user_id FROM ads WHERE id=?)", (aid,))
        r = cur.fetchone()
        if r and r[0]:
            try:
                asyncio.create_task(bot.send_message(r[0], f"❌ Ваша заявка #{aid} отклонена."))
            except Exception:
                pass
        await callback.message.edit_text(f"❌ Заявка #{aid} отклонена. Назад🔙", reply_markup=mk_back_kb())
    elif action == "postnow" and arg:
        aid = int(arg)
        await callback.message.edit_text("🚀 Публикация запускается...")
        ok = await publish_ad(aid)
        if ok:
            await callback.message.edit_text(f"✅ Объявление #{aid} опубликовано. Назад🔙", reply_markup=mk_back_kb())
        else:
            await callback.message.edit_text(f"❌ Ошибка при публикации #{aid}. Назад🔙", reply_markup=mk_back_kb())
    else:
        await callback.message.edit_text("Неизвестная админская команда. Назад🔙", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("flow:my_ad:"))
async def handle_my_ad(callback:CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":",2)
    aid = int(parts[2])
    ad = get_ad(aid)
    if not ad:
        await callback.message.edit_text("Объявление не найдено. Назад🔙", reply_markup=mk_back_kb()); return
    aid, uid, title, text_body, media_json, package, target_channel, scheduled_at, status = ad
    s = f"📌 #{aid} • {title}\nСтатус: {status}\nЗапланировано: {scheduled_at}\n\n{(text_body[:1000] + '...') if len(text_body)>1000 else text_body}"
    kb = InlineKeyboardBuilder()
    if status == "pending":
        kb.button(text="🗑 Отозвать заявку", callback_data=f"user:withdraw:{aid}")
    kb.button(text="Назад🔙", callback_data="back:main")
    await callback.message.edit_text(s, reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data and c.data.startswith("user:"))
async def handle_user_actions(callback:CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":",2)
    action = parts[1]
    arg = parts[2] if len(parts)>2 else None
    if action == "withdraw" and arg:
        aid = int(arg)
        cur = db.cursor()
        cur.execute("SELECT user_id FROM ads WHERE id=?", (aid,))
        r = cur.fetchone()
        user = get_user_by_tg(callback.from_user.id)
        if not r or not user or r[0] != user[0]:
            await callback.message.edit_text("⛔ Нельзя отменить — не ваш пост. Назад🔙", reply_markup=mk_back_kb()); return
        set_ad_status(aid, "rejected")
        await callback.message.edit_text("🗑 Заявка отозвана. Назад🔙", reply_markup=mk_back_kb())
    else:
        await callback.message.edit_text("Неизвестное действие. Назад🔙", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("back:"))
async def handle_back(callback:CallbackQuery):
    await callback.answer()
    dest = callback.data.split(":",1)[1]
    if dest == "main":
        user = get_user_by_tg(callback.from_user.id)
        greeting = main_greeting_text(user)
        extra = "\n\nНажми кнопку, чтобы продолжить."
        await callback.message.edit_text(greeting + extra, reply_markup=mk_main_kb())
    else:
        await callback.message.edit_text("🔙 Возврат в меню", reply_markup=mk_main_kb())

# ====== Wizard message flow handler ======
@dp.message()
async def wizard_messages(message:Message):
    uid = message.from_user.id
    if uid in wizard_states:
        st = wizard_states[uid]
        step = st.get("step")
        if step == "title":
            st.setdefault("fields", {})["title"] = message.text.strip()[:120]
            st["step"] = "text"
            await message.answer("✍️ Шаг 2: Отправьте текст объявления (до 800 символов).", reply_markup=mk_back_kb())
            return
        if step == "text":
            st["fields"]["text"] = message.text.strip()[:800]
            st["step"] = "package"
            kb = InlineKeyboardBuilder()
            kb.button(text="Free (очередь) 🕒", callback_data="pkg:free")
            kb.button(text="Featured (приоритет) ⭐", callback_data="pkg:featured")
            kb.button(text="Назад🔙", callback_data="back:main")
            await message.answer("Выберите пакет размещения:", reply_markup=kb.as_markup())
            return
    # convenience quick-add: add:title|text
    if message.text and message.text.startswith("add:"):
        parts = message.text.split(":",1)[1].split("|",1)
        title = parts[0].strip()
        text_body = parts[1].strip() if len(parts)>1 else "—"
        create_user_if_not_exists(uid, message.from_user.username or "")
        user = get_user_by_tg(uid)
        aid = save_ad(user[0], title, text_body, "", "free", CHANNEL or None, None)
        await message.answer(f"✅ Заявка создана #{aid}. Ожидает модерации. Назад🔙", reply_markup=mk_main_kb())
        return
    # if not in wizard, just remind to use menu
    await message.answer("Используй меню для действий или /start, чтобы вернуться. Назад🔙", reply_markup=mk_main_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("pkg:"))
async def handle_pkg(callback:CallbackQuery):
    await callback.answer()
    pkg = callback.data.split(":",1)[1]
    uid = callback.from_user.id
    st = wizard_states.get(uid)
    if not st or not st.get("fields"):
        await callback.message.edit_text("Ошибка состояния, начните заново. Назад🔙", reply_markup=mk_back_kb())
        wizard_states.pop(uid, None)
        return
    fields = st["fields"]
    create_user_if_not_exists(uid, callback.from_user.username or "")
    user = get_user_by_tg(uid)
    aid = save_ad(user[0], fields["title"], fields["text"], "", pkg, CHANNEL or None, None)
    wizard_states.pop(uid, None)
    await callback.message.edit_text(f"🎉 Готово! Заявка #{aid} отправлена на модерацию. Ожидайте. Назад🔙", reply_markup=mk_main_kb())

# ====== Publish logic (uses CHANNEL if set, otherwise sends preview to ADMIN_ID) ======
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
    post_text = f"✨ {title}\n\n{text_body}\n\n▶ Попробовать: {ref_link}\n\n❤️ Поддержите автора через реф‑ссылку!"
    success = False
    publish_target = target_channel or (CHANNEL if CHANNEL else None)
    try:
        if publish_target:
            await bot.send_message(publish_target, post_text)
            success = True
            logger.info("Posted ad %s to channel %s", aid, publish_target)
        else:
            if ADMIN_ID:
                await bot.send_message(ADMIN_ID, f"🔔 Preview for ad #{aid}:\n\n{post_text}")
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
                    await bot.send_message(r[0], f"✅ Ваша реклама #{aid} опубликована в {publish_target}.")
                else:
                    await bot.send_message(r[0], f"✅ Ваша реклама #{aid} готова. Администратор получил превью.")
            except Exception:
                pass
    return success

# ====== Scheduled runner for scheduled posts ======
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

# ====== Minimal aiohttp health + redirect (for Render web service) ======
async def start_web():
    try:
        from aiohttp import web
    except Exception:
        logger.info("aiohttp not installed; skipping web server")
        return
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
                pass
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            return web.HTTPFound(f"https://t.me/{bot_username}?start={ref}")
        except Exception:
            return web.Response(text="Redirect unavailable", status=500)

    app.router.add_get("/", health)
    app.router.add_get("/r/{ref}", redirect_ref)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Web server started on port %s", PORT)

# ====== Startup ======
async def on_startup():
    if ADMIN_ID:
        create_user_if_not_exists(ADMIN_ID, "admin")
    asyncio.create_task(start_web())
    asyncio.create_task(scheduled_runner())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(on_startup())
    logger.info("Starting polling")
    dp.run_polling(bot)
