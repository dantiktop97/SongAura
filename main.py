from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils import executor
import os

TOKEN = os.getenv("STAR")
bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# Кнопки
def main_menu():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"),
        InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile")
    )

def roulette_menu():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🎟️ СПИН", callback_data="spin"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )

def result_menu():
    return InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="spin"),
        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
    )

# Команды
@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    name = message.from_user.first_name
    await message.answer(
        f"✨ Главное меню\n\n"
        f"✨ Привет, {name}! Добро пожаловать в StarryCasino — здесь выигрыши не ждут, они случаются! ✨\n\n"
        f"Что тебя ждёт:\n\n"
        f"🎁 Мгновенные бонусы — прямо на аккаунт, без задержек\n"
        f"🎰 Розыгрыши и игры — каждый шанс на выигрыш реально захватывающий\n"
        f"📲 Удобный формат — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
        f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
        f"Запускаем удачу! 🌟",
        reply_markup=main_menu()
    )

@dp.callback_query_handler(lambda c: c.data == "play")
async def play(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🎰 Раздел рулетка\n\n"
        "Добро пожаловать в фруктовую рулетку!\n"
        "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
        "💡 Правила игры:\n"
        "• 3 одинаковых фрукта → выигрыш ×2\n"
        "• 3 звезды ⭐ → выигрыш ×3\n"
        "• 3 семёрки 7️⃣ → джекпот ×5\n"
        "• Любая неполная комбинация → выигрыш отсутствует",
        reply_markup=roulette_menu()
    )

@dp.callback_query_handler(lambda c: c.data == "spin")
async def spin(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "…БАРАБАНЫ КРУТЯТСЯ… 🎰\n\n"
        "| ⭐ | ⭐ | ⭐ |\n\n"
        "🎉 Отлично! Вы собрали три одинаковых символа!\n"
        "✨ Ваша ставка увеличивается!\n"
        "💰 Ваш баланс: 1234 монет\n"
        "Не останавливайтесь — сыграйте ещё раз и ловите удачу! 🍀",
        reply_markup=result_menu()
    )

@dp.callback_query_handler(lambda c: c.data == "profile")
async def profile(callback: types.CallbackQuery):
    uid = callback.from_user.id
    await callback.message.edit_text(
        f"👤 Профиль\n\n"
        f"🆔 Ваш ID: {uid}\n"
        f"💰 Ваш текущий баланс: 0⭐️\n\n"
        "Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
        "Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
        )
    )

@dp.callback_query_handler(lambda c: c.data == "back_to_main")
async def back(callback: types.CallbackQuery):
    name = callback.from_user.first_name
    await callback.message.edit_text(
        f"✨ Главное меню\n\n"
        f"✨ Привет, {name}! Добро пожаловать в StarryCasino — здесь выигрыши не ждут, они случаются! ✨\n\n"
        f"Что тебя ждёт:\n\n"
        f"🎁 Мгновенные бонусы — прямо на аккаунт, без задержек\n"
        f"🎰 Розыгрыши и игры — каждый шанс на выигрыш реально захватывающий\n"
        f"📲 Удобный формат — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
        f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
        f"Запускаем удачу! 🌟",
        reply_markup=main_menu()
    )

if __name__ == "__main__":
    executor.start_polling(dp)
