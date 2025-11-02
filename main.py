import os import logging import re import aiosqlite import asyncio import nest_asyncio from aiohttp import web from datetime import datetime, timedelta, timezone from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions from telegram.ext import ( Application, CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, ContextTypes, filters, )

—————————–

Конфигурация

—————————–

logging.basicConfig(format=”%(asctime)s - %(levelname)s - %(message)s”, level=logging.INFO) logger = logging.getLogger(name)

TOKEN = os.getenv(“PLAY”) DB_PATH = “data.db”

—————————–

База данных

—————————–

async def init_db(): async with aiosqlite.connect(DB_PATH) as db: await db.execute(””” CREATE TABLE IF NOT EXISTS required_subs ( id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER, channel_identifier TEXT, expires_at TEXT ) “””) await db.commit()

async def db_query(query, params=(), fetch=False): async with aiosqlite.connect(DB_PATH) as db: cur = await db.execute(query, params) await db.commit() return await cur.fetchall() if fetch else []

—————————–

Вспомогательные функции

—————————–

def parse_duration(spec): m = re.fullmatch(r”(\d+)\s*([smhd])”, spec.strip(), re.IGNORECASE) if not m: return None num, unit = int(m.group(1)), m.group(2).lower() return {“s”: timedelta(seconds=num), “m”: timedelta(minutes=num), “h”: timedelta(hours=num), “d”: timedelta(days=num)}.get(unit)

def fmt_dt(dt): return dt.astimezone(timezone.utc).strftime(”%Y-%m-%d %H:%M UTC”) if dt else “∞”

def main_menu(): return InlineKeyboardMarkup([ [InlineKeyboardButton(“📘 Инструкция”, callback_data=“instruction”)], [InlineKeyboardButton(“📁 Профиль”, callback_data=“profile”)], [InlineKeyboardButton(“📋 Статус подписок”, callback_data=“status”)], ])

—————————–

Telegram-хендлеры

—————————–

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): name = update.effective_user.first_name or update.effective_user.username or “друг” await update.message.reply_text( f”👋 Привет, {name}!\n\n” “Я бот, который помогает контролировать обязательные подписки в Telegram-группах.\n” “📌 Я блокирую сообщения от пользователей, которые не подписались на нужные каналы.\n\n” “Выбери действие ниже 👇”, reply_markup=main_menu(), )

async def ping_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): await update.message.reply_text(“🏓 Я жив!”)

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): q = update.callback_query await q.answer() try: await q.message.delete() except: pass

kb = [[InlineKeyboardButton("🔙 Назад", callback_data="back")]]
if q.data == "instruction":
    await q.message.chat.send_message(
        "📘 Инструкция:\n\n"
        "1️⃣ Добавь меня в группу и сделай админом.\n"
        "2️⃣ Используй /setup @канал 24h — добавить обязательную подписку.\n"
        "3️⃣ /unsetup @канал — удалить.\n"
        "4️⃣ /status — список активных проверок.",
        reply_markup=InlineKeyboardMarkup(kb),
    )
elif q.data == "profile":
    chat = q.message.chat
    await q.message.chat.send_message(
        f"📁 Профиль:\n\n🆔 ID: {chat.id}\n💬 Тип: {chat.type}\n📛 Имя: {chat.title or chat.username or chat.first_name}",
        reply_markup=InlineKeyboardMarkup(kb),
    )
elif q.data == "status":
    subs = await db_query("SELECT channel_identifier, expires_at FROM required_subs WHERE chat_id=?", (q.message.chat.id,), True)
    if not subs:
        await q.message.chat.send_message("📋 Активных обязательных подписок нет.", reply_markup=InlineKeyboardMarkup(kb))
    else:
        text = [f"📋 Активные ОП ({len(subs)}):"]
        for i, (identifier, expires) in enumerate(subs, 1):
            dt = fmt_dt(datetime.fromisoformat(expires)) if expires else "∞"
            text.append(f"{i}. {identifier} — до {dt}")
        await q.message.chat.send_message("\n".join(text), reply_markup=InlineKeyboardMarkup(kb))
elif q.data == "back":
    await q.message.chat.send_message("🔙 Возврат в главное меню.\n\nВыбери действие ниже 👇", reply_markup=main_menu())


async def setup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): if len(context.args) < 2: return await update.message.reply_text(“Использование: /setup @канал 24h”) identifier, duration = context.args[0], context.args[1] delta = parse_duration(duration) if not delta: return await update.message.reply_text(“Неверный формат времени. Пример: 24h, 7d”) expires = datetime.now(timezone.utc) + delta await db_query(“INSERT INTO required_subs (chat_id, channel_identifier, expires_at) VALUES (?, ?, ?)”, (update.effective_chat.id, identifier, expires.isoformat())) await update.message.reply_text(f”✅ Добавлено ОП на {identifier} до {fmt_dt(expires)}”)

async def unsetup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): if len(context.args) < 1: return await update.message.reply_text(“Использование: /unsetup @канал”) await db_query(“DELETE FROM required_subs WHERE channel_identifier=?”, (context.args[0],)) await update.message.reply_text(f”✅ Убрано ОП с {context.args[0]}”)

async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE): msg, user, chat = update.effective_message, update.effective_user, update.effective_chat if not user or not msg: return subs = await db_query(“SELECT channel_identifier, expires_at FROM required_subs WHERE chat_id=?”, (chat.id,), True) if not subs: return

not_subscribed = []
for identifier, expires in subs:
    if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
        await db_query("DELETE FROM required_subs WHERE channel_identifier=?", (identifier,))
        continue
    try:
        member = await context.bot.get_chat_member(identifier, user.id)
        if member.status in ("left", "kicked"):
            not_subscribed.append(identifier)
    except:
        not_subscribed.append(identifier)

if not not_subscribed:
    try: await context.bot.restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=True))
    except: pass
    return

try: await msg.delete()
except: pass
try: await context.bot.restrict_chat_member(chat.id, user.id, permissions=ChatPermissions(can_send_messages=False))
except: pass

for channel in not_subscribed:
    link = f"https://t.me/{channel.strip('@')}"
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Подписаться", url=link)]])
    await context.bot.send_message(chat.id, f"{user.mention_html()}, чтобы писать в чат, необходимо подписаться на:\n{channel}", reply_markup=keyboard, parse_mode="HTML")


async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE): logger.info(f”my_chat_member update: {update.to_dict()}”)

—————————–

aiohttp-сервер для Render

—————————–

async def start_server(): app = web.Application() app.router.add_get(”/”, lambda request: web.Response(text=“✅ Бот работает через polling + aiohttp”)) runner = web.AppRunner(app) await runner.setup() site = web.TCPSite(runner, “0.0.0.0”, 8000) await site.start()

—————————–

Запуск polling + aiohttp

—————————–

async def main(): await init_db() tg_app = Application.builder().token(TOKEN).build() tg_app.add_handler(CommandHandler(“start”, start_handler)) tg_app.add_handler(CommandHandler(“ping”, ping_handler)) tg_app.add_handler(CommandHandler(“setup”, setup_handler)) tg_app.add_handler(CommandHandler(“unsetup”, unsetup_handler)) tg_app.add_handler(CallbackQueryHandler(callback_handler)) tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message)) tg_app.add_handler(ChatMemberHandler(chat_member_handler, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER))

    await asyncio.gather(
        tg_app.run_polling(),
        start_server()
    )

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
