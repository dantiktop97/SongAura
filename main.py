#!/usr/bin/env python3
# main.py — Business Bot (aiogram polling) с корректными inline клавиатурами и callback handlers,
# event engine, SQLite, и минимальным HTTP health (если нужно для Web Service)
import os
import json
import random
import logging
import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ====== Config ======
BOT_TOKEN = os.getenv("PLAY")
if not BOT_TOKEN:
    raise RuntimeError("Set PLAY env var with bot token")

DB_PATH = os.getenv("DB_PATH", "business.db")
EVENT_INTERVAL_SECONDS = int(os.getenv("EVENT_INTERVAL_SECONDS", str(60 * 60 * 12)))  # default 12h
HEALTH_PORT = int(os.getenv("PORT", "8000"))

# ====== Logging ======
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

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
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS businesses (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        type TEXT,
        name TEXT,
        balance INTEGER,
        level INTEGER DEFAULT 1,
        reputation INTEGER DEFAULT 0,
        last_event_at TEXT
    );
    CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY,
        business_id INTEGER,
        event_type TEXT,
        payload TEXT,
        resolved INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY,
        business_id INTEGER,
        amount INTEGER,
        reason TEXT,
        created_at TEXT
    );
    """)
    conn.commit()
    return conn

db = init_db()

# ====== Helpers ======
def get_user_by_tg(tg_id):
    cur = db.cursor()
    cur.execute("SELECT id,tg_id,username FROM users WHERE tg_id=?", (tg_id,))
    return cur.fetchone()

def create_user_if_not_exists(tg_id, username):
    if not get_user_by_tg(tg_id):
        cur = db.cursor()
        cur.execute("INSERT INTO users (tg_id,username,created_at) VALUES (?,?,?)", (tg_id, username or "", now_iso()))
        db.commit()

def get_business_for_user(tg_id):
    cur = db.cursor()
    cur.execute("""SELECT b.id,b.type,b.name,b.balance,b.level,b.reputation,b.last_event_at
                   FROM businesses b
                   JOIN users u ON u.id=b.user_id
                   WHERE u.tg_id=?""", (tg_id,))
    return cur.fetchone()

def create_business(tg_id, btype, name, start_balance=1000):
    cur = db.cursor()
    cur.execute("SELECT id FROM users WHERE tg_id=?", (tg_id,))
    r = cur.fetchone()
    if not r:
        return None
    uid = r[0]
    cur.execute("INSERT INTO businesses (user_id,type,name,balance,last_event_at) VALUES (?,?,?,?,?)",
                (uid, btype, name, start_balance, now_iso()))
    db.commit()
    return cur.lastrowid

# ====== Commands & UI ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    kb = InlineKeyboardBuilder()
    kb.button(text="Создать бизнес", callback_data="ui:create_business")
    kb.button(text="Мой бизнес", callback_data="ui:my_business")
    kb.button(text="События", callback_data="ui:events")
    kb.button(text="Топ", callback_data="ui:leaderboard")
    await message.answer(
        "Привет! Добро пожаловать в Business Bot.\nВыберите действие:",
        reply_markup=kb.as_markup()
    )

@dp.message(Command("create_business"))
async def cmd_create_business_text(message: Message):
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    if get_business_for_user(message.from_user.id):
        await message.answer("У вас уже есть бизнес. Посмотреть: /mybusiness")
        return
    create_business(message.from_user.id, "coffeeshop", "BeanLab", 1000)
    await message.answer("Создана кофейня BeanLab с балансом 1000 монет. Первые события будут генерироваться автоматически.")

@dp.message(Command("mybusiness"))
async def cmd_mybusiness(message: Message):
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    b = get_business_for_user(message.from_user.id)
    if not b:
        await message.answer("У вас нет бизнеса. Создайте: /create_business или нажмите кнопку Создать бизнес.")
        return
    bid, typ, name, balance, level, rep, last_ev = b
    await message.answer(f"{name} ({typ})\nБаланс: {balance}\nУровень: {level}\nРепутация: {rep}\nПоследнее событие: {last_ev}")

@dp.message(Command("leaderboard"))
async def cmd_leaderboard(message: Message):
    cur = db.cursor()
    cur.execute("SELECT name,balance FROM businesses ORDER BY balance DESC LIMIT 10")
    rows = cur.fetchall()
    if not rows:
        await message.answer("Топ пока пуст.")
        return
    text = "Топ бизнесов:\n" + "\n".join([f"{i+1}. {r[0]} — {r[1]} монет" for i, r in enumerate(rows)])
    await message.answer(text)

# ====== UI callbacks (menu) ======
@dp.callback_query(lambda c: c.data and c.data.startswith("ui:"))
async def handle_ui(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":", 1)[1]
    if cmd == "create_business":
        if get_business_for_user(callback.from_user.id):
            await callback.message.edit_text("У вас уже есть бизнес. Посмотреть: /mybusiness")
            return
        create_business(callback.from_user.id, "coffeeshop", "BeanLab", 1000)
        await callback.message.edit_text("Создана кофейня BeanLab с балансом 1000 монет.")
    elif cmd == "my_business":
        b = get_business_for_user(callback.from_user.id)
        if not b:
            await callback.message.edit_text("У вас нет бизнеса. Создайте через /create_business")
            return
        bid, typ, name, balance, level, rep, last_ev = b
        await callback.message.edit_text(f"{name} ({typ})\nБаланс: {balance}\nУровень: {level}\nРепутация: {rep}")
    elif cmd == "events":
        # trigger same as /events
        await callback.message.edit_text("Используйте команду /events или ждите уведомления о событии.")
    elif cmd == "leaderboard":
        await callback.message.edit_text("Используйте /leaderboard чтобы посмотреть топ.")
    else:
        await callback.message.edit_text("Неизвестная команда меню.")

# ====== Events: show and actions ======
@dp.message(Command("events"))
async def cmd_events(message: Message):
    create_user_if_not_exists(message.from_user.id, message.from_user.username or "")
    b = get_business_for_user(message.from_user.id)
    if not b:
        await message.answer("У вас нет бизнеса. Создайте: /create_business")
        return
    bid = b[0]
    cur = db.cursor()
    cur.execute("SELECT id,event_type,payload FROM events WHERE business_id=? AND resolved=0", (bid,))
    rows = cur.fetchall()
    if not rows:
        await message.answer("Нет активных событий.")
        return
    for eid, etype, payload in rows:
        data = json.loads(payload) if payload else {}
        kb = InlineKeyboardBuilder()
        kb.button(text="Инвестировать", callback_data=f"evt:{eid}:invest")
        kb.button(text="Игнорировать", callback_data=f"evt:{eid}:ignore")
        await message.answer(f"Событие: {etype}\n{data.get('msg','')}", reply_markup=kb.as_markup())

@dp.callback_query(lambda c: c.data and c.data.startswith("evt:"))
async def handle_event_action(callback: CallbackQuery):
    await callback.answer()
    try:
        _, eid_s, action = callback.data.split(":", 2)
        eid = int(eid_s)
    except Exception:
        await callback.message.edit_text("Некорректные данные действия.")
        return

    cur = db.cursor()
    cur.execute("SELECT business_id,event_type,payload FROM events WHERE id=? AND resolved=0", (eid,))
    ev = cur.fetchone()
    if not ev:
        await callback.message.edit_text("Событие уже обработано или не найдено.")
        return
    bid, etype, payload = ev

    if action == "invest":
        cur.execute("SELECT balance,name FROM businesses WHERE id=?", (bid,))
        bal = cur.fetchone()
        if not bal:
            await callback.message.edit_text("Бизнес не найден.")
            return
        balance = bal[0]
        name = bal[1]
        change = random.randint(-50, 300)
        newbal = balance + change - 200
        cur.execute("UPDATE businesses SET balance=? WHERE id=?", (newbal, bid))
        cur.execute("INSERT INTO transactions (business_id,amount,reason,created_at) VALUES (?,?,?,?)",
                    (bid, change-200, "invest", now_iso()))
        cur.execute("UPDATE events SET resolved=1 WHERE id=?", (eid,))
        db.commit()
        await callback.message.edit_text(f"Вы инвестировали 200. Результат: {'прибыль' if change>0 else 'убыток'} {change}. Баланс: {newbal}")
    elif action == "ignore":
        cur.execute("UPDATE events SET resolved=1 WHERE id=?", (eid,))
        cur.execute("UPDATE businesses SET reputation = reputation - 1 WHERE id=?", (bid,))
        db.commit()
        await callback.message.edit_text("Игнорирование. Репутация понижена на 1.")
    else:
        await callback.message.edit_text("Неизвестное действие.")

# ====== Event generator (background) ======
async def event_generator():
    await asyncio.sleep(5)
    while True:
        try:
            cur = db.cursor()
            cutoff_dt = datetime.utcnow() - timedelta(seconds=EVENT_INTERVAL_SECONDS)
            cutoff = cutoff_dt.isoformat()
            cur.execute("SELECT id,name FROM businesses WHERE last_event_at<?", (cutoff,))
            rows = cur.fetchall()
            for bid, bname in rows:
                etype = random.choice(["customer_complaint", "supplier_offer", "inspection"])
                payload = json.dumps({"msg": f"Случайное событие: {etype}"})
                cur.execute("INSERT INTO events (business_id,event_type,payload,created_at) VALUES (?,?,?,?)",
                            (bid, etype, payload, now_iso()))
                cur.execute("UPDATE businesses SET last_event_at=? WHERE id=?", (now_iso(), bid))
                db.commit()
                # notify owner
                cur2 = db.cursor()
                cur2.execute("SELECT u.tg_id FROM businesses b JOIN users u ON u.id=b.user_id WHERE b.id=?", (bid,))
                r = cur2.fetchone()
                if r:
                    tg_id = r[0]
                    try:
                        await bot.send_message(tg_id, f"Событие для бизнеса {bname}: {etype}\nИспользуйте /events чтобы посмотреть.")
                    except Exception:
                        logger.exception("Failed to send event notification")
        except Exception:
            logger.exception("Event generator error")
        # short sleep for testing; increase in production
        await asyncio.sleep(30)

# ====== Minimal health HTTP server (optional) ======
async def start_health_server():
    try:
        from aiohttp import web
    except Exception:
        logger.info("aiohttp not installed; skipping health server")
        return
    async def health(req):
        return web.Response(text="ok")
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", HEALTH_PORT)
    await site.start()
    logger.info("Health server started on port %s", HEALTH_PORT)

# ====== Startup ======
async def on_startup():
    # run background tasks
    asyncio.create_task(event_generator())
    asyncio.create_task(start_health_server())

if __name__ == "__main__":
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(on_startup())
        logger.info("Starting polling")
        dp.run_polling(bot)
    finally:
        try:
            loop.run_until_complete(bot.session.close())
        except Exception:
            pass
