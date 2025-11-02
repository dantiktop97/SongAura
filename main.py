import os
import asyncio
import logging
from datetime import datetime, timedelta, timezone
import re
import aiosqlite
from aiohttp import web
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

# ---------------------------------------------
# Конфигурация и логирование
# ---------------------------------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("PLAY")
if not TOKEN:
    raise SystemExit("❌ Не найден токен в переменной PLAY")

PORT = int(os.getenv("PORT", "8000"))
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", f"https://example.com{WEBHOOK_PATH}")  # свой домен Render

DB_PATH = "data.db"


# ---------------------------------------------
# Инициализация базы
# ---------------------------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                channel_identifier TEXT,
                expires_at TIMESTAMP
            )
            """
        )
        await db.commit()


async def db_query(query: str, params=(), fetch=False):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(query, params)
        await db.commit()
        if fetch:
            rows = await cursor.fetchall()
            return rows
        return []


# ---------------------------------------------
# Утилиты
# ---------------------------------------------
def parse_duration(spec: str):
    m = re.fullmatch(r"(\d+)\s*([smhd])", spec.strip(), re.IGNORECASE)
    if not m:
        return None
    value = int(m.group(1))
    unit = m.group(2).lower()
    return {
        "s": timedelta(seconds=value),
        "m": timedelta(minutes=value),
        "h": timedelta(hours=value),
        "d": timedelta(days=value),
    }.get(unit)


def fmt_dt(dt: datetime):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ---------------------------------------------
# Основные команды
# ---------------------------------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📁 Профиль", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="instruction")],
        [InlineKeyboardButton("⚙️ Настройка ОП", callback_data="setup_help")],
    ]
    text = (
        "👋 Привет! Я бот, который контролирует обязательные подписки (ОП).\n\n"
        "Команды:\n"
        "/setup @channel 24h — добавить ОП\n"
        "/unsetup @channel off — убрать ОП\n"
        "/status — список активных ОП\n"
        "\nДобавь меня в группу и сделай админом, чтобы я мог ограничивать пользователей."
    )
    await update.effective_message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "instruction":
        await q.message.reply_text(
            "📘 Инструкция:\n\n"
            "1️⃣ Добавь бота в канал и в группу (бот должен быть админом).\n"
            "2️⃣ В группе используй /setup @канал 24h (или 7d и т.д.)\n"
            "3️⃣ /unsetup @канал off — убрать.\n"
            "4️⃣ /status — активные проверки."
        )
    elif q.data == "setup_help":
        await q.message.reply_text("/setup @канал 24h — добавить\n/unsetup @канал off — убрать")
    elif q.data == "profile":
        chat = q.message.chat
        await q.message.reply_text(
            f"📁 Профиль:\n"
            f"ID: {chat.id}\n"
            f"Тип: {chat.type}\n"
            f"Имя: {chat.title or chat.username or chat.first_name}"
        )


async def setup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if len(context.args) < 2:
        return await msg.reply_text("Использование: /setup @канал 24h")

    identifier, duration = context.args[0], context.args[1]
    delta = parse_duration(duration)
    if not delta:
        return await msg.reply_text("Неверный формат времени. Пример: 24h, 30m, 7d")

    expires_at = datetime.now(timezone.utc) + delta
    await db_query(
        "INSERT INTO required_subs (chat_id, channel_identifier, expires_at) VALUES (?, ?, ?)",
        (msg.chat_id, identifier, expires_at),
    )
    await msg.reply_text(f"✅ Добавлено ОП на {identifier} до {fmt_dt(expires_at)}")


async def unsetup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        return await update.effective_message.reply_text("Использование: /unsetup @канал off")

    identifier, flag = context.args[0], context.args[1].lower()
    if flag != "off":
        return await update.effective_message.reply_text("Второй аргумент должен быть off")

    await db_query("DELETE FROM required_subs WHERE channel_identifier = ?", (identifier,))
    await update.effective_message.reply_text(f"✅ ОП {identifier} удалено")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = await db_query("SELECT channel_identifier, expires_at FROM required_subs WHERE chat_id=?", (chat_id,), True)
    if not subs:
        return await update.message.reply_text("📋 Ваши активные подписки:\n┗ Общее количество: 0")

    text = [f"📋 Ваши активные подписки:\n┗ Общее количество: {len(subs)}\n"]
    for i, (identifier, exp) in enumerate(subs, 1):
        dt = fmt_dt(datetime.fromisoformat(exp)) if exp else "∞"
        text.append(f"{i}️⃣ {identifier}\n┣ ⏳ Активна до: {dt}")
    await update.message.reply_text("\n".join(text))


# ---------------------------------------------
# Проверка подписки и реакция на сообщение
# ---------------------------------------------
async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not user or not msg:
        return

    # Получить активные ОП
    subs = await db_query(
        "SELECT id, channel_identifier, expires_at FROM required_subs WHERE chat_id=?",
        (chat.id,),
        True,
    )
    if not subs:
        return

    # Проверяем каждую подписку
    not_subscribed = []
    for _, identifier, expires_at in subs:
        if expires_at:
            if datetime.fromisoformat(expires_at) < datetime.now(timezone.utc):
                await db_query("DELETE FROM required_subs WHERE channel_identifier=?", (identifier,))
                continue

        try:
            channel_username = identifier.strip()
            if channel_username.startswith("@"):
                channel_username = channel_username[1:]

            member = await context.bot.get_chat_member(f"@{channel_username}", user.id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(identifier)
        except Exception:
            not_subscribed.append(identifier)

    if not not_subscribed:
        # Если пользователь подписан, снять ограничение (если есть)
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=ChatPermissions(can_send_messages=True)
            )
        except Exception:
            pass
        return

    # Удалить сообщение
    try:
        await msg.delete()
    except Exception:
        pass

    # Ограничить пользователя
    try:
        await context.bot.restrict_chat_member(
            chat.id, user.id, permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception:
        pass

    # Отправить уведомление с кнопкой
    for channel in not_subscribed:
        username_clean = channel.lstrip("@")
        link = f"https://t.me/{username_clean}"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔗 Подписаться", url=link)]]
        )
        text = (
            f"{user.mention_html()} чтобы писать в чат, необходимо подписаться на канал(ы):\n"
            f"{channel}"
        )
        await context.bot.send_message(
            chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


# ---------------------------------------------
# Основной запуск с aiohttp
# ---------------------------------------------
async def main():
    await init_db()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("setup", setup_handler))
    app.add_handler(CommandHandler("unsetup", unsetup_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))

    # aiohttp сервер
    aio_app = web.Application()

    async def handle(request):
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response(text="ok")

    aio_app.router.add_post(WEBHOOK_PATH, handle)

    await app.bot.set_webhook(WEBHOOK_URL)
    logger.info(f"🚀 Webhook установлен на {WEBHOOK_URL}")
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    logger.info(f"Бот запущен на порту {PORT}")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
