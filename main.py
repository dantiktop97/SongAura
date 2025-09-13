import os
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = os.getenv("Song")  # Токен бота
ADMIN_ID = 6525179440       # Твой Telegram ID

# ===================== ДАННЫЕ =====================
quotes = [f"💬 Цитата #{i+1} — Это пример бесконечной цитаты {i+1}" for i in range(100000)]
jokes = [
    "😂 Почему программисты любят темную тему? Потому что светлая — для слабаков!",
    "😂 Жизнь — как код: иногда работает, иногда баги.",
    "😂 Учёные доказали: смех продлевает жизнь, особенно над багами."
]

used_quotes = set()
used_jokes = set()
user_history = []

# ===================== КЛАВИАТУРЫ =====================
def main_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random_quote")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    # Добавляем админ меню если это админ
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    return InlineKeyboardMarkup(keyboard)

def back_menu(user_id=None):
    keyboard = [[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]]
    # Админ кнопка
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    return InlineKeyboardMarkup(keyboard)

def quote_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("📌 Ещё одна цитата", callback_data="random_quote")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    return InlineKeyboardMarkup(keyboard)

def joke_menu(user_id=None):
    keyboard = [
        [InlineKeyboardButton("😂 Ещё один юмор", callback_data="humor")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ]
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    return InlineKeyboardMarkup(keyboard)

# ===================== ПРИВЕТСТВИЕ =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAuraBot — твой бот с цитатами и юмором!\n\n"
        "💡 Используй кнопки ниже или команды:\n"
        "- /start — открыть главное меню\n"
        "- Выбери случайную цитату или юмор\n\n"
        "🎉 Наслаждайся!"
    )

# ===================== ФУНКЦИИ =====================
def get_random_quote() -> str:
    global used_quotes
    available = list(set(quotes) - used_quotes)
    if not available:
        used_quotes.clear()
        available = list(quotes)
    quote = random.choice(available)
    used_quotes.add(quote)
    return quote

def get_random_joke() -> str:
    global used_jokes
    available = list(set(jokes) - used_jokes)
    if not available:
        used_jokes.clear()
        available = list(jokes)
    joke = random.choice(available)
    used_jokes.add(joke)
    return joke

def update_user_history(user):
    global user_history
    if user.username and user.username not in user_history:
        user_history.append(user.username)
        # Ограничим до последних 100 пользователей для хранения
        if len(user_history) > 100:
            user_history = user_history[-100:]

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_user_history(user)
    markup = main_menu(user.id)
    await update.message.reply_text(full_greeting(user.first_name or "друг"), reply_markup=markup)

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    update_user_history(user)
    await query.answer()
    
    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(
            text=quote,
            reply_markup=quote_menu(user.id)
        )
    elif query.data == "humor":
        joke = get_random_joke()
        await query.edit_message_text(
            text=joke,
            reply_markup=joke_menu(user.id)
        )
    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Этот бот присылает случайные цитаты и юмор.\n"
            "💡 Цитаты и юмор не повторяются, пока все не будут показаны.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu(user.id))
    elif query.data == "admin" and user.id == ADMIN_ID:
        stats = "\n".join(user_history[-10:]) if user_history else "Пока нет пользователей"
        await query.edit_message_text(
            text=f"🛠 *Меню админа*\n\n📊 Последние уникальные пользователи:\n{stats}",
            parse_mode="Markdown",
            reply_markup=back_menu(user.id)
        )
    elif query.data == "back":
        await query.edit_message_text(full_greeting(user.first_name or "друг"), reply_markup=main_menu(user.id))

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
