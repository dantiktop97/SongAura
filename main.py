import os
import json
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("Song")  # Твой токен
ADMIN_ID = 6525179440       # Только для тебя

# ===================== Загрузка цитат =====================
with open("quotes.json", encoding="utf-8") as f:
    quotes = json.load(f)

used_quotes = set()

# ===================== История пользователей =====================
USERS_FILE = "users.json"
if os.path.exists(USERS_FILE):
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        users = json.load(f)
else:
    users = []

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
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]])

def quote_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Ещё одна цитата", callback_data="random_quote")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAuraBot!\n"
        "💡 Используй кнопки ниже для навигации.\n"
    )

# ===================== Выдача цитат =====================
def get_random_quote():
    global used_quotes
    available = list(set(quotes) - used_quotes)
    if not available:
        used_quotes.clear()
        available = quotes.copy()
    quote = random.choice(available)
    used_quotes.add(quote)
    return quote

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    user_id = update.effective_user.id
    username = update.effective_user.username or str(user_id)

    # Сохраняем пользователя
    if username not in users:
        users.append(username)
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

# ===================== Обработка кнопок =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"
    user_id = query.from_user.id

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(f"💬 {quote}", reply_markup=quote_menu())

    elif query.data == "humor":
        joke = "😂 Почему программисты любят темную тему? Потому что светлая — для слабаков!"
        await query.edit_message_text(joke, reply_markup=back_menu())

    elif query.data == "about":
        text = "ℹ️ Этот бот присылает случайные цитаты и юмор.\n🎉 Наслаждайся!"
        await query.edit_message_text(text, reply_markup=back_menu())

    elif query.data == "admin" and user_id == ADMIN_ID:
        last_users = "\n".join(users[-10:])
        text = f"📊 Последние 10 уникальных пользователей:\n{last_users}"
        await query.edit_message_text(text, reply_markup=back_menu())

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
