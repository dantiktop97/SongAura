import os
import asyncio
import threading
import http.server
import socketserver
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("Song")  # переменная окружения с токеном

# ===================== YT-DLP =====================
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'outtmpl': 'song.%(ext)s',
    'quiet': True,
    'cookiefile': 'cookies.txt',
    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
}

# ===================== ПРОГРЕСС =====================
def build_bar(steps: int) -> str:
    return f"{'✅' * steps}{'⬜' * (10 - steps)} {steps*10}%"

async def progress_task(msg, query: str, done_event: asyncio.Event, step_delay: float = 0.5):
    last_text = ""
    for step in range(1, 11):
        if done_event.is_set():
            final_text = f"🔍 Ищу песню: {query}\n{build_bar(10)} ✅"
            if final_text != last_text:
                await msg.edit_text(final_text)
            return
        current_text = f"🔍 Ищу песню: {query}\n{build_bar(step)}"
        if current_text != last_text:
            await msg.edit_text(current_text)
            last_text = current_text
        await asyncio.sleep(step_delay)
    if not done_event.is_set():
        final_text = f"🔍 Ищу песню: {query}\n{build_bar(10)} ✅"
        if final_text != last_text:
            await msg.edit_text(final_text)

def download_with_ytdlp(query: str):
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=True)
        entry = info['entries'][0]
        filename = ydl.prepare_filename(entry).replace(".webm", ".mp3").replace(".m4a", ".mp3")
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

# ===================== ПРИВЕТСТВИЕ =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "🎶 Добро пожаловать в SongAura — твой музыкальный помощник в Telegram!\n"
        "🚀 Я быстро нахожу песни на YouTube и присылаю их прямо сюда.\n\n"
        "📌 Основные команды:\n"
        "- /start — открыть главное меню\n"
        "- /search текст — найти песню по названию\n\n"
        "💡 Совет: точное название песни или добавление исполнителя ускоряет поиск.\n"
        "🎵 Используй кнопки ниже для удобного управления.\n\n"
        "🎉 Приятного прослушивания!\n"
        "Автор: @SongAuraBot"
    )

# ===================== БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ =====================
async def safe_edit_message(query, text, reply_markup=None, parse_mode=None):
    if query.message.text == text and query.message.reply_markup == reply_markup:
        return
    await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /search Название песни 🎵")
        return

    query_text = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу песню: {query_text}\n{build_bar(0)}")

    done_event = asyncio.Event()
    progress = asyncio.create_task(progress_task(msg, query_text, done_event))

    try:
        entry, file_name = await asyncio.to_thread(download_with_ytdlp, query_text)
        done_event.set()
        await progress

        await update.message.reply_audio(
            open(file_name, "rb"),
            title=entry.get('title', query_text),
            caption="🎶 Сделано с помощью @SongAuraBot"
        )
        os.remove(file_name)

    except Exception as e:
        done_event.set()
        if not progress.done():
            await progress
        await msg.edit_text(f"❌ Ошибка при получении аудио: {e}")

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"

    if query.data == "search_help":
        await safe_edit_message(
            query,
            "🎵 Чтобы найти песню, используй команду:\n\n"
            "`/search название_песни`\n\n"
            "Пример: `/search ты похож на кота`\n\n"
            "💡 Совет: добавление исполнителя ускоряет поиск.\n"
            "🎶 Попробуй прямо сейчас!",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    elif query.data == "about":
        await safe_edit_message(
            query,
            "ℹ️ *О SongAura*\n\n"
            "🎶 SongAura — твой музыкальный помощник в Telegram!\n"
            "🚀 Быстро ищет песни на YouTube и присылает их прямо сюда.\n\n"
            "📌 Основные команды:\n"
            "- /start — открыть главное меню\n"
            "- /search текст — найти песню\n\n"
            "💡 Совет: точное название песни ускоряет поиск.\n"
            "🎵 Используй кнопки ниже для удобного управления.\n\n"
            "Автор: @SongAuraBot\n"
            "🎉 Приятного прослушивания!",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    elif query.data == "back":
        await safe_edit_message(
            query,
            full_greeting(user_name),
            reply_markup=main_menu()
        )

# ===================== DUMMY SERVER ДЛЯ RENDER =====================
def run_dummy_server():
    port = int(os.getenv("PORT", 10000))
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        httpd.serve_forever()

# ===================== MAIN =====================
if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Бот SongAura запущен...")
    app.run_polling()
