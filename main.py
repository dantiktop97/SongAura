import os
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes
)

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Токен бота
BOT_NAME = "@QuotesAuraBot"

QUOTE_CATEGORIES = {
    "Мотивация": [
        "Не откладывай на завтра то, что можно сделать сегодня.",
        "Смелость — это сопротивление страху, а не отсутствие страха.",
        "Учись на ошибках других. Ты не сможешь прожить достаточно долго, чтобы сделать их все сам."
    ],
    "Жизнь": [
        "Жизнь — это то, что с тобой происходит, пока ты строишь планы. — Джон Леннон",
        "Счастье — это когда то, что ты думаешь, что ты говоришь, и что ты делаешь, совпадает. — Махатма Ганди"
    ],
    "Юмор": [
        "Жизнь слишком коротка, чтобы тратить её на плохие шутки.",
        "Если жизнь подбрасывает лимоны — делай лимонад и продай его с прибылью!"
    ]
}

# ===================== Хранение состояния =====================
user_queues = {}  # {user_id: {category: [цитаты для показа]}}
user_history = {} # {user_id: [последние 5 цитат]}

# ===================== Меню =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎯 Случайная цитата", callback_data="random")],
        [InlineKeyboardButton("📂 Выбрать категорию", callback_data="categories")],
        [InlineKeyboardButton("📝 Мои последние цитаты", callback_data="history")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]])

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        f"🎶 Добро пожаловать в {BOT_NAME} — твой помощник по цитатам и мотивации!\n"
        "🚀 Я могу показать тебе случайные цитаты, или ты можешь выбрать категорию.\n\n"
        "📌 Основные функции:\n"
        "- Случайная цитата — мгновенно покажу вдохновляющую цитату.\n"
        "- Категории — выбери тему и получай цитаты по интересам.\n"
        "- Мои последние цитаты — быстро вспомни последние полученные цитаты.\n\n"
        "🎉 Попробуй прямо сейчас, выбрав опцию ниже!"
    )

# ===================== Цитата без повторов =====================
def get_unique_quote(user_id, category=None):
    if user_id not in user_queues:
        user_queues[user_id] = {}
    if user_id not in user_history:
        user_history[user_id] = []

    if category:
        if category not in user_queues[user_id] or not user_queues[user_id][category]:
            user_queues[user_id][category] = QUOTE_CATEGORIES[category].copy()
            random.shuffle(user_queues[user_id][category])
        quote = user_queues[user_id][category].pop()
    else:
        chosen_cat = random.choice(list(QUOTE_CATEGORIES.keys()))
        quote = get_unique_quote(user_id, chosen_cat)
        return quote

    # Добавляем в историю
    user_history[user_id].append(quote)
    if len(user_history[user_id]) > 5:
        user_history[user_id].pop(0)

    return quote

# ===================== Безопасное редактирование =====================
async def safe_edit_message(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        pass

# ===================== Кнопки =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"
    user_id = query.from_user.id

    if query.data == "random":
        quote = get_unique_quote(user_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Ещё одна цитата", callback_data="random")],
            [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
        ])
        await safe_edit_message(query, f"🎯 Случайная цитата:\n\n{quote}", reply_markup=keyboard)

    elif query.data == "categories":
        keyboard = [[InlineKeyboardButton(name, callback_data=f"cat_{name}")] for name in QUOTE_CATEGORIES.keys()]
        keyboard.append([InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")])
        await safe_edit_message(query, "📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("cat_"):
        category = query.data.replace("cat_", "")
        quote = get_unique_quote(user_id, category)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 Ещё одна цитата", callback_data=f"cat_{category}")],
            [InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]
        ])
        await safe_edit_message(query, f"📂 {category}:\n\n{quote}", reply_markup=keyboard)

    elif query.data == "history":
        quotes = user_history.get(user_id, [])
        if not quotes:
            text = "📝 У тебя пока нет цитат в истории."
        else:
            text = "📝 Твои последние цитаты:\n\n" + "\n\n".join(quotes)
        await safe_edit_message(query, text, reply_markup=back_menu())

    elif query.data == "about":
        await safe_edit_message(
            query,
            f"ℹ️ *О {BOT_NAME}*\n\n"
            "💡 QuoteAura — это бот, который вдохновляет тебя цитатами и мотивацией.\n"
            "🎯 Случайные цитаты, подборки по категориям, просмотр истории и inline режим.\n\n"
            "Автор: @QuotesAuraBot",
            parse_mode="Markdown",
            reply_markup=back_menu()
        )

    elif query.data == "back":
        await safe_edit_message(query, full_greeting(user_name), reply_markup=main_menu())

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(full_greeting(user_name), reply_markup=main_menu())

# ===================== MAIN =====================
if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 10000))
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(button_handler))

    print(f"{BOT_NAME} бот запущен...")
    app.run_polling()
