import os
import random
import time
import json
import threading
from flask import Flask, request, abort
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery

# ====== Настройки ======
TOKEN = os.getenv("STAR")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "")
CURRENCY = os.getenv("CURRENCY", "XTR")
PORT = int(os.getenv("PORT", "10000"))
RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
BALANCE_FILE = "balances.json"

if not TOKEN:
    raise RuntimeError("Переменная STAR не установлена")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)
balances_lock = threading.Lock()

# ====== Символы и шансы ======
SYMBOLS = [("🍒", 25), ("🍋", 25), ("🍉", 20), ("⭐", 15), ("7️⃣", 5)]
MULTIPLIERS = {"fruit": 2, "star": 3, "jackpot": 5}

# ====== Баланс ======
def load_balances():
    try:
        with balances_lock:
            if not os.path.exists(BALANCE_FILE):
                return {}
            with open(BALANCE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        return {}

def save_balances(balances):
    try:
        with balances_lock:
            with open(BALANCE_FILE, "w", encoding="utf-8") as f:
                json.dump(balances, f, ensure_ascii=False)
    except Exception as e:
        print("Ошибка при сохранении:", e)

balances = load_balances()

def get_balance(user_id):
    with balances_lock:
        return int(balances.get(str(user_id), 100))

def set_balance(user_id, value):
    with balances_lock:
        balances[str(user_id)] = int(value)
        save_balances(balances)

# ====== Рулетка ======
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
            return "jackpot", MULTIPLIERS["jackpot"]
        if s == "⭐":
            return "star", MULTIPLIERS["star"]
        return "fruit", MULTIPLIERS["fruit"]
    return "lose", 0

def matrix_to_text(matrix):
    return "\n".join("| " + " | ".join(row) + " |" for row in matrix)

def make_result_text(matrix, result, mult, new_balance):
    mid = matrix[1]
    if result == "lose":
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"❌ <b>Увы… комбинация не совпала.</b>\n"
            f"💰 <b>Баланс:</b> {new_balance} ⭐️\n"
            f"Попробуйте ещё раз!"
        )
    else:
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"🎉 <b>Победа!</b> {' '.join(mid)}\n"
            f"✨ <b>Выигрыш:</b> ×{mult}\n"
            f"💰 <b>Баланс:</b> {new_balance} ⭐️"
        )

# ====== Клавиатуры ======
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"))
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))
    return kb

def play_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("КРУТИТЬ ЗА 15 ⭐️", callback_data="spin_15"))
    kb.add(InlineKeyboardButton("КРУТИТЬ ЗА 25 ⭐️", callback_data="spin_25"))
    kb.add(InlineKeyboardButton("КРУТИТЬ ЗА 50 ⭐️", callback_data="spin_50"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def profile_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def result_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="play"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

# ====== Тексты ======
def welcome_text(name):
    return (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> — здесь выигрыши не ждут, они случаются! ✨\n\n"
        f"🎁 <b>Мгновенные бонусы</b> — прямо на аккаунт\n"
        f"🎰 <b>Розыгрыши и игры</b> — каждый шанс на выигрыш реально захватывающий\n"
        f"📲 <b>Удобный формат</b> — всё работает прямо в Telegram\n\n"
        f"Запускаем удачу! 🌟"
    )

def play_text():
    return (
        "🎰 <b>Раздел ИГРАТЬ</b>\n\n"
        "💡 Выберите ставку:\n"
        "• За 15 ⭐️ можно выиграть до 100 ⭐️\n"
        "• За 25 ⭐️ — до 150 ⭐️\n"
        "• За 50 ⭐️ — до 250 ⭐️\n\n"
        "Чем выше ставка — тем выше шанс на крупный выигрыш!"
    )

def profile_text(uid, bal):
    return (
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 <b>ID:</b> {uid}\n"
        f"💰 <b>Баланс:</b> {bal} ⭐️\n\n"
        f"Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
        f"Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰"
    )

# ====== Хэндлеры ======
@bot.message_handler(commands=["start"])
def start(message):
    name = message.from_user.first_name or "игрок"
    bot.send_message(message.chat.id, welcome_text(name), reply_markup=main_menu_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "play")
def play(call):
    bot.edit_message_text(play_text(), call.message.chat.id, call.message.message_id, reply_markup=play_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    bot.edit_message_text(profile_text(uid, bal), call.message.chat.id, call.message.message_id, reply_markup=profile_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back(call):
    name = call.from_user.first_name or "игрок"
    bot.edit_message_text(welcome_text(name), call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb(), parse_mode="HTML")

# ====== Оплата ======
@bot.callback_query_handler(func=lambda call: call.data in {"spin_15", "spin_25", "spin_50"})
def spin_pay(call):
    stake_map = {"spin_15": 15, "spin_25": 25, "spin_50": 50}
    stake = stake_map[call.data]
    payload = f"spin:{call.from_user.id}:{stake}:{int(time.time()*1000)}"
    prices = [LabeledPrice(label=f"Спин за {stake} ⭐️", amount=stake)]

    try:
        bot.send_invoice(
            call.message.chat.id,
            title=f"Спин за {stake} ⭐️",
            description="Оплата за слот машину",
            invoice_payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency=CURRENCY,
            prices=prices
        )
    except Exception as e:
        bot.answer_callback_query(call.id, f"Ошибка: {e}", show_alert=True)
        return

    bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query: PreCheckoutQuery):
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok
