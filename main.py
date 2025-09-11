import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================== Конфигурация =====================
TOKEN = os.getenv("QuotesAuraBot")  # Секрет Render

# Пример категорий цитат
QUOTE_CATEGORIES = {
    "random": [
        "Цитата 1",
        "Цитата 2",
        "Цитата 3"
    ],
    "humor": [
        "Юмор 1",
        "Юмор 2",
        "Юмор 3"
    ]
}

# Очереди пользователей для уникальных цитат
user_queues = {}  # user_id -> category -> list
user_history = {}  # user_id -> list of last shown quotes

# ===================== Кнопки =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    keyboard = [[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]]
    return InlineKeyboardMarkup(keyboard)

def quote_menu(category):
    keyboard = [
        [InlineKeyboardButton("🔁 Ещё одна цитата", callback_data=f"quote_{category}")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAuraBot — твой помощник по цитатам!\n\n"
        "💡 Используй кнопки ниже, чтобы получать цитаты и юмор.\n"
        "📌 Команды:\n"
        "- /start — главное меню\n\n"
        "🎉 Приятного настроения!"
    )

# ===================== Логика получения уникальной цитаты =====================
def get_unique_quote(user_id, category):
    if user_id not in user_queues:
        user_queues[user_id] = {}
    if category not in user_queues[user_id] or not user_queues[user_id][category]:
        # создаём новую очередь и перемешиваем
        user_queues[user_id][category] = QUOTE_CATEGORIES[category].copy()
        random.shuffle(user_queues[user_id][category])
    quote = user_queues[user_id][category].pop(0)
    return quote

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

# ===================== Обработчик кнопок =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"

    if query.data == "back":
        await query.edit_message_text(full_greeting(user_name), reply_markup=main_menu())
    elif query.data in QUOTE_CATEGORIES:
        quote = get_unique_quote(query.from_user.id, query.data)
        await query.edit_message_text(quote, reply_markup=quote_menu(query.data))
    elif query.data.startswith("quote_"):
        category = query.data.split("_", 1)[1]
        quote = get_unique_quote(query.from_user.id, category)
        await query.edit_message_text(quote, reply_markup=quote_menu(category))

# ===================== MAIN =====================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    WEBHOOK_URL = f"https://yourdomain.com/{TOKEN}"  # Заменить на ваш URL Render
    print("QuotesAuraBot запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
