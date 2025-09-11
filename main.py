import os
import asyncio
from yt_dlp import YoutubeDL
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Токен Telegram бота
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
        "🚀 Я быстро нахожу песни на ВКонтакте и присылаю их прямо сюда.\n\n"
        "📌 Команды:\n"
        "- /start — открыть приветствие\n"
        "- /search <название песни> — найти песню\n\n"
        "🎵 Наслаждайся музыкой!"
    )

# ===================== Загрузка с VK =====================
def download_vk_audio(query: str):
    """Ищем песню в VK через yt-dlp и скачиваем аудио"""
    search_url = f"vksearch:{query}"  # yt-dlp поддерживает VK search
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(search_url, download=True)
        entry = info['entries'][0]  # Берём первый результат
        filename = ydl.prepare_filename(entry).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return entry, filename

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name))

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /search <название песни> 🎵")
        return

    query_text = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу песню: {query_text}...")

    try:
        # Скачиваем песню в отдельном потоке
        entry, file_name = await asyncio.to_thread(download_vk_audio, query_text)
        await update.message.reply_audio(
            open(file_name, "rb"),
            title=entry.get('title', query_text),
            caption="🎶 SongAura"
        )
        os.remove(file_name)
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Ошибка: {e}")

# ===================== MAIN =====================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("search", search_command))

    WEBHOOK_URL = f"https://songaura.onrender.com/{TOKEN}"  # Ваш URL на Render
    print("Бот запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
