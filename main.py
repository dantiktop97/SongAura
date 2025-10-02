import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, CallbackContext

TOKEN = os.getenv("STAR")
updater = Updater(token=TOKEN, use_context=True)
dispatcher = updater.dispatcher

def main_menu_kb():
    kb = [[InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"),
           InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile")]]
    return InlineKeyboardMarkup(kb)

def roulette_kb():
    kb = [[InlineKeyboardButton("🎟️ СПИН", callback_data="spin"),
           InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(kb)

def result_kb():
    kb = [[InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="spin"),
           InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(kb)

def start(update: Update, context: CallbackContext):
    name = update.effective_user.first_name or "игрок"
    text = (
        f"✨ Главное меню\n\n"
        f"✨ Привет, {name}! Добро пожаловать в StarryCasino — здесь выигрыши не ждут, они случаются! ✨\n\n"
        f"Что тебя ждёт:\n\n"
        f"🎁 Мгновенные бонусы — прямо на аккаунт, без задержек\n"
        f"🎰 Розыгрыши и игры — каждый шанс на выигрыш реально захватывающий\n"
        f"📲 Удобный формат — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
        f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
        f"Запускаем удачу! 🌟"
    )
    update.message.reply_text(text, reply_markup=main_menu_kb())

def callback_handler(update: Update, context: CallbackContext):
    data = update.callback_query.data
    q = update.callback_query
    if data == "play":
        q.edit_message_text(
            "🎰 Раздел рулетка\n\n"
            "Добро пожаловать в фруктовую рулетку!\n"
            "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
            "💡 Правила игры:\n"
            "• 3 одинаковых фрукта → выигрыш ×2\n"
            "• 3 звезды ⭐ → выигрыш ×3\n"
            "• 3 семёрки 7️⃣ → джекпот ×5\n"
            "• Любая неполная комбинация → выигрыш отсутствует",
            reply_markup=roulette_kb()
        )
    elif data == "spin":
        q.edit_message_text(
            "…БАРАБАНЫ КРУТЯТСЯ… 🎰\n\n"
            "| ⭐ | ⭐ | ⭐ |\n\n"
            "🎉 Отлично! Вы собрали три одинаковых символа!\n"
            "✨ Ваша ставка увеличивается!\n"
            "💰 Ваш баланс: 1234 монет\n"
            "Не останавливайтесь — сыграйте ещё раз и ловите удачу! 🍀",
            reply_markup=result_kb()
        )
    elif data == "profile":
        uid = q.from_user.id
        q.edit_message_text(
            f"👤 Профиль\n\n🆔 Ваш ID: {uid}\n💰 Ваш текущий баланс: 0⭐️\n\n"
            "Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
            "Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]])
        )
    elif data == "back_to_main":
        name = q.from_user.first_name or "игрок"
        q.edit_message_text(
            f"✨ Главное меню\n\n"
            f"✨ Привет, {name}! Добро пожаловать в StarryCasino — здесь выигрыши не ждут, они случаются! ✨\n\n"
            f"Что тебя ждёт:\n\n"
            f"🎁 Мгновенные бонусы — прямо на аккаунт, без задержек\n"
            f"🎰 Розыгрыши и игры — каждый шанс на выигрыш реально захватывающий\n"
            f"📲 Удобный формат — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
            f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
            f"Запускаем удачу! 🌟",
            reply_markup=main_menu_kb()
        )
    q.answer()

dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CallbackQueryHandler(callback_handler))

if __name__ == "__main__":
    updater.start_polling()
    updater.idle()
