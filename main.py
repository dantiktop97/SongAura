import os
import random
import time
import json
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery

TOKEN = os.getenv("STAR")   # токен твоего бота (секрет STAR)
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

BALANCE_FILE = "balances.json"
spin_locks = set()

SYMBOLS = [
    ("🍒", 25),
    ("🍋", 25),
    ("🍉", 20),
    ("⭐", 15),
    ("7️⃣", 5),
]

def load_balances():
    try:
        with open(BALANCE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_balances(balances):
    with open(BALANCE_FILE, "w", encoding="utf-8") as f:
        json.dump(balances, f)

balances = load_balances()

def get_balance(user_id):
    return int(balances.get(str(user_id), 1000))

def set_balance(user_id, value):
    balances[str(user_id)] = int(value)
    save_balances(balances)

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

def matrix_to_text(matrix):
    return "\n".join("| " + " | ".join(row) + " |" for row in matrix)

def make_result_text(matrix, result, mult, new_balance):
    mid = matrix[1]
    if result == "lose":
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"❌ <b>Увы… комбинация не совпала.</b>\n"
            f"💰 <b>Баланс:</b> {new_balance} монет\n"
            f"Не расстраивайтесь — сыграйте ещё раз, удача рядом! ✨🎰"
        )
    else:
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"🎉 <b>Отлично!</b> Вы собрали: {' '.join(mid)}\n"
            f"✨ <b>Выигрыш:</b> ×{mult}\n"
            f"💰 <b>Баланс:</b> {new_balance} монет\n"
            f"Не останавливайтесь — сыграйте ещё раз и ловите удачу! 🍀"
        )

# ---- клавиатуры ----
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"))
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))
    return kb

def roulette_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎟️ СПИН (1⭐)", callback_data="spin_pay"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def result_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Сыграть ещё раз (1⭐)", callback_data="spin_pay"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

# ---- /start ----
@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name or "игрок"
    text = (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> ✨\n\n"
        f"Жми «ИГРАТЬ» и пробуй удачу 🎰"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

# ---- play ----
@bot.callback_query_handler(func=lambda call: call.data == "play")
def play(call):
    bot.edit_message_text(
        "🎰 <b>Фруктовая рулетка</b>\n\n"
        "• 3 фрукта → ×2\n"
        "• 3 ⭐ → ×3\n"
        "• 3 7️⃣ → ×5\n"
        "• иначе → проигрыш",
        call.message.chat.id, call.message.message_id, reply_markup=roulette_kb(), parse_mode="HTML"
    )

# ---- оплата звездами ----
@bot.callback_query_handler(func=lambda call: call.data == "spin_pay")
def spin_pay(call):
    prices = [LabeledPrice(label="Один спин 🎰", amount=1)]  # 1⭐
    bot.send_invoice(
        call.message.chat.id,
        title="🎰 Спин",
        description="Крути рулетку за 1⭐",
        invoice_payload="spin_slot",
        provider_token="",  # для Stars можно оставить пустым
        currency="XTR",
        prices=prices
    )
    bot.answer_callback_query(call.id)

# ---- подтверждение платежа ----
@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query: PreCheckoutQuery):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

# ---- успешная оплата ----
@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    if message.successful_payment.invoice_payload != "spin_slot":
        return
    user_id = message.from_user.id
    threading.Thread(target=do_spin, args=(message.chat.id, user_id)).start()

# ---- логика спина ----
def do_spin(chat_id, user_id):
    msg = bot.send_message(chat_id, "…БАРАБАНЫ КРУТЯТСЯ… 🎰")

    frames = [spin_once() for _ in range(3)]
    for frame in frames:
        bot.edit_message_text(matrix_to_text(frame), chat_id, msg.message_id)
        time.sleep(0.6)

    final = spin_once()
    result, mult = eval_middle_row(final)

    bal = get_balance(user_id)
    # списание 1⭐
    bet = 1
    bal -= bet
    if result != "lose":
        win = bet * mult
        bal += win
    set_balance(user_id, bal)

    text = make_result_text(final, result, mult, bal)
    bot.edit_message_text(text, chat_id, msg.message_id, reply_markup=result_kb(), parse_mode="HTML")

# ---- профиль ----
@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    bot.edit_message_text(
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 ID: {uid}\n"
        f"💰 Баланс: {bal}⭐️",
        call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb(), parse_mode="HTML"
    )

# ---- назад ----
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back(call):
    name = call.from_user.first_name or "игрок"
    bot.edit_message_text(
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> ✨",
        call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb(), parse_mode="HTML"
    )

if __name__ == "__main__":
    bot.infinity_polling()
