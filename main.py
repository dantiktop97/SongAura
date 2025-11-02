import os
import asyncio
import logging
import re
import aiosqlite
from datetime import datetime, timedelta, timezone
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
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)

# -----------------------------
# Конфигурация
# -----------------------------
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("PLAY")
if not TOKEN:
    raise SystemExit("❌ Не найден токен бота в переменной PLAY")

DB_PATH = "data.db"


# -----------------------------
# Работа с базой данных
# -----------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                channel_identifier TEXT,
                expires_at TEXT
            )
            """
        )
        await db.commit()


async def db_query(query, params=(), fetch=False):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(query, params)
        await db.commit()
        if fetch:
            return await cur.fetchall()
        return []


# -----------------------------
# Вспомогательные функции
# -----------------------------
def parse_duration(spec):
    m = re.fullmatch(r"(\d+)\s*([smhd])", spec.strip(), re.IGNORECASE)
    if not m:
        return None
    num, unit = int(m.group(1)), m.group(2).lower()
    return {
        "s": timedelta(seconds=num),
        "m": timedelta(minutes=num),
        "h": timedelta(hours=num),
        "d": timedelta(days=num),
    }.get(unit)


def fmt_dt(dt):
    if not dt:
        return "∞"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# -----------------------------
# Хендлеры
# -----------------------------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("📁 Профиль", callback_data="profile")],
        [InlineKeyboardButton("📘 Инструкция", callback_data="instruction")],
    ]
    await update.message.reply_text(
        "👋 Привет! Я бот для проверки обязательных подписок.\n\n"
        "💡 Команды:\n"
        "/setup @канал 24h — добавить обязательную подписку\n"
        "/unsetup @канал — удалить\n"
        "/status — посмотреть активные проверки.",
        reply_markup=InlineKeyboardMarkup(kb),
    )


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "instruction":
        await q.message.reply_text(
            "📘 Инструкция:\n"
            "1️⃣ Добавь бота в группу и сделай админом.\n"
            "2️⃣ Используй /setup @канал 24h — добавить проверку.\n"
            "3️⃣ /unsetup @канал — убрать.\n"
            "4️⃣ /status — список активных проверок."
        )
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
        return await msg.reply_text("Неверный формат времени. Пример: 24h, 7d")

    expires = datetime.now(timezone.utc) + delta
    await db_query(
        "INSERT INTO required_subs (chat_id, channel_identifier, expires_at) VALUES (?, ?, ?)",
        (msg.chat_id, identifier, expires.isoformat()),
    )
    await msg.reply_text(f"✅ Добавлено ОП на {identifier} до {fmt_dt(expires)}")


async def unsetup_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 1:
        return await update.message.reply_text("Использование: /unsetup @канал")
    identifier = context.args[0]
    await db_query("DELETE FROM required_subs WHERE channel_identifier=?", (identifier,))
    await update.message.reply_text(f"✅ Убрано ОП с {identifier}")


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = await db_query(
        "SELECT channel_identifier, expires_at FROM required_subs WHERE chat_id=?",
        (chat_id,),
        True,
    )
    if not subs:
        return await update.message.reply_text("📋 Активных обязательных подписок нет.")

    text = [f"📋 Активные ОП ({len(subs)}):\n"]
    for i, (identifier, expires) in enumerate(subs, 1):
        dt = fmt_dt(datetime.fromisoformat(expires)) if expires else "∞"
        text.append(f"{i}. {identifier} — до {dt}")
    await update.message.reply_text("\n".join(text))


async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not user or not msg:
        return

    subs = await db_query(
        "SELECT channel_identifier, expires_at FROM required_subs WHERE chat_id=?",
        (chat.id,),
        True,
    )
    if not subs:
        return

    not_subscribed = []
    for identifier, expires in subs:
        if expires and datetime.fromisoformat(expires) < datetime.now(timezone.utc):
            await db_query("DELETE FROM required_subs WHERE channel_identifier=?", (identifier,))
            continue

        try:
            member = await context.bot.get_chat_member(identifier, user.id)
            if member.status in ("left", "kicked"):
                not_subscribed.append(identifier)
        except Exception:
            not_subscribed.append(identifier)

    if not not_subscribed:
        try:
            await context.bot.restrict_chat_member(
                chat.id, user.id, permissions=ChatPermissions(can_send_messages=True)
            )
        except Exception:
            pass
        return

    try:
        await msg.delete()
    except Exception:
        pass

    try:
        await context.bot.restrict_chat_member(
            chat.id, user.id, permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception:
        pass

    for channel in not_subscribed:
        link = f"https://t.me/{channel.strip('@')}"
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔗 Подписаться", url=link)]]
        )
        await context.bot.send_message(
            chat.id,
            f"{user.mention_html()}, чтобы писать в чат, необходимо подписаться на:\n{channel}",
            reply_markup=keyboard,
            parse_mode="HTML",
        )


async def chat_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"my_chat_member update: {update.to_dict()}")


# -----------------------------
# Запуск polling
# -----------------------------
async def main():
    await init_db()

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(CommandHandler("setup", setup_handler))
    app.add_handler(CommandHandler("unsetup", unsetup_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_message))
    app.add_handler(ChatMemberHandler(chat_member_handler, chat_member_types=ChatMemberHandler.MY_CHAT_MEMBER))

    logger.info("🚀 Бот запущен через polling")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
