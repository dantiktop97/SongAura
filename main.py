import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("Song")  # Секрет Render

# ===================== ЦИТАТЫ И ЮМОР =====================
quotes = [f"Цитата #{i}: Пример цитаты {i}" for i in range(1, 100001)]
jokes = [f"Шутка #{i}: Пример шутки {i}" for i in range(1, 10001)]

used_quotes = set()
used_jokes = set()
last_users = []  # Для админ меню (только уникальные)

ADMIN_ID = 6525179440  # ID @danyadz

# ===================== КЛАВИАТУРЫ =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random_quote")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]])

def quote_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Ещё одна цитата", callback_data="random_quote")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

def joke_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Ещё одна шутка", callback_data="humor")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Последние пользователи", callback_data="last_users")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

# ===================== ПРИВЕТСТВИЕ =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAuraBot — цитаты и юмор без повторов!\n\n"
        "💡 Используй кнопки ниже для навигации.\n"
        "- /start — главное меню\n"
        "- Случайная цитата или шутка"
    )

# ===================== ФУНКЦИИ ЦИТАТ/ЮМОР =====================
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

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_name = user.first_name or "друг"
    if user.username and user.username not in last_users:
        last_users.append(user.username)
    # Добавляем админ кнопку, если пользователь админ
    keyboard = main_menu().inline_keyboard
    if user.id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(full_greeting(user_name), reply_markup=markup)

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    user_name = user.first_name or "друг"

    # ==================== ЦИТАТА ====================
    if query.data == "random_quote":
        text = f"💬 {get_random_quote()}"
        markup = quote_menu()
        if query.message.text != text:  # Предотвращаем ошибку "Message is not modified"
            await query.edit_message_text(text=text, reply_markup=markup)

    # ==================== ЮМОР ====================
    elif query.data == "humor":
        text = f"😂 {get_random_joke()}"
        markup = joke_menu()
        if query.message.text != text:
            await query.edit_message_text(text=text, reply_markup=markup)

    # ==================== О БОТЕ ====================
    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Этот бот присылает цитаты и юмор.\n"
            "🎉 Цитаты и шутки не повторяются до полного исчерпания.\n"
            "💡 Наслаждайся и делись с друзьями!"
        )
        if query.message.text != text:
            await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())

    # ==================== ВЕРНУТЬСЯ НАЗАД ====================
    elif query.data == "back":
        # Добавляем админ кнопку, если пользователь админ
        keyboard = main_menu().inline_keyboard
        if user.id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
        markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(full_greeting(user_name), reply_markup=markup)

    # ==================== МЕНЮ АДМИНА ====================
    elif query.data == "admin":
        if user.id != ADMIN_ID:
            return  # Никто кроме админа не видит
        await query.edit_message_text("🛠 Меню админа", reply_markup=admin_menu())

    elif query.data == "last_users":
        if user.id != ADMIN_ID:
            return
        if last_users:
            text = "📊 Последние уникальные пользователи:\n" + "\n".join(last_users[-10:])
        else:
            text = "Нет данных о пользователях."
        await query.edit_message_text(text=text, reply_markup=admin_menu())

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
