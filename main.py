import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

TOKEN = os.getenv("Song")  # Секрет Render для вашего бота
ADMIN_ID = 6525179440  # Твой Telegram ID

# ===================== ЦИТАТЫ =====================
quotes = [
    "Жизнь — это то, что с тобой происходит, пока ты строишь планы.",
    "Счастье — это путь, а не пункт назначения.",
    "Учиться никогда не поздно, а останавливаться — всегда рано.",
    "Смех — лучшее лекарство.",
    "Каждый день — новый шанс изменить свою жизнь.",
    "Не откладывай на завтра то, что можно сделать сегодня.",
    "Верь в себя, даже когда никто другой не верит.",
    "Ошибки — это шаги к успеху.",
    "Терпение и труд всё перетрут.",
    "Лучший способ предсказать будущее — создать его."
]

# Для статистики последних пользователей
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
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]])

def quote_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Ещё одна цитата", callback_data="random_quote")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ])

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("📊 Статистика последних пользователей", callback_data="stats")],
        [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
    ]
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

# ===================== ВЫДАЧА ЦИТАТ =====================
def get_random_quote() -> str:
    return random.choice(quotes)  # Бесконечно, цитаты могут повторяться

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"

    # Добавляем пользователя в статистику
    username = update.effective_user.username or update.effective_user.first_name
    last_users.append(username)
    if len(last_users) > 10:
        last_users.pop(0)

    # Приветствие
    if update.effective_user.id == ADMIN_ID:
        # Добавляем кнопку админ-меню только для тебя
        keyboard = main_menu().inline_keyboard + [[InlineKeyboardButton("🛠 Меню админа", callback_data="admin")]]
        await update.message.reply_text(full_greeting(user_name), reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"

    # Добавляем пользователя в статистику
    username = query.from_user.username or query.from_user.first_name
    last_users.append(username)
    if len(last_users) > 10:
        last_users.pop(0)

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(text=f"💬 {quote}", reply_markup=quote_menu())

    elif query.data == "humor":
        joke = "😂 Почему программисты любят темную тему? Потому что светлая — для слабаков!"
        await query.edit_message_text(text=joke, reply_markup=back_menu())

    elif query.data == "about":
        text = (
            "ℹ️ *О QuotesAuraBot*\n\n"
            "Этот бот присылает случайные цитаты и юмор.\n"
            "💡 Цитаты выдаются бесконечно.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())

    elif query.data == "back":
        if query.from_user.id == ADMIN_ID:
            keyboard = main_menu().inline_keyboard + [[InlineKeyboardButton("🛠 Меню админа", callback_data="admin")]]
            await query.edit_message_text(full_greeting(user_name), reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text(full_greeting(user_name), reply_markup=main_menu())

    elif query.data == "admin" and query.from_user.id == ADMIN_ID:
        await query.edit_message_text("🛠 Меню админа:", reply_markup=admin_menu())

    elif query.data == "stats" and query.from_user.id == ADMIN_ID:
        if last_users:
            text = "📊 Последние 10 пользователей, кто использовал бота:\n\n"
            text += "\n".join(f"- @{u}" for u in last_users)
        else:
            text = "📊 Пока никто не использовал бота."
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
