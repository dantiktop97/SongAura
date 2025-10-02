# combined_bots.py
import os
import json
import threading
import asyncio
import time
import random

# ----- CONFIG (через env) -----
STAR = os.getenv("STAR")                      # token для telebot (игровой)
AIO_TOKEN = os.getenv("AIO_TOKEN") or STAR    # если AIO_TOKEN не задан, используем STAR
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "")  # оставляем пустым по умолчанию
CURRENCY = os.getenv("CURRENCY", "RUB")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

# ----- BALANCE UTILS (sync + async) -----
BALANCE_FILE = "balances.json"
_file_lock = threading.Lock()
_async_lock = asyncio.Lock()

def _ensure_file():
    if not os.path.exists(BALANCE_FILE):
        with open(BALANCE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_balances():
    _ensure_file()
    with _file_lock:
        with open(BALANCE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return {}

def save_balances(balances):
    _ensure_file()
    with _file_lock:
        tmp = BALANCE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(balances, f)
        os.replace(tmp, BALANCE_FILE)

def get_balance(user_id, default=0):
    balances = load_balances()
    return int(balances.get(str(user_id), default))

def set_balance(user_id, value):
    balances = load_balances()
    balances[str(user_id)] = int(value)
    save_balances(balances)

def add_balance(user_id, delta):
    balances = load_balances()
    balances[str(user_id)] = int(balances.get(str(user_id), 0)) + int(delta)
    save_balances(balances)

# Async wrappers for aiogram handlers
async def aload_balances():
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, load_balances)

async def aget_balance(user_id, default=0):
    balances = await aload_balances()
    return int(balances.get(str(user_id), default))

async def aadd_balance(user_id, delta):
    async with _async_lock:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, add_balance, user_id, delta)

# ----- TELEBOT (sync) game bot -----
try:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
except Exception:
    telebot = None

if telebot and STAR:
    TOKEN = STAR
    tb_bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

    SYMBOLS = [
        ("🍒", 25),
        ("🍋", 25),
        ("🍉", 20),
        ("⭐", 15),
        ("7️⃣", 5),
    ]

    BALANCE_START = 0
    spin_locks = set()

    def weighted_choice(symbols):
        items, weights = zip(*symbols)
        return random.choices(items, weights=weights, k=1)[0]

    def spin_once():
        return [[weighted_choice(SYMBOLS) for _ in range(3)] for _ in range(3)]

    def eval_middle_row(matrix):
        mid = matrix[1]
        if mid[0] == mid[1] == mid[2]:
            s = mid[0]
            if s == "7️⃣":
                return "jackpot", 5
            if s == "⭐":
                return "star", 3
            return "fruit", 2
        return "lose", 0

    def main_menu_kb():
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"))
        kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))
        return kb

    def roulette_kb():
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🎟️ СПИН", callback_data="spin"))
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        return kb

    def result_kb():
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="spin"))
        kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        return kb

    @tb_bot.message_handler(commands=['start'])
    def tb_start(message):
        name = message.from_user.first_name or "игрок"
        text = (
            f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b>!\n\n"
            f"Нажми <b>ИГРАТЬ</b>, чтобы сделать спин (стоимость 1 ⭐️).\n"
            f"Проверить баланс: /balance"
        )
        tb_bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

    @tb_bot.message_handler(commands=['balance'])
    def tb_balance(message):
        bal = get_balance(message.from_user.id, BALANCE_START)
        tb_bot.send_message(message.chat.id, f"💰 Ваш баланс: {bal} ⭐️")

    @tb_bot.callback_query_handler(func=lambda call: True)
    def tb_callback(call):
        data = call.data
        if data == "play":
            tb_bot.edit_message_text(
                "🎰 <b>Рулетка</b>\n\nВыберите <b>СПИН</b> чтобы сыграть (1 ⭐️)",
                call.message.chat.id, call.message.message_id, reply_markup=roulette_kb()
            )
        elif data == "spin":
            tb_spin_handler(call)
        elif data == "profile":
            uid = call.from_user.id
            bal = get_balance(uid, BALANCE_START)
            tb_bot.edit_message_text(
                f"👤 <b>Профиль</b>\n\n🆔 <b>Ваш ID:</b> {uid}\n💰 <b>Баланс:</b> {bal} ⭐️",
                call.message.chat.id, call.message.message_id,
                reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
            )
        elif data == "back_to_main":
            name = call.from_user.first_name or "игрок"
            tb_bot.edit_message_text(
                f"✨ Привет, <b>{name}</b>! Возвращение в меню.",
                call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb()
            )
        tb_bot.answer_callback_query(call.id)

    def tb_spin_handler(call):
        chat_id = call.message.chat.id
        user_id = call.from_user.id

        if chat_id in spin_locks:
            tb_bot.answer_callback_query(call.id, "Спин уже выполняется. Подождите...", show_alert=False)
            return

        bal = get_balance(user_id, BALANCE_START)
        bet = 1
        if bal < bet:
            tb_bot.answer_callback_query(call.id, "Недостаточно звёзд. Пополните баланс.", show_alert=True)
            tb_bot.send_message(chat_id, "Чтобы пополнить баланс, используйте /buy в платёжном боте.")
            return

        bal -= bet
        set_balance(user_id, bal)

        spin_locks.add(chat_id)
        tb_bot.answer_callback_query(call.id)
        threading.Thread(target=_tb_run_quick_spin, args=(call, user_id, bet)).start()

    def _tb_run_quick_spin(call, user_id, bet):
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        refunded = False
        try:
            final = spin_once()
            middle = final[1]
            result, mult = eval_middle_row(final)

            bal = get_balance(user_id, BALANCE_START)
            if result != "lose":
                win = bet * mult
                bal += win
                set_balance(user_id, bal)

            middle_text = " | ".join(middle)
            if result == "lose":
                suffix = f"\n\n❌ <b>Увы… комбинация не совпала.</b>\n💰 <b>Баланс:</b> {bal} ⭐️"
            else:
                suffix = f"\n\n🎉 <b>Вы выиграли!</b>\n✨ <b>Выигрыш:</b> ×{mult}\n💰 <b>Баланс:</b> {bal} ⭐️"

            text = f"<b>Выпало:</b>\n{middle_text}{suffix}"
            tb_bot.edit_message_text(text, chat_id, msg_id, reply_markup=result_kb(), parse_mode="HTML")
        except Exception:
            try:
                bal = get_balance(user_id, BALANCE_START)
                bal += bet
                set_balance(user_id, bal)
                refunded = True
                tb_bot.edit_message_text("Произошла ошибка при расчёте результата. Ставка возвращена.", chat_id, msg_id)
            except:
                pass
        finally:
            spin_locks.discard(chat_id)
            if refunded:
                try:
                    tb_bot.send_message(user_id, "⚠️ Ставка возвращена из-за ошибки. Баланс восстановлен.")
                except:
                    pass

    def run_telebot():
        try:
            tb_bot.remove_webhook()
        except:
            pass
        tb_bot.infinity_polling()
else:
    def run_telebot():
        print("telebot не установлен или STAR не задан, пропускаем запуск telebot.")

# ----- AIOGRAM (async) payment bot example -----
try:
    from aiogram import Bot, Dispatcher, types
    from aiogram.types import LabeledPrice, PreCheckoutQuery
    from aiogram.filters import Command
except Exception:
    Bot = None

if Bot and AIO_TOKEN:
    aio_bot = Bot(token=AIO_TOKEN)
    dp = Dispatcher()

    @dp.message(Command("buy"))
    async def cmd_buy(message: types.Message):
        amount_stars = 10
        price_amount = 100
        payload = f"buy:{message.from_user.id}:{amount_stars}"
        prices = [LabeledPrice(label=f"{amount_stars} ⭐️", amount=price_amount)]
        await aio_bot.send_invoice(
            chat_id=message.chat.id,
            title="Покупка звёзд",
            description=f"Пакет {amount_stars} ⭐️",
            payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency=CURRENCY,
            prices=prices
        )

    @dp.pre_checkout_query()
    async def process_pre_checkout(pre_checkout_q: PreCheckoutQuery):
        await pre_checkout_q.answer(ok=True)

    @dp.message()
    async def handle_successful_payment(message: types.Message):
        if not message.successful_payment:
            return
        sp = message.successful_payment
        payload = sp.invoice_payload or ""
        if payload.startswith("buy:"):
            parts = payload.split(":")
            try:
                amount_stars = int(parts[2])
            except:
                amount_stars = 0
            buyer_id = message.from_user.id
            if amount_stars > 0:
                await aadd_balance(buyer_id, amount_stars)
                await message.answer(f"✅ Оплата принята. На баланс начислено {amount_stars} ⭐️")
                return
        try:
            total_amount = int(sp.total_amount)
            stars = total_amount // 10
            if stars > 0:
                await aadd_balance(message.from_user.id, stars)
                await message.answer(f"✅ Оплата принята. На баланс начислено {stars} ⭐️")
                return
        except:
            pass
        await message.answer("⚠️ Оплата принята, но не удалось определить количество звёзд. Свяжитесь с поддержкой.")

    async def run_aiogram():
        await dp.start_polling(aio_bot)
else:
    async def run_aiogram():
        print("aiogram не настроен или AIO_TOKEN пуст, пропускаем aiogram.")

# ----- MAIN: запускаем telebot в потоке и aiogram в asyncio -----
def main():
    t = threading.Thread(target=run_telebot, daemon=True)
    t.start()

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(run_aiogram())
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if Bot and AIO_TOKEN:
                loop.run_until_complete(aio_bot.session.close())
        except:
            pass

if __name__ == "__main__":
    main()
