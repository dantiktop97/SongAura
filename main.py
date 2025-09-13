import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================== КОНФИГ =====================
TOKEN = os.getenv("Song")  # Токен бота
ADMIN_ID = 6525179440       # Твой Telegram ID (Danya)

# ===================== ЦИТАТЫ =====================
# Генерируем "бесконечные" цитаты для примера
def generate_quote(n: int) -> str:
    return f"💬 Цитата #{n} — Это пример бесконечной цитаты {n}"

# ===================== ХРАНЕНИЕ =====================
used_quotes = set()
quote_counter = 1
unique_users = set()
last_users = []

# ===================== КЛАВИАТУРЫ =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random_quote")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
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

def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Статистика пользователей", callback_data="stats")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

# ===================== ПРИВЕТСТВИЕ =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAura — твой бот с цитатами и юмором!\n\n"
        "💡 Используй кнопки ниже:\n"
        "- Случайная цитата\n"
        "- Юмор\n"
        "- О боте\n\n"
        "🎉 Наслаждайся!"
    )

# ===================== ФУНКЦИИ =====================
def get_random_quote():
    global quote_counter
    quote = generate_quote(quote_counter)
    quote_counter += 1
    return quote

def add_user(user):
    global unique_users, last_users
    if user.id not in unique_users:
        unique_users.add(user.id)
        last_users.append(f"@{user.username}" if user.username else user.first_name)
        if len(last_users) > 10:  # храним только последних 10 пользователей
            last_users.pop(0)

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)
    await update.message.reply_text(
        full_greeting(user.first_name or "друг"),
        reply_markup=main_menu()
    )

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    add_user(user)
    user_name = user.first_name or "друг"

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(text=quote, reply_markup=quote_menu())

    elif query.data == "humor":
        joke = "😂 Почему программисты любят темную тему? Потому что светлая — для слабаков!"
        await query.edit_message_text(text=joke, reply_markup=back_menu())

    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Этот бот присылает случайные цитаты и юмор.\n"
            "💡 Цитаты бесконечны и не повторяются сразу.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())

    elif query.data == "back":
        # Добавляем кнопку админа, если это твой ID
        if user.id == ADMIN_ID:
            keyboard = main_menu().inline_keyboard + [[InlineKeyboardButton("🛠 Меню админа", callback_data="admin")]]
            await query.edit_message_text(full_greeting(user_name), reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(full_greeting(user_name), reply_markup=main_menu())

    elif query.data == "admin":
        if user.id == ADMIN_ID:
            await query.edit_message_text("🛠 Меню администратора", reply_markup=admin_menu())
        else:
            await query.edit_message_text("❌ У вас нет доступа к админ-меню.", reply_markup=back_menu())

    elif query.data == "stats":
        if user.id == ADMIN_ID:
            users_text = "\n".join(last_users[-10:]) if last_users else "Нет пользователей"
            await query.edit_message_text(f"📊 Последние уникальные пользователи:\n{users_text}", reply_markup=admin_menu())
        else:
            await query.edit_message_text("❌ У вас нет доступа к статистике.", reply_markup=back_menu())

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
