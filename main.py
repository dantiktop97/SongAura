#!/usr/bin/env python3
# main.py — Dev Tools Bot (aiogram polling)
# - весь интерфейс через inline-кнопки
# - много функций: статус, логи, deploy, добавить/удалить сервис, история действий, симуляция, help
# - короткая цепочка "Назад🔙" возвращает в главное меню
# - эмодзи и дружелюбные тексты
import os
import asyncio
import logging
import random
import sqlite3
import json
from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ====== Config ======
BOT_TOKEN = os.getenv("PLAY")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DB_PATH = os.getenv("DB_PATH", "devtools_full.db")
HEALTH_PORT = int(os.getenv("PORT", "8000"))

if not BOT_TOKEN:
    raise RuntimeError("Set PLAY env var with bot token")

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
    CREATE TABLE IF NOT EXISTS services (
        id INTEGER PRIMARY KEY,
        name TEXT UNIQUE,
        status TEXT,
        last_checked TEXT
    );
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY,
        service_name TEXT,
        level TEXT,
        message TEXT,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS actions (
        id INTEGER PRIMARY KEY,
        service_name TEXT,
        action TEXT,
        user_tg INTEGER,
        result TEXT,
        created_at TEXT
    );
    """)
    conn.commit()
    return conn

db = init_db()

# ====== Helpers ======
def is_admin(user_id: int) -> bool:
    return ADMIN_ID and int(user_id) == int(ADMIN_ID)

def ensure_service(name: str):
    cur = db.cursor()
    cur.execute("SELECT name FROM services WHERE name=?", (name,))
    if not cur.fetchone():
        cur.execute("INSERT INTO services (name,status,last_checked) VALUES (?,?,?)", (name, "unknown", now_iso()))
        db.commit()

def list_services():
    cur = db.cursor()
    cur.execute("SELECT name,status FROM services ORDER BY name")
    return cur.fetchall()

def write_log(service: str, level: str, message: str):
    cur = db.cursor()
    cur.execute("INSERT INTO logs (service_name,level,message,created_at) VALUES (?,?,?,?)",
                (service, level, message, now_iso()))
    db.commit()

def read_logs(service: str, limit: int = 50):
    cur = db.cursor()
    cur.execute("SELECT created_at, level, message FROM logs WHERE service_name=? ORDER BY id DESC LIMIT ?", (service, limit))
    return cur.fetchall()

def set_service_status(name: str, status: str):
    cur = db.cursor()
    cur.execute("UPDATE services SET status=?, last_checked=? WHERE name=?", (status, now_iso(), name))
    db.commit()

def get_service_status(name: str):
    cur = db.cursor()
    cur.execute("SELECT status,last_checked FROM services WHERE name=?", (name,))
    r = cur.fetchone()
    return r if r else ("unknown", None)

def record_action(service: str, action: str, user: int, result: str):
    cur = db.cursor()
    cur.execute("INSERT INTO actions (service_name,action,user_tg,result,created_at) VALUES (?,?,?,?,?)",
                (service, action, user, result, now_iso()))
    db.commit()

def read_actions(service: str, limit: int = 20):
    cur = db.cursor()
    cur.execute("SELECT created_at, action, user_tg, result FROM actions WHERE service_name=? ORDER BY id DESC LIMIT ?", (service, limit))
    return cur.fetchall()

# ====== UI builders ======
def main_menu_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Состояние сервиса", callback_data="ui:status")
    kb.button(text="📜 Логи", callback_data="ui:logs")
    kb.button(text="🚀 Deploy", callback_data="ui:deploy")
    kb.button(text="🛠 Сервисы", callback_data="ui:services")
    kb.button(text="📈 История действий", callback_data="ui:history")
    kb.button(text="⚙️ Симуляция логов", callback_data="ui:simulate")
    kb.button(text="❓ Помощь", callback_data="ui:help")
    return kb.as_markup(row_width=2)

def services_list_kb():
    kb = InlineKeyboardBuilder()
    rows = list_services()
    if not rows:
        kb.button(text="➕ Добавить сервис", callback_data="svc:add")
        kb.button(text="🔙 Назад", callback_data="back:main")
        return kb.as_markup()
    for name, status in rows:
        kb.button(text=f"{'🟢' if status=='ok' else '🟡' if status=='degraded' else '🔴'} {name}",
                  callback_data=f"svc:open:{name}")
    kb.button(text="➕ Добавить сервис", callback_data="svc:add")
    kb.button(text="🗑 Удалить сервис", callback_data="svc:remove")
    kb.button(text="🔙 Назад", callback_data="back:main")
    return kb.as_markup(row_width=1)

def service_kb(name: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Check status", callback_data=f"svc:check:{name}")
    kb.button(text="📜 Показать логи", callback_data=f"svc:logs:{name}")
    kb.button(text="🚀 Deploy", callback_data=f"svc:deploy:{name}")
    kb.button(text="📈 История", callback_data=f"svc:history:{name}")
    kb.button(text="🔙 Назад", callback_data="ui:services")
    return kb.as_markup(row_width=2)

def confirm_kb(prefix: str, val: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=f"{prefix}:confirm:{val}")
    kb.button(text="❌ Отмена", callback_data=f"{prefix}:cancel:{val}")
    return kb.as_markup()

# ====== Commands and menu ======
@dp.message(Command("start"))
async def cmd_start(message: Message):
    ensure_service("web-app")
    text = (
        "👋 Привет! Я Dev Tools Bot — помощник разработчика.\n"
        "Выбирай действие кнопкой ниже. Всё через inline‑кнопки, быстро и удобно.\n\n"
        "🔐 Если ты — админ, у тебя будут дополнительные действия (deploy, удаление)."
    )
    await message.answer(text, reply_markup=main_menu_kb())

@dp.callback_query(lambda c: c.data and c.data.startswith("ui:"))
async def handle_ui(callback: CallbackQuery):
    await callback.answer()
    cmd = callback.data.split(":", 1)[1]
    if cmd == "status":
        await callback.message.edit_text("🔎 Введите /status <service> или нажмите Сервисы → выбрать сервис.", reply_markup=main_menu_kb())
    elif cmd == "logs":
        await callback.message.edit_text("📜 Введите /logs <service> [n] или нажмите Сервисы → выбрать сервис.", reply_markup=main_menu_kb())
    elif cmd == "deploy":
        await callback.message.edit_text("🚀 Deploy — выбери сервис в разделе Сервисы, затем нажми Deploy.", reply_markup=main_menu_kb())
    elif cmd == "services":
        await callback.message.edit_text("🛠 Список сервисов:", reply_markup=services_list_kb())
    elif cmd == "history":
        await callback.message.edit_text("📈 История действий — выберите сервис в Сервисы → История.", reply_markup=main_menu_kb())
    elif cmd == "simulate":
        await callback.message.edit_text("⚙️ Симуляция логов включена — периодически будут появляться случайные логи.", reply_markup=main_menu_kb())
    elif cmd == "help":
        await callback.message.edit_text(
            "❓ Помощь:\n"
            "/status <service> — проверить статус\n"
            "/logs <service> [n] — последние n строк лога\n"
            "/deploy <service> — запустить mock deploy (только админ)\n\n"
            "Используйте меню Сервисы для быстрого доступа.\n🔙 Кнопка Назад возвращает в главное меню.",
            reply_markup=main_menu_kb()
        )
    else:
        await callback.message.edit_text("Неизвестная команда меню.", reply_markup=main_menu_kb())

# ====== Service navigation callbacks ======
@dp.callback_query(lambda c: c.data and c.data.startswith("svc:"))
async def handle_svc(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":", 2)
    action = parts[1]
    arg = parts[2] if len(parts) > 2 else None

    if action == "open" and arg:
        svc = arg
        status, last = get_service_status(svc)
        await callback.message.edit_text(f"📌 Сервис: {svc}\nСтатус: {status}\nПоследняя проверка: {last}",
                                         reply_markup=service_kb(svc))
    elif action == "check" and arg:
        svc = arg
        # simulate check
        status = random.choice(["ok", "degraded", "down"])
        set_service_status(svc, status)
        write_log(svc, "INFO", f"Status checked -> {status}")
        await callback.message.edit_text(f"🔎 Результат проверки: {svc} — {status}", reply_markup=service_kb(svc))
    elif action == "logs" and arg:
        svc = arg
        rows = read_logs(svc, limit=50)
        if not rows:
            await callback.message.edit_text("📭 Нет логов для этого сервиса.", reply_markup=service_kb(svc))
            return
        text = f"📜 Логи для {svc} (последние {min(len(rows),50)}):\n" + "\n".join([f"{r[0]} [{r[1]}] {r[2]}" for r in rows[:40]])
        await callback.message.edit_text(text, reply_markup=service_kb(svc))
    elif action == "deploy" and arg:
        svc = arg
        if not is_admin(callback.from_user.id):
            await callback.message.edit_text("⛔ Доступ запрещён. Только админ может запускать deploy.", reply_markup=service_kb(svc))
            return
        await callback.message.edit_text(f"🚀 Подготовка к deploy для {svc}...", reply_markup=confirm_kb("deploy", svc))
    elif action == "add":
        # short prompt: ask user to send "add:<name>"
        await callback.message.edit_text("➕ Введите имя нового сервиса в сообщении в формате: add:<имя>\nПример: add:api-server", reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="back:main").as_markup())
    elif action == "remove":
        # list services with delete buttons
        rows = list_services()
        if not rows:
            await callback.message.edit_text("Нет сервисов для удаления.", reply_markup=services_list_kb())
            return
        kb = InlineKeyboardBuilder()
        for name, _ in rows:
            kb.button(text=f"🗑 Удалить {name}", callback_data=f"svc:del:{name}")
        kb.button(text="🔙 Назад", callback_data="back:main")
        await callback.message.edit_text("Выберите сервис для удаления:", reply_markup=kb.as_markup(row_width=1))
    elif action == "del" and arg:
        svc = arg
        cur = db.cursor()
        cur.execute("DELETE FROM services WHERE name=?", (svc,))
        cur.execute("DELETE FROM logs WHERE service_name=?", (svc,))
        cur.execute("DELETE FROM actions WHERE service_name=?", (svc,))
        db.commit()
        await callback.message.edit_text(f"🗑 Сервис {svc} и связанные данные удалены.", reply_markup=services_list_kb())
    else:
        await callback.message.edit_text("Неизвестное действие сервиса.", reply_markup=main_menu_kb())

# ====== Deploy confirm/cancel ======
@dp.callback_query(lambda c: c.data and c.data.startswith("deploy:"))
async def handle_deploy_confirm(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":", 2)
    action = parts[1]
    svc = parts[2] if len(parts) > 2 else None
    if action == "confirm" and svc:
        await callback.message.edit_text(f"🚀 Deploy для {svc} запущен... Это симуляция.")
        record_action(svc, "deploy", callback.from_user.id, "started")
        # simulate steps
        await asyncio.sleep(1)
        write_log(svc, "INFO", "Deploy: pulling")
        await asyncio.sleep(1)
        write_log(svc, "INFO", "Deploy: migrating")
        await asyncio.sleep(1)
        ok = random.random() > 0.15
        if ok:
            write_log(svc, "INFO", "Deploy finished: success")
            set_service_status(svc, "ok")
            record_action(svc, "deploy", callback.from_user.id, "success")
            await callback.message.edit_text(f"✅ Deploy для {svc} завершён успешно.", reply_markup=service_kb(svc))
        else:
            write_log(svc, "ERROR", "Deploy failed: healthcheck")
            set_service_status(svc, "degraded")
            record_action(svc, "deploy", callback.from_user.id, "failed")
            await callback.message.edit_text(f"❌ Deploy для {svc} завершился с ошибкой.", reply_markup=service_kb(svc))
    else:
        await callback.message.edit_text("❌ Deploy отменён.", reply_markup=main_menu_kb())

# ====== Back navigation (короткая цепочка) ======
@dp.callback_query(lambda c: c.data and c.data.startswith("back:"))
async def handle_back(callback: CallbackQuery):
    await callback.answer()
    dest = callback.data.split(":", 1)[1]
    if dest == "main":
        await callback.message.edit_text("🔙 Возвращено в главное меню.", reply_markup=main_menu_kb())
    else:
        await callback.message.edit_text("🔙 Возвращено.", reply_markup=main_menu_kb())

# ====== Text commands for convenience ======
@dp.message(Command("status"))
async def cmd_status(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /status <service>")
        return
    svc = parts[1].strip()
    ensure_service(svc)
    status = random.choice(["ok", "degraded", "down"])
    set_service_status(svc, status)
    write_log(svc, "INFO", f"Status checked -> {status}")
    await message.answer(f"🔎 Service {svc}: {status}", reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="back:main").as_markup())

@dp.message(Command("logs"))
async def cmd_logs(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /logs <service> [n]")
        return
    svc = parts[1]
    n = 50
    if len(parts) >= 3:
        try:
            n = int(parts[2])
        except Exception:
            pass
    ensure_service(svc)
    rows = read_logs(svc, limit=n)
    if not rows:
        await message.answer("📭 Нет логов.", reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="back:main").as_markup())
        return
    text = f"📜 Логи для {svc}:\n" + "\n".join([f"{r[0]} [{r[1]}] {r[2]}" for r in rows[:40]])
    await message.answer(text, reply_markup=InlineKeyboardBuilder().button(text="🔙 Назад", callback_data="back:main").as_markup())

@dp.message(Command("deploy"))
async def cmd_deploy_text(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /deploy <service>")
        return
    svc = parts[1].strip()
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Только админ может запускать deploy.")
        return
    ensure_service(svc)
    await message.answer(f"Подтвердите deploy для {svc}:", reply_markup=confirm_kb("deploy", svc))

# Quick add via text: add:<name>
@dp.message()
async def text_handler(message: Message):
    text = (message.text or "").strip()
    if text.startswith("add:"):
        name = text.split(":",1)[1].strip()
        if not name:
            await message.answer("Неверный формат. Пример: add:api-server")
            return
        ensure_service(name)
        await message.answer(f"➕ Сервис {name} добавлен.", reply_markup=services_list_kb())
        return
    # fallback friendly reply
    await message.answer("Не распознал команду. Используйте главное меню или /help.", reply_markup=main_menu_kb())

# ====== History handler ======
@dp.callback_query(lambda c: c.data and c.data.startswith("svc:history:") or (c.data and c.data.startswith("ui:history")))
async def handle_history(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":", 2)
    if len(parts) == 3 and parts[1] == "history":
        svc = parts[2]
        rows = read_actions(svc, limit=30)
        if not rows:
            await callback.message.edit_text(f"📉 Для {svc} нет действий.", reply_markup=service_kb(svc))
            return
        text = f"📈 История действий для {svc}:\n" + "\n".join([f"{r[0]} | {r[1]} by {r[2]} -> {r[3]}" for r in rows])
        await callback.message.edit_text(text, reply_markup=service_kb(svc))
    else:
        await callback.message.edit_text("Выберите сервис и нажмите История.", reply_markup=main_menu_kb())

# ====== Health HTTP server (optional) ======
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

# ====== Background filler: simulate logs periodically ======
async def filler_task():
    while True:
        try:
            cur = db.cursor()
            cur.execute("SELECT name FROM services")
            rows = cur.fetchall()
            for (name,) in rows:
                if random.random() < 0.4:
                    lvl = random.choice(["INFO", "WARN", "ERROR"])
                    msg = random.choice([
                        "heartbeat ok",
                        "connection pool saturated",
                        "cache miss rate increased",
                        "external API timeout",
                        "request processed",
                        "DB connection restored",
                        "rate limit approaching"
                    ])
                    write_log(name, lvl, msg)
        except Exception:
            logger.exception("filler_task error")
        await asyncio.sleep(8)

# ====== Startup ======
async def on_startup():
    ensure_service("web-app")
    asyncio.create_task(start_health_server())
    asyncio.create_task(filler_task())

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
