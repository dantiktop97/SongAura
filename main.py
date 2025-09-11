import os
import requests
from bs4 import BeautifulSoup
from yt_dlp import YoutubeDL
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Ваш секрет Render
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

# ===================== Поиск RuTube =====================
def search_rutube(query: str) -> str:
    """Ищем видео на RuTube и возвращаем ссылку на первое видео"""
    search_url = f"https://rutube.ru/search/video/{query.replace(' ', '%20')}/"
    resp = requests.get(search_url)
    if resp.status_code != 200:
        raise Exception("Ошибка поиска на RuTube")
    
    soup = BeautifulSoup(resp.text, "html.parser")
    video_tag = soup.find("a", class_="search-video__title")
    if not video_tag:
        raise Exception("Видео не найдено")
    
    video_url = "https://rutube.ru" + video_tag.get("href")
    return video_url

def download_rutube_audio(query: str):
    """Скачиваем аудио с RuTube через yt-dlp"""
    url = search_rutube(query)
    with YoutubeDL(YDL_OPTS) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
        return info, filename

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name))

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Используй: /search Название песни 🎵")
        return
    
    query_text = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Ищу песню: {query_text}...")

    try:
        info, file_name = await asyncio.to_thread(download_rutube_audio, query_text)
        await update.message.reply_audio(
            open(file_name, "rb"),
            title=info.get('title', query_text),
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

    # Запуск через webhook
    WEBHOOK_URL = f"https://songaura.onrender.com/{TOKEN}"
    print("Бот запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
