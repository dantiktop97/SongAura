import os
import asyncio
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("Song")  # Используем секрет из Render

# ===================== YT-DLP =====================
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'outtmpl': 'song.%(ext)s',
    'quiet': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
}

def download_from_rutube(url: str):
    """
    Загружает аудио с RuTube по прямой ссылке на видео.
    """
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return info, filename

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

# ===================== МЕНЮ =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎵 Инструкция по поиску", callback_data="search_help")],
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
        "🚀 Я могу загружать аудио с RuTube по ссылке.\n\n"
        "📌 Основные команды:\n"
        "- /start — открыть главное меню\n"
        "- /search <ссылка_на_RuTube> — получить аудио\n\n"
        "🎵 Используй кнопки ниже для удобного управления.\n"
        "🎉 Приятного прослушивания!\n"
        "Автор: @SongAuraBot"
    )

# ===================== БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ =====================
async def safe_edit_message(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        pass

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /search <ссылка на RuTube> 🎵")
        return

    url = context.args[0]
    msg = await update.message.reply_text(f"🔍 Загружаю аудио с RuTube...\n{build_bar(0)}")
    done_event = asyncio.Event()
    progress = asyncio.create_task(progress_task(msg, url, done_event))

    try:
        info, file_name = await asyncio.to_thread(download_from_rutube, url)
        done_event.set()
        await progress

        await update.message.reply_audio(
            open(file_name, "rb"),
            title=info.get('title', 'Аудио с RuTube'),
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
    user_name = query.from_user.first_name or "друг"

    if query.data == "search_help":
        await safe_edit_message(
            query,
            "🎵 Чтобы получить аудио, отправь команду:\n\n"
            "`/search ссылка_на_RuTube`\n\n"
            "Пример: `/search https://rutube.ru/video/xxxxxx`\n\n"
            "💡 Видео должно быть открытое!",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    elif query.data == "about":
        await safe_edit_message(
            query,
            "ℹ️ *О SongAura*\n\n"
            "🎶 SongAura — это твой музыкальный помощник в Telegram!\n"
            "🚀 Загружает аудио с RuTube без необходимости авторизации.\n\n"
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

# ===================== MAIN =====================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    # ===================== WEBHOOK =====================
    WEBHOOK_URL = "https://songaura.onrender.com/" + TOKEN  # Твой URL Render + токен

    print("Бот SongAura запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
