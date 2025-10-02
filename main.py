#!/usr/bin/env python3
import os
import time
import random
import json
import threading
import traceback
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

# ====== Настройки ======
TOKEN = os.getenv("STAR")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "").strip()  # если пустой — локальная оплата звёздами
SPIN_PRICE_AMOUNT = int(os.getenv("SPIN_PRICE_AMOUNT", "100"))  # для инвойса в минимальных ед.
CURRENCY = os.getenv("CURRENCY", "RUB")

if not TOKEN:
    raise SystemExit("Требуется токен бота в переменной окружения STAR")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ====== Файлы и состояние ======
BALANCE_FILE = "balances.json"
PAYMENTS_FILE = "payments.json"  # лог реальных и фейковых charge_id чтобы предотвратить дубли
spin_locks = set()
pending_spin_invoice = {}  # user_id -> {"chat_id": int, "msg_id": int}

# ====== Утилиты для JSON хранения ======
def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# Балансы
def load_balances():
    return _load_json(BALANCE_FILE, {})

def save_balances(balances):
    _save_json(BALANCE_FILE, balances)

balances = load_balances()

def get_balance(user_id):
    return int(balances.get(str(user_id), 0))

def set_balance(user_id, value):
    balances[str(user_id)] = int(value)
    save_balances(balances)

def add_balance(user_id, delta):
    balances[str(user_id)] = get_balance(user_id) + int(delta)
    save_balances(balances)

# Логи платежей (телеграм charge id и фейки)
def load_payments():
    return _load_json(PAYMENTS_FILE, {})

def save_payments(payments):
    _save_json(PAYMENTS_FILE, payments)

payments = load_payments()  # key: charge_id -> info dict

def record_payment(charge_id, info):
    if not charge_id:
        return False
    if charge_id in payments:
        return False
    payments[charge_id] = info
    save_payments(payments)
    return True

# ====== Рулетка: символы и логика ======
SYMBOLS = [
    ("🍒", 25),
    ("🍋", 25),
    ("🍉", 20),
    ("⭐", 15),
    ("7️⃣", 5),
]

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
            f"💰 <b>Баланс:</b> {new_balance} ⭐️\n"
            f"Не расстраивайтесь — сыграйте ещё раз, удача рядом! ✨🎰"
        )
    else:
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"🎉 <b>Отлично!</b> Вы собрали: {' '.join(mid)}\n"
            f"✨ <b>Выигрыш:</b> ×{mult}\n"
            f"💰 <b>Баланс:</b> {new_balance} ⭐️\n"
            f"Не останавливайтесь — сыграйте ещё раз и ловите удачу! 🍀"
        )

# ====== Клавиатуры ======
def main_menu_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎰 ИГРАТЬ", callback_data="play"))
    kb.add(InlineKeyboardButton("🎟️ КУПИТЬ СПИН (1⭐)", callback_data="buy_spin"))
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))
    return kb

def roulette_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🎟️ КУПИТЬ СПИН (1⭐)", callback_data="buy_spin"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def profile_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def result_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="buy_spin"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

# ====== Хэндлеры старт/навигация ======
try:
    bot.remove_webhook()
except Exception:
    pass

@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name or "игрок"
    text = (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> — игра на виртуальные звёзды.\n\n"
        f"Нажми КУПИТЬ СПИН чтобы увидеть окно оплаты и получить 1⭐ для спина."
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "play")
def play(call):
    bot.edit_message_text(
        "🎰 <b>Раздел рулетка</b>\n\n"
        "Испытай свою удачу и купи спин за 1⭐.",
        call.message.chat.id, call.message.message_id, reply_markup=roulette_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    bot.edit_message_text(
        f"👤 <b>Профиль</b>\n\n🆔 <b>Ваш ID:</b> {uid}\n💰 <b>Ваш текущий баланс:</b> {bal} ⭐️",
        call.message.chat.id, call.message.message_id, reply_markup=profile_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back(call):
    start(call.message)
    bot.answer_callback_query(call.id)

# ====== BUY SPIN: когда нажали кнопку купить спин ======
def _make_unique_payload(prefix, user_id):
    return f"{prefix}:{user_id}:{int(time.time()*1000)}"

@bot.callback_query_handler(func=lambda call: call.data == "buy_spin")
def cb_buy_spin(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if chat_id in spin_locks:
        bot.answer_callback_query(call.id, "В этом чате уже выполняется спин. Подождите...", show_alert=False)
        return

    # если нет PROVIDER_TOKEN — показываем локальную "оплату звёздами" интерфейс
    if not PROVIDER_TOKEN:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(f"Оплатить 1 ⭐️", callback_data=f"fake_pay:{user_id}"))
        kb.add(InlineKeyboardButton("Отмена", callback_data="fake_cancel"))
        try:
            bot.edit_message_text(
                f"💳 Оплата спина\n\nСтоимость: 1 ⭐️\nНажмите Оплатить, чтобы подтвердить списание 1 ⭐️ со своего баланса.",
                chat_id, call.message.message_id, reply_markup=kb
            )
        except Exception:
            bot.send_message(chat_id,
                f"💳 Оплата спина\n\nСтоимость: 1 ⭐️\nНажмите Оплатить, чтобы подтвердить списание 1 ⭐️ со своего баланса.",
                reply_markup=kb
            )
        bot.answer_callback_query(call.id)
        return

    # Если PROVIDER_TOKEN задан — отправляем реальный инвойс (payload уникальный)
    payload = _make_unique_payload("spin", user_id)
    prices = [LabeledPrice(label="★1", amount=SPIN_PRICE_AMOUNT)]
    try:
        invoice_msg = bot.send_invoice(
            chat_id=chat_id,
            title="Покупка спина",
            description="Оплата за слот машина — 1 ★",
            invoice_payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency=CURRENCY,
            prices=prices
        )
    except TypeError:
        invoice_msg = bot.send_invoice(
            chat_id=chat_id,
            title="Покупка спина",
            description="Оплата за слот машина — 1 ★",
            payload=payload,
            provider_token=PROVIDER_TOKEN,
            currency=CURRENCY,
            prices=prices
        )

    # запоминаем куда нужно редактировать сообщение после successful_payment
    try:
        if invoice_msg is not None:
            pending_spin_invoice[user_id] = {"chat_id": invoice_msg.chat.id, "msg_id": invoice_msg.message_id}
        else:
            pending_spin_invoice[user_id] = {"chat_id": chat_id, "msg_id": call.message.message_id}
    except Exception:
        pending_spin_invoice[user_id] = {"chat_id": chat_id, "msg_id": call.message.message_id}

    bot.answer_callback_query(call.id, "Открылось окно оплаты")

# ====== Fake pay callbacks (режим без провайдера) ======
@bot.callback_query_handler(func=lambda call: call.data and call.data.startswith("fake_pay:"))
def cb_fake_pay(call):
    # data = fake_pay:<user_id_in_payload>
    parts = call.data.split(":", 1)
    try:
        target_uid = int(parts[1])
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка данных.", show_alert=True)
        return

    user_id = call.from_user.id
    if user_id != target_uid:
        bot.answer_callback_query(call.id, "Оплата может быть подтверждена только вашим аккаунтом.", show_alert=True)
        return

    bal = get_balance(user_id)
    if bal < 1:
        bot.answer_callback_query(call.id, "У вас недостаточно звёзд для оплаты.", show_alert=True)
        return

    # списываем 1 звезду и записываем fake charge id чтобы не допустить дублей
    fake_charge = f"fake-{user_id}-{int(time.time()*1000)}"
    success_recorded = record_payment(fake_charge, {
        "type": "fake",
        "user_id": user_id,
        "time": int(time.time())
    })
    if not success_recorded:
        bot.answer_callback_query(call.id, "Этот платёж уже обработан.", show_alert=True)
        return

    set_balance(user_id, bal - 1)
    try:
        pending_spin_invoice[user_id] = {"chat_id": call.message.chat.id, "msg_id": call.message.message_id}
    except Exception:
        pending_spin_invoice[user_id] = {"chat_id": call.message.chat.id, "msg_id": call.message.message_id}

    bot.answer_callback_query(call.id, f"Оплата 1 ⭐️ подтверждена (id {fake_charge}). Запускаю спин.")
    bot.send_message(user_id, f"✅ Оплата принята. ChargeID: {fake_charge}. Списано 1 ⭐️.")
    threading.Thread(target=_run_spin_animation_after_payment, args=(call.message.chat.id, call.message.message_id, user_id)).start()

@bot.callback_query_handler(func=lambda call: call.data == "fake_cancel")
def cb_fake_cancel(call):
    try:
        bot.edit_message_text("Оплата отменена. Возвращаю в меню.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb())
    except Exception:
        pass
    bot.answer_callback_query(call.id, "Отменено")

# ====== PreCheckout handler (для реальных провайдеров) ======
@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_q):
    try:
        bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)
    except Exception:
        pass

# ====== Successful payment handler ======
@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    sp = message.successful_payment
    if not sp:
        return
    payload = getattr(sp, "invoice_payload", None) or getattr(sp, "payload", None) or ""
    user_id = message.from_user.id
    ext_id = getattr(sp, "telegram_payment_charge_id", None)
    amount = getattr(sp, "total_amount", None) or getattr(sp, "invoice_total_amount", None) or 0
    currency = getattr(sp, "currency", None) or CURRENCY

    # Защита от двойной обработки: проверяем telegram_payment_charge_id
    if ext_id and ext_id in payments:
        try:
            message.reply("⚠️ Этот платёж уже обработан.")
        except Exception:
            pass
        return

    # Регистрируем платёж
    info = {
        "type": "real",
        "user_id": user_id,
        "time": int(time.time()),
        "amount": amount,
        "currency": currency
    }
    if ext_id:
        record_payment(ext_id, info)

    # Зачисляем 1 звезду (эквивалент покупки)
    try:
        add_balance(user_id, 1)
    except Exception:
        pass

    # Если payload — spin:... — запускаем спин-анимацию, редактируя сообщение инвойса если доступно
    if str(payload).startswith("spin:"):
        pending = pending_spin_invoice.pop(user_id, None)
        if pending:
            chat_id = pending["chat_id"]; msg_id = pending["msg_id"]
        else:
            sent = bot.send_message(user_id, "✅ Оплата получена. Запускаю спин...")
            chat_id = sent.chat.id; msg_id = sent.message_id
        threading.Thread(target=_run_spin_animation_after_payment, args=(chat_id, msg_id, user_id)).start()
    else:
        try:
            bot.send_message(user_id, "✅ Оплата получена. 1 ⭐️ зачислена на ваш баланс.")
        except Exception:
            pass

# ====== Запуск спина и начисление выигрыша ======
def _run_spin_animation_after_payment(chat_id, msg_id, user_id):
    try:
        spin_locks.add(chat_id)
        frames = [spin_once() for _ in range(4)]
        for frame in frames[:-1]:
            try:
                bot.edit_message_text(matrix_to_text(frame) + "\n\n🎰 Крутится...", chat_id, msg_id)
            except Exception:
                pass
            time.sleep(0.6)

        final = spin_once()
        result, mult = eval_middle_row(final)

        # Начисляем выигрыш (если выигрыш есть)
        if result != "lose":
            win = 1 * mult
            add_balance(user_id, win)

        new_bal = get_balance(user_id)
        text = make_result_text(final, result, mult, new_bal)
        try:
            bot.edit_message_text(text, chat_id, msg_id, reply_markup=result_kb(), parse_mode="HTML")
        except Exception:
            bot.send_message(chat_id, text, reply_markup=result_kb(), parse_mode="HTML")
    except Exception:
        try:
            bot.edit_message_text("Произошла ошибка при выполнении спина. Свяжитесь с поддержкой.", chat_id, msg_id)
        except Exception:
            pass
        traceback.print_exc()
    finally:
        spin_locks.discard(chat_id)

# ====== Запуск бота ======
if __name__ == "__main__":
    try:
        print("Bot started")
        bot.infinity_polling()
    except KeyboardInterrupt:
        pass
