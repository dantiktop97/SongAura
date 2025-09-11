import os
import requests
from yt_dlp import YoutubeDL
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Токен Telegram-бота
VK_TOKEN = os.getenv("VK_TOKEN")  # Access token VK

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
        "🚀 Я быстро нахожу песни через VK и присылаю их прямо сюда.\n\n"
        "📌 Команды:\n"
        "- /start — открыть приветствие\n"
        "- /search название песни — найти и скачать\n\n"
        "🎵 Наслаждайся музыкой!"
    )

# ===================== Поиск через VK API =====================
def search_vk_audio(query: str) -> str:
    """Ищем песню через VK API и возвращаем прямую ссылку на аудио"""
    url = "https://api.vk.com/method/audio.search"
    params = {
        "q": query,
        "count": 1,
        "access_token": VK_TOKEN,
        "v": "5.131"
    }
    resp = requests.get(url, params=params)
    data = resp.json()

    if "error" in data:
        raise Exception(f"VK API error: {data['error']['error_msg']}")

    items = data.get("response", {}).get("items", [])
    if not items:
        raise Exception("Аудио не найдено")

    audio_url = items[0].get("url")
    if not audio_url:
        raise Exception("Прямой URL аудио не найден")

    return audio_url

def download_audio(url: str):
    """Скачиваем аудио через yt-dlp по прямой ссылке"""
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
        audio_url = await asyncio.to_thread(search_vk_audio, query_text)
        info, file_name = await asyncio.to_thread(download_audio, audio_url)

        await update.message.reply_audio(
            open(file_name, "rb"),
            title=info.get("title", query_text),
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

    # Запуск через webhook (Render)
    WEBHOOK_URL = f"https://songaura.onrender.com/{TOKEN}"
    print("Бот запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
