import os
import random
import time
import json
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

# ====== Настройки ======
TOKEN = os.getenv("STAR")  # токен бота
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "")  # токен платежного провайдера (для реальных оплат)
SPIN_PRICE_AMOUNT = int(os.getenv("SPIN_PRICE_AMOUNT", "100"))  # минимальные единицы валюты (например 100 = 1.00 RUB)
CURRENCY = os.getenv("CURRENCY", "RUB")

if not TOKEN:
    raise SystemExit("Требуется токен бота в переменной окружения STAR")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ====== Файлы и состояние ======
BALANCE_FILE = "balances.json"
spin_locks = set()  # чатовые локи для предотвращения параллельных спинов
pending_spin_invoice = {}  # user_id -> {"chat_id": int, "msg_id": int}

# ====== Символы и шансы ======
SYMBOLS = [
    ("🍒", 25),
    ("🍋", 25),
    ("🍉", 20),
    ("⭐", 15),
    ("7️⃣", 5),
]

# ====== Баланс: загрузка/сохранение ======
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
    balances[str(user_id)] = get_balance(user_id) + int(delta)
    save_balances(balances)

# ====== Рулетка: случайный выбор и оценка ======
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

# ====== Клавиатуры (вертикальные) ======
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

def profile_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

def result_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔄 Сыграть ещё раз", callback_data="spin"))
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

# ====== Хэндлеры: старт и навигация ======
try:
    bot.remove_webhook()
except Exception:
    pass

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
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "play")
def play(call):
    bot.edit_message_text(
        "🎰 <b>Раздел рулетка</b>\n\n"
        "Добро пожаловать в фруктовую рулетку!\n"
        "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
        "💡 <b>Правила игры:</b>\n"
        "• 3 одинаковых фрукта → выигрыш ×2\n"
        "• 3 звезды ⭐ → выигрыш ×3\n"
        "• 3 семёрки 7️⃣ → джекпот ×5\n"
        "• Любая неполная комбинация → выигрыш отсутствует",
        call.message.chat.id, call.message.message_id, reply_markup=roulette_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    bot.edit_message_text(
        f"👤 <b>Профиль</b>\n\n"
        f"🆔 <b>Ваш ID:</b> {uid}\n"
        f"💰 <b>Ваш текущий баланс:</b> {bal} ⭐️\n\n"
        f"Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
        f"Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰",
        call.message.chat.id, call.message.message_id, reply_markup=profile_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back(call):
    # Возвращаем на главный экран, тот же текст что в /start
    start(call.message)
    bot.answer_callback_query(call.id)

# ====== SPIN: отправка нативного инвойса ======
@bot.callback_query_handler(func=lambda call: call.data == "spin")
def spin_invoice_handler(call):
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if chat_id in spin_locks:
        bot.answer_callback_query(call.id, "Спин уже выполняется. Подождите...", show_alert=False)
        return

    # Заглушка перед инвойсом (визуальный эффект)
    sent = bot.send_message(chat_id, "🎰 Подготовка барабанов...\n💳 Ожидание оплаты…")
    pending_spin_invoice[user_id] = {"chat_id": sent.chat.id, "msg_id": sent.message_id}

    # Формируем инвойс: заголовок/описание/метка цены как в примере
    prices = [LabeledPrice(label="★1", amount=SPIN_PRICE_AMOUNT)]
    payload = f"spin:{user_id}"
    bot.send_invoice(
        chat_id=chat_id,
        title="Покупка спинов",
        description="Оплата за слот машину",
        payload=payload,
        provider_token=PROVIDER_TOKEN,  # для тестов можно оставить пустым, реальные платежи не пройдут без провайдера
        currency=CURRENCY,
        prices=prices
    )
    bot.answer_callback_query(call.id)

# ====== Обработка успешной оплаты и запуск анимации ======
@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    sp = message.successful_payment
    payload = (sp.invoice_payload or "")
    user_id = message.from_user.id

    # Если payload - не наш спин, просто уведомляем
    if not payload.startswith("spin:"):
        bot.send_message(user_id, "✅ Оплата принята. Спасибо.")
        return

    # Найти заглушку для анимации
    pending = pending_spin_invoice.pop(user_id, None)
    if pending:
        chat_id = pending["chat_id"]
        msg_id = pending["msg_id"]
    else:
        sent = bot.send_message(user_id, "✅ Оплата получена. Запускаю спин...")
        chat_id = sent.chat.id
        msg_id = sent.message_id

    # Запускаем анимацию в отдельном потоке
    threading.Thread(target=_run_spin_animation_after_payment, args=(chat_id, msg_id, user_id)).start()

def _run_spin_animation_after_payment(chat_id, msg_id, user_id):
    try:
        spin_locks.add(chat_id)
        # Кадры кручения
        frames = [spin_once() for _ in range(4)]
        for frame in frames[:-1]:
            bot.edit_message_text(matrix_to_text(frame) + "\n\n🎰 Крутится...", chat_id, msg_id)
            time.sleep(0.6)
        # Финал
        final = spin_once()
        result, mult = eval_middle_row(final)

        # Начисляем выигрыш (оплата спина была внешней через Telegram)
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
    finally:
        spin_locks.discard(chat_id)

# ====== Повторный спин через кнопку "Сыграть ещё раз" ======
# Кнопка просто вызывает callback "spin" и весь цикл повторится (инвойс -> оплата -> анимация)

# ====== Запуск бота ======
if __name__ == "__main__":
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Polling stopped:", e)
