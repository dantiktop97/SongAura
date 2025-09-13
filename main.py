import os
import random
from collections import deque
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Твой токен
ADMIN_ID = 6525179440  # Твой ID
MAX_HISTORY = 10  # Сколько последних пользователей хранить

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

used_quotes = set()
user_history = deque(maxlen=MAX_HISTORY)  # Хранит последних 10 пользователей

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
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
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

# ===================== ВЫДАЧА ЦИТАТ =====================
def get_random_quote() -> str:
    global used_quotes
    available = list(set(quotes) - used_quotes)
    if not available:  # если все цитаты использованы, очищаем
        used_quotes.clear()
        available = list(quotes)
    quote = random.choice(available)
    used_quotes.add(quote)
    return quote

# ===================== КОМАНДЫ =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    user_history.appendleft(f"@{update.effective_user.username or update.effective_user.first_name}")
    
    # Создаем меню, добавляем админ-кнопку только тебе
    if update.effective_user.id == ADMIN_ID:
        keyboard_buttons = list(main_menu().inline_keyboard)
        keyboard_buttons.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
        reply_markup = InlineKeyboardMarkup(keyboard_buttons)
    else:
        reply_markup = main_menu()
    
    await update.message.reply_text(full_greeting(user_name), reply_markup=reply_markup)

# ===================== ОБРАБОТЧИК КНОПОК =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"
    
    # Запись пользователя в историю
    user_history.appendleft(f"@{query.from_user.username or query.from_user.first_name}")

    if query.data == "random_quote":
        quote = get_random_quote()
        await query.edit_message_text(
            text=f"💬 {quote}",
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
            "Этот бот присылает случайные цитаты и юмор.\n"
            "💡 Цитаты не повторяются до тех пор, пока не будут использованы все.\n"
            "🎉 Приятного пользования!"
        )
        await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=back_menu())

    elif query.data == "admin" and query.from_user.id == ADMIN_ID:
        await query.edit_message_text(
            text="🛠 Меню админа",
            reply_markup=admin_menu()
        )

    elif query.data == "stats" and query.from_user.id == ADMIN_ID:
        stats_text = "📊 Последние пользователи:\n" + "\n".join(list(user_history)[:MAX_HISTORY])
        await query.edit_message_text(text=stats_text, reply_markup=admin_menu())

    elif query.data == "back":
        # Возвращаемся в главное меню с кнопкой админа если ты
        if query.from_user.id == ADMIN_ID:
            keyboard_buttons = list(main_menu().inline_keyboard)
            keyboard_buttons.append([InlineKeyboardButton("🛠 Меню админа", callback_data="admin")])
            reply_markup = InlineKeyboardMarkup(keyboard_buttons)
        else:
            reply_markup = main_menu()
        await query.edit_message_text(full_greeting(user_name), reply_markup=reply_markup)

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
