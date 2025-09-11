import os
import requests
from yt_dlp import YoutubeDL
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import asyncio

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Секрет Render
YDL_OPTS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'outtmpl': 'song.%(ext)s',
    'quiet': True,
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192'
    }],
}

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "🎶 Добро пожаловать в SongAura — твой музыкальный помощник!\n"
        "🚀 Я быстро нахожу песни на RuTube и присылаю их прямо сюда.\n\n"
        "📌 Команды:\n"
        "- /start — открыть приветствие\n"
        "- /search текст — найти песню\n\n"
        "🎵 Наслаждайся музыкой!"
    )

# ===================== Меню =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎵 Как искать песни", callback_data="search_help")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    keyboard = [[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]]
    return InlineKeyboardMarkup(keyboard)

# ===================== Поиск RuTube =====================
def search_rutube(query: str) -> str:
    """Ищем видео на RuTube и возвращаем ссылку на первое видео"""
    search_url = f"https://rutube.ru/api/v3/search/video/?query={query.replace(' ', '%20')}&count=1"
    resp = requests.get(search_url)
    if resp.status_code != 200:
        raise Exception("Ошибка поиска на RuTube")
    data = resp.json()
    if not data.get("results"):
        raise Exception("Видео не найдено")
    video_id = data["results"][0]["id"]
    return f"https://rutube.ru/video/{video_id}/"

def download_rutube_audio(query: str):
    """Скачиваем аудио с RuTube через yt-dlp"""
    url = search_rutube(query)
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return info, filename

# ===================== Прогресс =====================
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

# ===================== Команды =====================
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
        info, file_name = await asyncio.to_thread(download_rutube_audio, query_text)
        done_event.set()
        await progress
        await update.message.reply_audio(
            open(file_name, "rb"),
            title=info.get('title', query_text),
            caption="🎶 SongAura"
        )
        os.remove(file_name)
    except Exception as e:
        done_event.set()
        await progress
        await msg.edit_text(f"❌ Ошибка при получении аудио: {e}")

# ===================== Обработчик кнопок =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"

    if query.data == "search_help":
        await query.edit_message_text(
            "🎵 Чтобы найти песню, используй команду:\n\n"
            "`/search название_песни`\n\n"
            "Пример: `/search Время и Стекло — Навсегда`\n"
            "💡 Совет: добавление исполнителя ускоряет поиск.",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )
    elif query.data == "about":
        await query.edit_message_text(
            "ℹ️ *О SongAura*\n\n"
            "🎶 SongAura — музыкальный помощник в Telegram!\n"
            "🚀 Быстро ищет песни на RuTube и присылает их сюда.\n"
            "Автор: @SongAuraBot",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )
    elif query.data == "back":
        await query.edit_message_text(full_greeting(user_name), reply_markup=main_menu())

# ===================== MAIN =====================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    WEBHOOK_URL = f"https://songaura.onrender.com/{TOKEN}"
    print("Бот SongAura запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
