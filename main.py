import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("STAR")
bot = telebot.TeleBot(TOKEN, parse_mode=None)

def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"),
        InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile")
    )
    return kb

def roulette_kb():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🎟️ СПИН", callback_data="spin"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    return kb

def result_kb():
    kb = InlineKeyboardMarkup()
    kb.row(
        InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="spin"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )
    return kb

@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name or "игрок"
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
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    if data == "play":
        bot.edit_message_text(
            "🎰 Раздел рулетка\n\n"
            "Добро пожаловать в фруктовую рулетку!\n"
            "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
            "💡 Правила игры:\n"
            "• 3 одинаковых фрукта → выигрыш ×2\n"
            "• 3 звезды ⭐ → выигрыш ×3\n"
            "• 3 семёрки 7️⃣ → джекпот ×5\n"
            "• Любая неполная комбинация → выигрыш отсутствует",
            call.message.chat.id, call.message.message_id, reply_markup=roulette_kb()
        )
    elif data == "spin":
        bot.edit_message_text(
            "…БАРАБАНЫ КРУТЯТСЯ… 🎰\n\n"
            "| ⭐ | ⭐ | ⭐ |\n\n"
            "🎉 Отлично! Вы собрали три одинаковых символа!\n"
            "✨ Ваша ставка увеличивается!\n"
            "💰 Ваш баланс: 1234 монет\n"
            "Не останавливайтесь — сыграйте ещё раз и ловите удачу! 🍀",
            call.message.chat.id, call.message.message_id, reply_markup=result_kb()
        )
    elif data == "profile":
        uid = call.from_user.id
        bot.edit_message_text(
            f"👤 Профиль\n\n🆔 Ваш ID: {uid}\n💰 Ваш текущий баланс: 0⭐️\n\n"
            "Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
            "Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰",
            call.message.chat.id, call.message.message_id,
            reply_markup=InlineKeyboardMarkup().row(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        )
    elif data == "back_to_main":
        name = call.from_user.first_name or "игрок"
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
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb())
    bot.answer_callback_query(call.id)

if __name__ == "__main__":
    # Render обычно запускает web-процесс; для Polling просто запустить bot.infinity_polling()
    bot.infinity_polling()
