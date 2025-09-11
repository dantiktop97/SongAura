import os
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Токен бота
VK_SERVICE_KEY = os.getenv("VK_KEY")  # Сервисный ключ VK
VK_API_VERSION = "5.131"

# ===================== Меню =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎵 Поиск песни", callback_data="search_help")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    keyboard = [[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]]
    return InlineKeyboardMarkup(keyboard)

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "🎶 Добро пожаловать в SongAura — твой музыкальный помощник!\n"
        "🚀 Быстро ищет песни в VK и присылает их прямо сюда.\n\n"
        "📌 Команды:\n"
        "- /start — главное меню\n"
        "- /search текст — найти песню по названию\n\n"
        "🎵 Наслаждайся музыкой!"
    )

# ===================== Прогресс =====================
def build_bar(steps: int) -> str:
    return f"{'✅'*steps}{'⬜'*(10-steps)} {steps*10}%"

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

# ===================== Поиск VK =====================
def search_vk_audio(query: str):
    url = "https://api.vk.com/method/audio.search"
    params = {
        "q": query,
        "count": 1,
        "access_token": VK_SERVICE_KEY,
        "v": VK_API_VERSION
    }
    resp = requests.get(url, params=params).json()
    if "error" in resp:
        raise Exception(resp["error"]["error_msg"])
    items = resp.get("response", {}).get("items", [])
    if not items:
        raise Exception("Песня не найдена")
    track = items[0]
    return {
        "title": track.get("artist", "") + " - " + track.get("title", ""),
        "url": track.get("url")
    }

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
        track = await asyncio.to_thread(search_vk_audio, query_text)
        done_event.set()
        await progress

        audio_resp = requests.get(track["url"])
        file_name = "song.mp3"
        with open(file_name, "wb") as f:
            f.write(audio_resp.content)

        await update.message.reply_audio(
            open(file_name, "rb"),
            title=track["title"],
            caption="🎶 SongAura"
        )
        os.remove(file_name)
        await msg.delete()
    except Exception as e:
        done_event.set()
        if not progress.done():
            await progress
        await msg.edit_text(f"❌ Ошибка: {e}")

# ===================== Кнопки =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"

    if query.data == "search_help":
        await query.edit_message_text(
            "🎵 Чтобы найти песню, используй команду:\n\n"
            "`/search название_песни`\n\n"
            "Пример: `/search Ты похож на кота`\n\n"
            "💡 Добавление исполнителя ускоряет поиск.",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )
    elif query.data == "about":
        await query.edit_message_text(
            "ℹ️ *О SongAura*\n\n"
            "🎶 SongAura — твой музыкальный помощник!\n"
            "🚀 Быстро ищет песни в VK.\n\n"
            "📌 Основные команды:\n"
            "- /start — главное меню\n"
            "- /search текст — найти песню\n\n"
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
