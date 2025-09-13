import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("Song")  # Твой токен Telegram бота
ADMIN_ID = 6525179440      # ID администратора (твой)

# ===================== Файлы с данными =====================
QUOTES_FILE = "quotes.json"
JOKES_FILE = "jokes.json"
USERS_FILE = "users.json"

# ===================== Загрузка данных =====================
def load_json(filename, default):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

quotes = load_json(QUOTES_FILE, ["Жизнь — это то, что с тобой происходит, пока ты строишь планы."])
jokes = load_json(JOKES_FILE, ["😂 Почему программисты любят темную тему? Потому что светлая — для слабаков!"])
unique_users = load_json(USERS_FILE, [])

used_quotes = set()
used_jokes = set()

# ===================== Клавиатуры =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random_quote")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    if ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("😂 Ещё один юмор", callback_data="humor")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAura — твой бот с цитатами и юмором!\n\n"
        "💡 Используй кнопки ниже или команды:\n"
        "- /start — открыть главное меню\n"
        "- Выбери случайную цитату или юмор\n\n"
        "🎉 Наслаждайся!"
    )

# ===================== Пользователи =====================
def add_user(user):
    if user.username and user.username not in unique_users:
        unique_users.append(user.username)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(unique_users, f, ensure_ascii=False)

# ===================== Получение цитаты/шутки =====================
def get_random_quote():
    global used_quotes
    available = list(set(quotes) - used_quotes)
    if not available:
        used_quotes.clear()
        available = quotes.copy()
    quote = random.choice(available)
    used_quotes.add(quote)
    return quote

def get_random_joke():
    global used_jokes
    available = list(set(jokes) - used_jokes)
    if not available:
        used_jokes.clear()
        available = jokes.copy()
    joke = random.choice(available)
    used_jokes.add(joke)
    return joke

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    user_name = user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

# ===================== Обработка кнопок =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    add_user(user)
    user_name = user.first_name or "друг"

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(text=f"💬 {quote}", reply_markup=quote_menu())

    elif query.data == "humor":
        joke = get_random_joke()
        await query.edit_message_text(text=joke, reply_markup=joke_menu())

    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Этот бот присылает случайные цитаты и юмор.\n"
            "💡 Цитаты не повторяются до тех пор, пока не будут использованы все.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())

    elif query.data == "admin":
        if user.id != ADMIN_ID:
            await query.edit_message_text("❌ Доступ запрещён", reply_markup=back_menu())
            return
        # Показ последних 10 уникальных пользователей
        last_users = unique_users[-10:] if unique_users else ["Никто ещё не заходил"]
        text = "📊 Последние уникальные пользователи:\n" + "\n".join(f"@{u}" for u in last_users)
        await query.edit_message_text(text=text, reply_markup=back_menu())

    elif query.data == "back":
        await query.edit_message_text(full_greeting(user_name), reply_markup=main_menu())

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
