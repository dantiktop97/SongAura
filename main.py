import os
import asyncio
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    ContextTypes, CallbackQueryHandler
)

TOKEN = os.getenv("Song")  # Ваш токен в Render

# ===================== YT-DLP =====================
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'outtmpl': 'song.%(ext)s',
    'quiet': True,
    'postprocessors': [],
}

# ===================== ПРОГРЕСС =====================
def build_bar(steps: int) -> str:
    return f"{'🟩' * steps}{'⬛' * (10 - steps)} {steps*10}%"

async def progress_task(msg, query: str, done_event: asyncio.Event, step_delay: float = 0.6):
    for step in range(1, 11):
        if done_event.is_set():
            await msg.edit_text(f"🔍 Ищу песню: {query} | {build_bar(10)}")
            return
        await msg.edit_text(f"🔍 Ищу песню: {query} | {build_bar(step)}")
        await asyncio.sleep(step_delay)
    if not done_event.is_set():
        await msg.edit_text(f"🔍 Ищу песню: {query} | {build_bar(10)}")

def download_with_ytdlp(query: str):
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=True)
        entry = info['entries'][0]
        filename = ydl.prepare_filename(entry)
        return entry, filename

# ===================== МЕНЮ =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎵 Поиск песни", callback_data="search_help")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    keyboard = [[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]]
    return InlineKeyboardMarkup(keyboard)

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"👋 Привет, {user}!\n\n"
        "Добро пожаловать в SongAura 🎶\n"
        "Я помогу найти и скачать музыку прямо здесь.\n\n"
        "Выбери действие ниже:",
        reply_markup=main_menu()
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /search Название песни")
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу песню: {query} | {build_bar(0)}")

    done_event = asyncio.Event()
    progress = asyncio.create_task(progress_task(msg, query, done_event))

    try:
        entry, file_name = await asyncio.to_thread(download_with_ytdlp, query)
        done_event.set()
        await progress

        await update.message.reply_audio(
            open(file_name, "rb"),
            title=entry.get('title', query),
            caption="🎶 Сделано с помощью @SongAuraBot"
        )
        try:
            os.remove(file_name)
        except Exception:
            pass

    except Exception as e:
        done_event.set()
        if not progress.done():
            await progress
        await msg.edit_text(f"❌ Ошибка при получении аудио: {e}")

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "search_help":
        await query.edit_message_text(
            "🎵 Чтобы найти песню, используй команду:\n\n"
            "`/search название_песни`\n\n"
            "Пример: `/search ты похож на кота`",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    elif query.data == "about":
        await query.edit_message_text(
            "ℹ️ *О SongAura*\n\n"
            "🎶 Этот бот ищет музыку на YouTube и присылает аудио прямо сюда.\n\n"
            "📌 Команды:\n"
            "- `/start` — открыть меню\n"
            "- `/search текст` — найти песню\n\n"
            "🚀 Автор: @SongAuraBot",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    elif query.data == "back":
        # Возврат на главное меню
        await query.edit_message_text(
            "👋 Главное меню SongAura 🎶\nВыбери действие ниже:",
            reply_markup=main_menu()
        )

# ===================== MAIN =====================
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    print("Бот SongAura запущен...")
    app.run_polling()
