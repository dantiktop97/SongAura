# main.py — BotPromoter для Render Web Service
# aiogram 3.22.0 + aiohttp
# polling + healthcheck + публикация в канал

import os, asyncio, logging, sqlite3, random, string
from datetime import datetime
from typing import Optional, List, Dict
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

# === ENV ===
TOKEN = os.getenv("PLAY")
CHANNEL = os.getenv("CHANNEL")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
PORT = int(os.getenv("PORT", "8000"))

# === Bot ===
bot = Bot(TOKEN)
dp = Dispatcher()

# === DB ===
db = sqlite3.connect("botpromoter.db", check_same_thread=False)
db.execute("""
CREATE TABLE IF NOT EXISTS ads (
  id INTEGER PRIMARY KEY,
  user_id INTEGER,
  title TEXT,
  text TEXT,
  created_at TEXT
);
""")
db.commit()

# === Utils ===
def now(): return datetime.utcnow().isoformat()
def save_ad(user_id, title, text):
    cur = db.cursor()
    cur.execute("INSERT INTO ads (user_id,title,text,created_at) VALUES (?,?,?)", (user_id, title, text, now()))
    db.commit()
    return cur.lastrowid

def get_user_name(msg): return msg.from_user.username or msg.from_user.first_name or "пользователь"

# === UI ===
def mk_kb(buttons: List[Dict]) -> InlineKeyboardMarkup:
    rows, row = [], []
    for b in buttons:
        btn = InlineKeyboardButton(text=b["text"], callback_data=b["callback_data"])
        row.append(btn)
        if len(row) == 2: rows.append(row); row = []
    if row: rows.append(row)
    rows.append([InlineKeyboardButton(text="Назад🔙", callback_data="back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

# === Wizard ===
wizard = {}

@dp.message(Command("start"))
async def start(msg: Message):
    name = get_user_name(msg)
    text = f"👋 Привет, {name}!\n\nДобро пожаловать в BotPromoter.\nНажми кнопку ниже, чтобы подать рекламу:"
    kb = mk_kb([
        {"text": "📢 Подать рекламу", "callback_data": "new"},
        {"text": "📊 Статистика", "callback_data": "stats"},
    ])
    await msg.answer(text, reply_markup=kb)

@dp.callback_query(lambda c: c.data == "new")
async def new_ad(cb: CallbackQuery):
    wizard[cb.from_user.id] = {"step": "title"}
    await cb.message.edit_text("📝 Введите заголовок объявления (до 100 символов):", reply_markup=mk_kb([]))

@dp.callback_query(lambda c: c.data == "back")
async def go_back(cb: CallbackQuery):
    await start(cb.message)

@dp.message()
async def wizard_input(msg: Message):
    uid = msg.from_user.id
    if uid not in wizard: return
    step = wizard[uid]["step"]
    if step == "title":
        wizard[uid]["title"] = msg.text[:100]
        wizard[uid]["step"] = "text"
        await msg.answer("✍️ Введите текст объявления (до 1000 символов):", reply_markup=mk_kb([]))
    elif step == "text":
        title = wizard[uid]["title"]
        text = msg.text[:1000]
        aid = save_ad(uid, title, text)
        preview = f"✨ Новая заявка #{aid}\n\n{title}\n\n{text}\n\n▶ @{get_user_name(msg)}"
        if CHANNEL:
            try: await bot.send_message(CHANNEL, preview)
            except: pass
        if ADMIN_ID:
            try: await bot.send_message(ADMIN_ID, f"📬 Заявка #{aid} от @{get_user_name(msg)} опубликована.")
            except: pass
        await msg.answer("✅ Заявка отправлена и опубликована в канал.", reply_markup=mk_kb([]))
        wizard.pop(uid)

# === Healthcheck ===
async def health(request): return web.Response(text="Bot is running")
async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# === Run ===
async def main():
    asyncio.create_task(start_web())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
