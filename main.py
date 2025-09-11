import os
import random
from telegram import (
    Update, InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes,
    InlineQueryHandler, CallbackQueryHandler
)

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Твой токен бота
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

# Хранение состояния пользователя, чтобы цитаты не повторялись
user_queues = {}  # {user_id: {category: [цитаты для показа]}}

# ===================== Меню =====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("🎯 Случайная цитата", callback_data="random")],
        [InlineKeyboardButton("📂 Выбрать категорию", callback_data="categories")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_menu():
    keyboard = [[InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")]]
    return InlineKeyboardMarkup(keyboard)

# ===================== Приветствие =====================
def full_greeting(user_name: str) -> str:
    return (
        f"👋 Привет, {user_name}!\n\n"
        "🎶 Добро пожаловать в QuoteAura — твой помощник по цитатам и мотивации!\n"
        "🚀 Я могу показать тебе случайные цитаты, или ты можешь выбрать категорию.\n\n"
        "📌 Основные функции:\n"
        "- Случайная цитата — мгновенно покажу вдохновляющую цитату.\n"
        "- Категории — выбери тему и получай цитаты по интересам.\n"
        "- Inline поиск — используй меня в любом чате через @YourBot.\n\n"
        "🎉 Попробуй прямо сейчас, выбрав опцию ниже!"
    )

# ===================== Inline поиск =====================
async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query

    results = []
    all_quotes = [q for quotes in QUOTE_CATEGORIES.values() for q in quotes]

    if not query:
        # Случайные цитаты
        for i in range(min(5, len(all_quotes))):
            quote = random.choice(all_quotes)
            results.append(InlineQueryResultArticle(
                id=str(i),
                title=f"Цитата {i+1}",
                input_message_content=InputTextMessageContent(quote)
            ))
    else:
        # Поиск по слову
        filtered = [q for q in all_quotes if query.lower() in q.lower()]
        for i, q in enumerate(filtered):
            results.append(InlineQueryResultArticle(
                id=str(i),
                title=q[:30] + "...",
                input_message_content=InputTextMessageContent(q)
            ))

    await update.inline_query.answer(results, cache_time=1)

# ===================== Получение цитаты без повторов =====================
def get_unique_quote(user_id, category=None):
    if user_id not in user_queues:
        user_queues[user_id] = {}

    if category:
        if category not in user_queues[user_id] or not user_queues[user_id][category]:
            # Если очередь пуста, создаем новую и перемешиваем
            user_queues[user_id][category] = QUOTE_CATEGORIES[category].copy()
            random.shuffle(user_queues[user_id][category])
        return user_queues[user_id][category].pop()
    else:
        # Для случайной категории
        all_categories = list(QUOTE_CATEGORIES.keys())
        chosen_cat = random.choice(all_categories)
        return get_unique_quote(user_id, chosen_cat)

# ===================== Безопасное редактирование =====================
async def safe_edit_message(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        pass

# ===================== Обработчик кнопок =====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_name = query.from_user.first_name or "друг"
    user_id = query.from_user.id

    if query.data == "random":
        quote = get_unique_quote(user_id)
        await safe_edit_message(query, f"🎯 Случайная цитата:\n\n{quote}", reply_markup=back_menu())

    elif query.data == "categories":
        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"cat_{name}")] for name in QUOTE_CATEGORIES.keys()
        ]
        keyboard.append([InlineKeyboardButton("⬅️ Вернуться назад", callback_data="back")])
        await safe_edit_message(query, "📂 Выберите категорию:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data.startswith("cat_"):
        category = query.data.replace("cat_", "")
        quote = get_unique_quote(user_id, category)
        await safe_edit_message(query, f"📂 {category}:\n\n{quote}", reply_markup=back_menu())

    elif query.data == "about":
        await safe_edit_message(
            query,
            f"ℹ️ *О QuoteAura*\n\n"
            "💡 QuoteAura — это бот, который вдохновляет тебя цитатами и мотивацией.\n"
            "🎯 Случайные цитаты, подборки по категориям и inline поиск.\n"
            "🚀 Используй Inline режим через @YourBot, чтобы делиться цитатами прямо в чате.\n\n"
            "Автор: @YourBot",
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
    app.add_handler(InlineQueryHandler(inline_query))

    print("QuoteAura бот запущен...")
    app.run_polling()
