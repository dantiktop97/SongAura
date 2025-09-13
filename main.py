import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===================== Настройки =====================
TOKEN = os.getenv("Song")  # Твой токен бота
ADMIN_ID = 6525179440      # Твой Telegram ID

# ===================== Цитаты =====================
# Генерация бесконечных цитат с номером
quote_counter = 0

# ===================== Пользователи =====================
unique_users = []

# ===================== Клавиатуры =====================
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Случайная цитата", callback_data="random_quote")],
        [InlineKeyboardButton("😂 Юмор", callback_data="humor")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ])

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

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "Добро пожаловать в QuotesAura — бот с цитатами и юмором!\n\n"
        "💡 Используй кнопки ниже или команды:\n"
        "- /start — открыть главное меню\n"
        "- Выбери случайную цитату или юмор\n\n"
        "🎉 Наслаждайся!"
    )

# ===================== Функция выдачи цитаты =====================
def get_random_quote() -> str:
    global quote_counter
    quote_counter += 1
    return f"💬 Цитата #{quote_counter} — Это пример бесконечной цитаты {quote_counter}"

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    user_id = update.effective_user.id
    # Добавляем пользователя, если его ещё нет
    if user_id not in [u['id'] for u in unique_users]:
        unique_users.append({'id': user_id, 'username': update.effective_user.username or user_name})
    # Формируем главное меню
    keyboard = main_menu()
    if user_id == ADMIN_ID:
        keyboard.inline_keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
    await update.message.reply_text(full_greeting(user_name), reply_markup=keyboard)

# ===================== Обработчик кнопок =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_name = query.from_user.first_name or "друг"

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(
            text=quote,
            reply_markup=quote_menu()
        )
    elif query.data == "humor":
        joke = "😂 Почему программисты любят темную тему? Потому что светлая — для слабаков!"
        await query.edit_message_text(
            text=joke,
            reply_markup=back_menu()
        )
    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Бот присылает бесконечные цитаты и юмор.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())
    elif query.data == "back":
        keyboard = main_menu()
        if user_id == ADMIN_ID:
            keyboard.inline_keyboard.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
        await query.edit_message_text(full_greeting(user_name), reply_markup=keyboard)
    elif query.data == "admin" and user_id == ADMIN_ID:
        await query.edit_message_text("🛠 Меню админа", reply_markup=admin_menu())
    elif query.data == "stats" and user_id == ADMIN_ID:
        last_users = unique_users[-10:]
        text = "📊 Последние уникальные пользователи:\n"
        for u in last_users:
            text += f"@{u['username']}\n"
        await query.edit_message_text(text=text, reply_markup=admin_menu())
    else:
        await query.edit_message_text("❌ У тебя нет доступа к этой функции.", reply_markup=back_menu())

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
