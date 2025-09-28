#!/usr/bin/env python3
# main.py — BotPromoter (ad submission + moderation + scheduled posting + referral tracking)
# - aiogram polling + aiohttp web for Render (web service)
# - SQLite storage created automatically
# - All UI via inline buttons, universal "Назад🔙" navigation back to /start greeting
# - If CHANNEL env is empty, bot sends post preview to ADMIN_ID instead of posting to channel
# - Friendly texts and emojis, greeting with username, "О боте" page, everywhere "Назад🔙" returns to menu
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
    kb.button(text="👤 Профиль", callback_data="menu:profile")
    kb.button(text="📢 Реклама", callback_data="menu:ads")
    kb.button(text="📊 Статистика", callback_data="menu:stats")
    kb.button(text="ℹ️ О боте", callback_data="menu:about")
    kb.button(text="❓ Помощь", callback_data="menu:help")
    if ADMIN_ID:
        kb.button(text="🔔 Админ", callback_data="menu:admin")
    return kb.as_markup(row_width=2)

def mk_back_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup()

def profile_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="✏️ Редактировать профиль", callback_data="profile:edit")
    kb.button(text="📜 Мои объявления", callback_data="profile:my_ads")
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup(row_width=2)

def ads_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Подать рекламу", callback_data="ads:new")
    kb.button(text="📌 Мои объявления", callback_data="ads:mine")
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup(row_width=2)

def stats_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔗 Моя реф‑ссылка", callback_data="stats:ref")
    kb.button(text="📈 Общая статистика", callback_data="stats:global")
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup(row_width=2)

def admin_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔔 Ожидающие заявки", callback_data="admin:pending")
    kb.button(text="⚙️ Настройки", callback_data="admin:settings")
    kb.button(text="Назад🔙", callback_data="back:main")
    return kb.as_markup(row_width=2)

# ====== Wizard state in memory (simple) ======
wizard_states = {}  # {tg_id: {"step":..., "fields": {...}}}

# ====== Handlers ======
@dp.message(Command("start"))
async def cmd_start(message:Message):
    args = (message.get_args() or "").strip()
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    user = get_user_by_tg(message.from_user.id)
    if args and args.startswith("ref_"):
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

@dp.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def handle_menu(callback:CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1]
    user = get_user_by_tg(callback.from_user.id)
    if cmd == "profile":
        text = "👤 Профиль\n\nЗдесь отображается информация о тебе. Выбери действие."
        await callback.message.edit_text(text, reply_markup=profile_kb())
    elif cmd == "ads":
        text = "📢 Реклама\n\nПодавай объявления и следи за статусом."
        await callback.message.edit_text(text, reply_markup=ads_kb())
    elif cmd == "stats":
        text = "📊 Статистика\n\nСмотри реф‑ссылки и общую аналитику."
        await callback.message.edit_text(text, reply_markup=stats_kb())
    elif cmd == "about":
        text = (
            "ℹ️ О боте\n\nBotPromoter — помощник для продвижения Telegram‑ботов.\n\n"
            "Функции:\n• Подача и модерация объявлений\n• Публикация в канал (если задан CHANNEL) или превью админу\n• Трекинг кликов по реф‑ссылкам\n\nНазад — возвращает в главное меню."
        )
        await callback.message.edit_text(text, reply_markup=mk_back_kb())
    elif cmd == "help":
        text = "❓ Помощь\n\nВсё управление через кнопки. Никаких команд — всё в интерфейсе."
        await callback.message.edit_text(text, reply_markup=mk_back_kb())
    elif cmd == "admin":
        if ADMIN_ID and callback.from_user.id == ADMIN_ID:
            await callback.message.edit_text("🔐 Панель администратора", reply_markup=admin_kb())
        else:
            await callback.message.edit_text("⛔ У вас нет прав администратора.", reply_markup=mk_back_kb())
    else:
        await callback.message.edit_text("Неизвестная опция. Назад🔙", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("ads:"))
async def handle_ads(callback:CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1]
    if cmd == "new":
        await callback.message.edit_text("📝 Подать рекламу — шаг 1: введите заголовок (до 120 символов).", reply_markup=mk_back_kb())
        wizard_states[callback.from_user.id] = {"step":"title","fields":{}}
    elif cmd == "mine":
        user = get_user_by_tg(callback.from_user.id)
        if not user:
            await callback.message.edit_text("Ошибка: профиль не найден.", reply_markup=mk_back_kb()); return
        cur = db.cursor()
        cur.execute("SELECT id,title,status FROM ads WHERE user_id=? ORDER BY created_at DESC", (user[0],))
        rows = cur.fetchall()
        if not rows:
            await callback.message.edit_text("У вас ещё нет заявок.", reply_markup=mk_back_kb()); return
        text = "📦 Ваши объявления:\n\n" + "\n".join([f"#{r[0]} • {r[1]} • {r[2]}" for r in rows])
        kb = InlineKeyboardBuilder()
        kb.button(text="Назад🔙", callback_data="back:main")
        await callback.message.edit_text(text, reply_markup=kb.as_markup())
    else:
        await callback.message.edit_text("Неизвестная опция в Рекламе.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("profile:"))
async def handle_profile(callback:CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1]
    if cmd == "edit":
        await callback.message.edit_text("✏️ Редактирование профиля — пока заглушка. Назад🔙", reply_markup=mk_back_kb())
    elif cmd == "my_ads":
        await callback.message.edit_text("Переход к моим объявлениям...", reply_markup=InlineKeyboardBuilder().button(text="Назад🔙", callback_data="back:main").as_markup())
    else:
        await callback.message.edit_text("Неизвестная опция профиля.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("stats:"))
async def handle_stats(callback:CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":",1)[1]
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
        await callback.message.edit_text(text, reply_markup=mk_back_kb())
    elif cmd == "global":
        cur = db.cursor()
        cur.execute("SELECT COUNT(*) FROM ads")
        total = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM clicks")
        clicks = cur.fetchone()[0]
        await callback.message.edit_text(f"📊 Общая статистика\nОбъявлений: {total}\nКликов: {clicks}", reply_markup=mk_back_kb())
    else:
        await callback.message.edit_text("Неизвестная опция статистики.", reply_markup=mk_back_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("admin:"))
async def handle_admin_actions(callback:CallbackQuery):
    await callback.answer()
    if not (ADMIN_ID and callback.from_user.id == ADMIN_ID):
        await callback.message.edit_text("⛔ Это админская зона. Назад🔙", reply_markup=mk_back_kb()); return
    parts = callback.data.split(":",2)
    action = parts[1]
    if action == "pending":
        rows = list_pending_ads()
        if not rows:
            await callback.message.edit_text("Нет ожидающих заявок.", reply_markup=mk_back_kb()); return
        kb = InlineKeyboardBuilder()
        for aid, uid, title, package, created in rows:
            kb.button(text=f"#{aid} {title}", callback_data=f"admin:preview:{aid}")
        kb.button(text="Назад🔙", callback_data="back:main")
        await callback.message.edit_text("🔔 Ожидающие заявки:", reply_markup=kb.as_markup(row_width=1))
    elif action == "settings":
        await callback.message.edit_text("⚙️ Настройки админа — пока заглушка.", reply_markup=mk_back_kb())
    elif action == "preview" and len(parts) > 2:
        aid = int(parts[2])
        ad = get_ad(aid)
        if not ad:
            await callback.message.edit_text("Объявление не найдено.", reply_markup=mk_back_kb()); return
        aid, uid, title, text_body, media_json, package, target_channel, scheduled_at, status = ad
        preview = f"🔎 Заявка #{aid}\n\n{title}\n\n{(text_body[:800] + '...') if len(text_body)>800 else text_body}\n\nПакет: {package}\nСтатус: {status}"
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ Одобрить", callback_data=f"admin:approve:{aid}")
        kb.button(text="❌ Отклонить", callback_data=f"admin:reject:{aid}")
        kb.button(text="🚀 Опубликовать сейчас", callback_data=f"admin:postnow:{aid}")
        kb.button(text="Назад🔙", callback_data="back:main")
        await callback.message.edit_text(preview, reply_markup=kb.as_markup(row_width=2))
    elif action in ("approve","reject","postnow") and len(parts) > 2:
        aid = int(parts[2])
        if action == "approve":
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
        elif action == "reject":
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
        elif action == "postnow":
            await callback.message.edit_text("🚀 Публикация запускается...")
            ok = await publish_ad(aid)
            if ok:
                await callback.message.edit_text(f"✅ Объявление #{aid} опубликовано. Назад🔙", reply_markup=mk_back_kb())
            else:
                await callback.message.edit_text(f"❌ Ошибка при публикации #{aid}. Назад🔙", reply_markup=mk_back_kb())
    else:
        await callback.message.edit_text("Неизвестная админская команда.", reply_markup=mk_back_kb())

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
            await message.answer("Выберите пакет размещения:", reply_markup=kb.as_markup(row_width=2))
            return
    # quick-add: add:title|text
    if message.text and message.text.startswith("add:"):
        parts = message.text.split(":",1)[1].split("|",1)
        title = parts[0].strip()
        text_body = parts[1].strip() if len(parts)>1 else "—"
        create_user_if_not_exists(uid, message.from_user.username or "")
        user = get_user_by_tg(uid)
        aid = save_ad(user[0], title, text_body, "", "free", CHANNEL or None, None)
        await message.answer(f"✅ Заявка создана #{aid}. Ожидает модерации. Назад🔙", reply_markup=mk_main_kb())
        return
    await message.answer("Используй меню или /start. Назад🔙", reply_markup=mk_main_kb())

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
