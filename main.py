import os
import random
import time
import json
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

TOKEN = os.getenv("STAR")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# убрать webhook, чтобы избежать ошибки 409 при polling
try:
    bot.remove_webhook()
except Exception:
    pass

BALANCE_FILE = "balances.json"
spin_locks = set()
pending_spin_invoice = {}  # user_id -> {"chat_id": int, "msg_id": int, "type": "spin_pay" or None}

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
    return int(balances.get(str(user_id), 0))

def set_balance(user_id, value):
    balances[str(user_id)] = int(value)
    save_balances(balances)

def add_balance(user_id, delta):
    balances[str(user_id)] = int(balances.get(str(user_id), 0)) + int(delta)
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
            f"💰 <b>Баланс:</b> {new_balance} ⭐️"
        )
    else:
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"🎉 <b>Отлично!</b> Вы собрали: {' '.join(mid)}\n"
            f"✨ <b>Выигрыш:</b> ×{mult}\n"
            f"💰 <b>Баланс:</b> {new_balance} ⭐️"
        )

# ----- keyboards -----
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"))
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))
    kb.add(InlineKeyboardButton("💳 Купить 1 ⭐️", callback_data="buy_star"))
    return kb

def roulette_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎟️ СПИН (1 ⭐️)", callback_data="spin"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def result_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="spin"))
    kb.add(InlineKeyboardButton("💳 Купить 1 ⭐️", callback_data="buy_star"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

# ----- handlers -----
@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name or "игрок"
    text = (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b>!\n\n"
        f"Нажми ИГРАТЬ → СПИН (стоит 1 ⭐️) или купи ⭐️ прямо здесь."
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

@bot.message_handler(commands=['balance'])
def cmd_balance(message):
    bal = get_balance(message.from_user.id)
    bot.send_message(message.chat.id, f"💰 Ваш баланс: {bal} ⭐️")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    if data == "play":
        bot.edit_message_text(
            "🎰 <b>Раздел рулетка</b>\n\n"
            "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
            "Стоимость спина: <b>1 ⭐️</b>",
            call.message.chat.id, call.message.message_id, reply_markup=roulette_kb()
        )
    elif data == "spin":
        spin_handler(call)
    elif data == "buy_star":
        buy_star_handler(call)
    elif data == "profile":
        uid = call.from_user.id
        bal = get_balance(uid)
        bot.edit_message_text(
            f"👤 <b>Профиль</b>\n\n🆔 <b>Ваш ID:</b> {uid}\n💰 <b>Баланс:</b> {bal} ⭐️",
            call.message.chat.id, call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
        )
    elif data == "back_to_main":
        name = call.from_user.first_name or "игрок"
        text = (
            f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b>!\n\n"
            f"Нажми ИГРАТЬ чтобы начать."
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb())
    bot.answer_callback_query(call.id)

# ----- buy star (invoice) -----
def buy_star_handler(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id
    # отправим заглушку, запомним место, затем отправим инвойс
    sent = bot.send_message(chat_id, "Ожидание оплаты 1 ⭐️… После оплаты баланс обновится.")
    pending_spin_invoice[user_id] = {"chat_id": sent.chat.id, "msg_id": sent.message_id, "type": "buy_star"}
    amount = 100  # минимальные единицы валюты (например копейки). Настрой по своему провайдеру
    prices = [LabeledPrice(label="1 ⭐️", amount=amount)]
    payload = f"buy:1"  # формат: buy:<amount_stars>
    # provider_token оставлен пустым по условию (реальные платежи не пройдут)
    bot.send_invoice(chat_id, title="Покупка 1 ⭐️", description="Покупка 1 звезды для спинов", payload=payload,
                     provider_token="", currency="RUB", prices=prices)

# ----- spin flow -----
def spin_handler(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if chat_id in spin_locks:
        bot.answer_callback_query(call.id, "Спин уже выполняется. Подождите...", show_alert=False)
        return

    bal = get_balance(user_id)
    bet = 1
    if bal < bet:
        # если нет звёзд — предложим оплатить спин напрямую (инвойс) или купить звёзды
        bot.answer_callback_query(call.id, "Недостаточно звёзд. Открой оплату.", show_alert=True)
        # отправляем инвойс для прямой оплаты спина
        sent = bot.send_message(chat_id, "Чтобы оплатить спин (1 ⭐️), завершите оплату ниже.")
        pending_spin_invoice[user_id] = {"chat_id": sent.chat.id, "msg_id": sent.message_id, "type": "spin_pay"}
        amount = 100  # стоимость пакета/спина в минимальных единицах валюты
        prices = [LabeledPrice(label="1 ⭐️ (для спина)", amount=amount)]
        payload = "spin_pay"  # пометка, что это оплата для немедленного спина
        bot.send_invoice(chat_id, title="Оплата спина — 1 ⭐️", description="Оплатите 1 звезду, чтобы сразу сделать спин",
                         payload=payload, provider_token="", currency="RUB", prices=prices)
        return

    # есть звезды — списываем и запускаем анимацию/результат
    spin_locks.add(chat_id)
    bot.answer_callback_query(call.id)
    # списать ставку сразу
    bal -= bet
    set_balance(user_id, bal)
    threading.Thread(target=_run_spin_animation, args=(call.message.chat.id, call.message.message_id, user_id, bet)).start()

def _run_spin_animation(chat_id, msg_id, user_id, bet):
    try:
        # создаём несколько кадров для эффекта кручения: каждая строка — случайна
        frames = [spin_once() for _ in range(5)]
        # последовательно показываем кадры
        for frame in frames[:-1]:
            bot.edit_message_text(matrix_to_text(frame) + "\n\n🎰 Крутится...", chat_id, msg_id)
            time.sleep(0.6)
        # финальный кадр — регенерируем для честности
        final = spin_once()
        result, mult = eval_middle_row(final)

        # если выигрыш — начисляем приз (ставка уже списана)
        if result != "lose":
            win = bet * mult
            add_balance(user_id, win)
        new_bal = get_balance(user_id)

        text = make_result_text(final, result, mult, new_bal)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=result_kb(), parse_mode="HTML")
    except Exception:
        try:
            # в случае ошибки возвращаем ставку
            add_balance(user_id, bet)
            bot.edit_message_text("Произошла ошибка во время спина. Ставка возвращена.", chat_id, msg_id)
        except:
            pass
    finally:
        spin_locks.discard(chat_id)

# ----- successful payment handler -----
@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    sp = message.successful_payment
    payload = sp.invoice_payload or ""
    user_id = message.from_user.id

    # запись простого лога платежа (локально) — можно расширить
    try:
        # payload examples: "buy:1" or "spin_pay"
        if payload.startswith("buy:"):
            # зачисляем указанное количество звёзд
            try:
                amount_stars = int(payload.split(":", 1)[1])
            except:
                amount_stars = 1
            add_balance(user_id, amount_stars)
            # обновить сообщение-заглушку, если было
            pending = pending_spin_invoice.pop(user_id, None)
            if pending and pending.get("type") == "buy_star":
                try:
                    bot.edit_message_text(f"✅ Оплата принята. На баланс начислено {amount_stars} ⭐️\n💰 Баланс: {get_balance(user_id)} ⭐️",
                                          pending["chat_id"], pending["msg_id"])
                except:
                    pass
            bot.send_message(user_id, f"✅ Оплата принята. На баланс начислено {amount_stars} ⭐️\n💰 Ваш баланс: {get_balance(user_id)} ⭐️")
            return

        if payload == "spin_pay":
            # пользователь оплатил спин напрямую — запускаем анимацию как если бы ставка списана
            pending = pending_spin_invoice.pop(user_id, None)
            # найдем chat_id/msg_id куда анимировать (сохраняли при инициировании)
            if pending:
                chat_id = pending["chat_id"]
                msg_id = pending["msg_id"]
            else:
                # fallback — отправляем новое сообщение для анимации
                sent = bot.send_message(user_id, "Оплата получена, запускаю спин...")
                chat_id = sent.chat.id
                msg_id = sent.message_id

            # spin: ставка уже оплачена внешне, поэтому НЕ списываем баланс, просто выполняем анимацию
            threading.Thread(target=_run_spin_animation_direct_payment, args=(chat_id, msg_id, user_id)).start()
            return

        # Other payloads: ignore or implement
        bot.send_message(user_id, "Оплата принята, спасибо.")
    except Exception:
        try:
            bot.send_message(user_id, "Произошла ошибка при обработке оплаты. Свяжитесь с поддержкой.")
        except:
            pass

def _run_spin_animation_direct_payment(chat_id, msg_id, user_id):
    try:
        frames = [spin_once() for _ in range(5)]
        for frame in frames[:-1]:
            bot.edit_message_text(matrix_to_text(frame) + "\n\n🎰 Крутится...", chat_id, msg_id)
            time.sleep(0.6)
        final = spin_once()
        result, mult = eval_middle_row(final)

        # выигрыш: начисляем на баланс (оплата была внешней)
        if result != "lose":
            win = 1 * mult
            add_balance(user_id, win)

        new_bal = get_balance(user_id)
        text = make_result_text(final, result, mult, new_bal)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=result_kb(), parse_mode="HTML")
    except Exception:
        try:
            bot.edit_message_text("Произошла ошибка при выполнении спина. Свяжитесь с поддержкой.", chat_id, msg_id)
        except:
            pass

if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Polling stopped:", e)
