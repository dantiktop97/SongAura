import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Ваш секрет Render
ADMIN_ID = 6525179440  # Ваш ID
MAX_DISPLAY_USERS = 10

# ===================== ЦИТАТЫ И ЮМОР =====================
# Для примера генерируем 100.000 шаблонных цитат и шуток
quotes = [f"Цитата #{i+1}" for i in range(100000)]
jokes = [f"Юмор #{i+1}" for i in range(100000)]

used_quotes = set()
used_jokes = set()
unique_users = []  # Список уникальных пользователей

# ===================== КЛАВИАТУРЫ =====================
def main_menu(admin=False):
    buttons = [
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random_quote")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    if admin:
        buttons.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    return InlineKeyboardMarkup(buttons)

def back_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

def quote_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Ещё одна цитата", callback_data="random_quote")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

def joke_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Ещё один юмор", callback_data="humor")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

# ===================== ПРИВЕТСТВИЕ =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAura — твой бот с цитатами и юмором!\n\n"
        "💡 Используй кнопки ниже или команды:\n"
        "- /start — открыть главное меню\n"
        "- Выбери случайную цитату или юмор\n\n"
        "🎉 Наслаждайся!"
    )

# ===================== БЕЗ ПОВТОРОВ =====================
def get_random_quote():
    global used_quotes
    available = list(set(quotes) - used_quotes)
    if not available:
        used_quotes.clear()
        available = list(quotes)
    quote = random.choice(available)
    used_quotes.add(quote)
    return quote

def get_random_joke():
    global used_jokes
    available = list(set(jokes) - used_jokes)
    if not available:
        used_jokes.clear()
        available = list(jokes)
    joke = random.choice(available)
    used_jokes.add(joke)
    return joke

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = user.first_name or "друг"
    
    # Уникальные пользователи
    if user.username and user.username not in unique_users:
        unique_users.append(user.username)
    
    is_admin = user.id == ADMIN_ID
    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu(admin=is_admin))

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_name = user.first_name or "друг"
    is_admin = user.id == ADMIN_ID

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(text=f"💬 {quote}", reply_markup=quote_menu())

    elif query.data == "humor":
        joke = get_random_joke()
        await query.edit_message_text(text=f"😂 {joke}", reply_markup=joke_menu())

    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Бот присылает случайные цитаты и юмор.\n"
            "💡 Цитаты и шутки не повторяются до исчерпания всех.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())

    elif query.data == "admin" and is_admin:
        # Кнопка для статистики уникальных пользователей
        last_users = unique_users[-MAX_DISPLAY_USERS:]
        stats_text = "📊 Последние уникальные пользователи:\n" + "\n".join(f"@{u}" for u in reversed(last_users))
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
        ])
        await query.edit_message_text(text=stats_text, reply_markup=keyboard)

    elif query.data == "back":
        await query.edit_message_text(full_greeting(user_name), reply_markup=main_menu(admin=is_admin))

# ===================== MAIN =====================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    WEBHOOK_URL = f"https://songaura.onrender.com/{TOKEN}"
    print("QuotesAuraBot запущен через webhook...")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,
        webhook_url=WEBHOOK_URL
    )
