import asyncio
import random
import aiosqlite
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, PreCheckoutQuery

# ================== НАСТРОЙКИ ==================
# Секрет STAR из переменной окружения
STAR = os.getenv("STAR")
if not STAR:
    raise RuntimeError("Переменная окружения STAR не установлена!")

DB_PATH = "casino.sqlite3"

bot = Bot(token=STAR)  # используем STAR как токен бота
dp = Dispatcher()

# ================== БАЗА ==================
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS spins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            result TEXT NOT NULL
        )
        """)
        await db.commit()

# ================== КОМАНДЫ ==================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    kb = types.InlineKeyboardMarkup(
        inline_keyboard=[[types.InlineKeyboardButton(text="Купить спин 🎰 (1⭐)", callback_data="buy_spin")]]
    )
    await message.answer(
        "Добро пожаловать в безопасное казино 🎲!\nЖми кнопку, чтобы купить спин:", 
        reply_markup=kb
    )

# ================== КУПИТЬ СПИН ==================
@dp.callback_query(F.data == "buy_spin")
async def cb_buy_spin(callback: types.CallbackQuery):
    prices = [LabeledPrice(label="🎰 Спин", amount=1)]  # 1 Star
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title="Один спин",
        description="Крути слот за 1⭐!",
        payload="spin",           # полезная нагрузка
        provider_token="",        # тест/Stars
        currency="XTR",
        prices=prices
    )
    await callback.answer()

# ================== ПРЕДОПЛАТА ==================
@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
    await pre_checkout_q.answer(ok=True)

# ================== УСПЕШНЫЙ ПЛАТЁЖ ==================
@dp.message(F.content_type == types.ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(message: types.Message):
    sp = message.successful_payment
    if not sp or sp.invoice_payload != "spin":
        return

    # 🎰 Крутим слот
    symbols = ["🍒", "🍋", "🍊", "🍇", "⭐", "💎"]
    result = [random.choice(symbols) for _ in range(3)]

    # Проверка выигрыша
    if len(set(result)) == 1:
        text = f"🎉 JACKPOT! {''.join(result)}\nТы поймал три одинаковых!"
    else:
        text = f"Крутится слот... {''.join(result)}\nПопробуй снова 🙂"

    # Сохраняем результат
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO spins (user_id, username, result) VALUES (?, ?, ?)",
            (message.from_user.id, message.from_user.username, ''.join(result))
        )
        await db.commit()

    await message.answer(text)

# ================== ЗАПУСК ==================
async def main():
    await init_db()
    print("Бот запущен! ⭐ Используется секрет STAR.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
