import os
import random
import time
import json
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = os.getenv("STAR")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# убрать webhook, чтобы избежать ошибки 409 при polling
try:
    bot.remove_webhook()
except Exception:
    pass

BALANCE_FILE = "balances.json"
spin_locks = set()

SYMBOLS = [
    ("🍒", 25),
    ("🍋", 25),
    ("🍉", 20),
    ("⭐", 15),
    ("7️⃣", 5),
]

# ----- balances -----
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

# ----- utilities -----
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

# ----- keyboards (vertical) -----
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

# ----- handlers -----
@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name or "игрок"
    text = (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> — здесь выигрыши не ждут, они случаются! ✨\n\n"
        f"Что тебя ждёт:\n\n"
        f"🎁 <b>Мгновенные бонусы</b> — прямо на аккаунт, без задержек\n"
        f"🎰 <b>Розыгрыши и игры</b> — каждый шанс на выигрыш реально захватывающий\n"
        f"📲 <b>Удобный формат</b> — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
        f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
        f"Запускаем удачу! 🌟"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    if data == "play":
        bot.edit_message_text(
            "🎰 <b>Раздел рулетка</b>\n\n"
            "Добро пожаловать в фруктовую рулетку!\n"
            "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
            "💡 <b>Правила игры:</b>\n"
            "• 3 одинаковых фрукта → выигрыш ×2\n"
            "• 3 звезды ⭐ → выигрыш ×3\n"
            "• 3 семёрки 7️⃣ → джекпот ×5\n"
            "• Любая неполная комбинация → выигрыш отсутствует",
            call.message.chat.id, call.message.message_id, reply_markup=roulette_kb()
        )
    elif data == "spin":
        spin_handler(call)
    elif data == "profile":
        uid = call.from_user.id
        bal = get_balance(uid)
        bot.edit_message_text(
            f"👤 <b>Профиль</b>\n\n🆔 <b>Ваш ID:</b> {uid}\n💰 <b>Ваш текущий баланс:</b> {bal}⭐️\n\n"
            f"Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
            f"Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰",
            call.message.chat.id, call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        )
    elif data == "back_to_main":
        name = call.from_user.first_name or "игрок"
        text = (
            f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> — здесь выигрыши не ждут, они случаются! ✨\n\n"
            f"Что тебя ждёт:\n\n"
            f"🎁 <b>Мгновенные бонусы</b> — прямо на аккаунт, без задержек\n"
            f"🎰 <b>Розыгрыши и игры</b> — каждый шанс на выигрыш реально захватывающий\n"
            f"📲 <b>Удобный формат</b> — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
            f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
            f"Запускаем удачу! 🌟"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb())
    bot.answer_callback_query(call.id)

# ----- quick spin: результат = середина, без колеса/анимации -----
def spin_handler(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if chat_id in spin_locks:
        bot.answer_callback_query(call.id, "Спин уже выполняется. Подождите...", show_alert=False)
        return

    bal = get_balance(user_id)
    bet = 1
    if bal < bet:
        bot.answer_callback_query(call.id, "Недостаточно средств для ставки.", show_alert=True)
        return

    spin_locks.add(chat_id)
    bot.answer_callback_query(call.id)  # закрыть индикатор
    threading.Thread(target=_run_quick_spin, args=(call, user_id, bet)).start()

def _run_quick_spin(call, user_id, bet):
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    try:
        # Генерируем полную 3x3 матрицу, но используем только среднюю строку
        final = spin_once()
        middle = final[1]  # например ["⭐", "🍉", "7️⃣"]

        # Оценка результата по средней строке
        result, mult = eval_middle_row(final)

        # Обновление баланса: списать ставку и добавить выигрыш при победе
        bal = get_balance(user_id)
        bal -= bet
        if result != "lose":
            win = bet * mult
            bal += win
        set_balance(user_id, bal)

        # Формат вывода: ровная строка с разделителем " | "
        middle_text = " | ".join(middle)  # "⭐ | 🍉 | 7️⃣"

        if result == "lose":
            suffix = (
                f"\n\n❌ <b>Увы… комбинация не совпала.</b>\n"
                f"💰 <b>Баланс:</b> {bal} монет"
            )
        else:
            suffix = (
                f"\n\n🎉 <b>Вы выиграли!</b>\n"
                f"✨ <b>Выигрыш:</b> ×{mult}\n"
                f"💰 <b>Баланс:</b> {bal} монет"
            )

        text = f"<b>Выпало:</b>\n{middle_text}{suffix}"
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=result_kb(), parse_mode="HTML")
    except Exception:
        try:
            bot.edit_message_text("Произошла ошибка при расчёте результата. Попробуйте ещё раз.", chat_id, msg_id)
        except:
            pass
    finally:
        spin_locks.discard(chat_id)

if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Polling stopped:", e)
