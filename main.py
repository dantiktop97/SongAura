# main.py
import os
import random
import time
import json
import threading
import telebot
from flask import Flask, request, abort
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice, PreCheckoutQuery

# ----------------- Настройки -----------------
TOKEN = os.getenv("STAR")   # секрет STAR (токен бота)
if not TOKEN:
    raise RuntimeError("Переменная окружения STAR не установлена!")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

BALANCE_FILE = "balances.json"
balances_lock = threading.Lock()

# ----------------- Символы и вероятности -----------------
SYMBOLS = [
    ("🍒", 25),
    ("🍋", 25),
    ("🍉", 20),
    ("⭐", 15),
    ("7️⃣", 5),
]

# ----------------- Балансы (файл) -----------------
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
        print("Ошибка при сохранении балансов:", e)

balances = load_balances()

def get_balance(user_id):
    with balances_lock:
        return int(balances.get(str(user_id), 1000))  # дефолт 1000

def set_balance(user_id, value):
    with balances_lock:
        balances[str(user_id)] = int(value)
        save_balances(balances)

# ----------------- Вспомогательное (слот) -----------------
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
            f"❌ <b>Увы… комбинация не совпала.</b>\n\n"
            f"💰 <b>Баланс:</b> {new_balance} монет\n\n"
            f"Не расстраивайтесь — сыграйте ещё раз, удача рядом! ✨🎰"
        )
    else:
        return (
            f"{matrix_to_text(matrix)}\n\n"
            f"🎉 <b>Отлично!</b> Вы собрали: {' '.join(mid)}\n\n"
            f"✨ <b>Выигрыш:</b> ×{mult}\n"
            f"💰 <b>Баланс:</b> {new_balance} монет\n\n"
            f"Не останавливайтесь — сыграйте ещё раз и ловите удачу! 🍀"
        )

# ----------------- Клавиатуры -----------------
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

def profile_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_main"))
    return kb

# ----------------- Тексты (весь текст сохранён) -----------------
def welcome_text(name):
    return (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b> — здесь выигрыши не ждут, они случаются! ✨\n\n"
        f"Что тебя ждёт:\n\n"
        f"🎁 <b>Мгновенные бонусы</b> — прямо на аккаунт, без задержек\n"
        f"🎰 <b>Розыгрыши и игры</b> — каждый шанс на выигрыш реально захватывающий\n"
        f"📲 <b>Удобный формат</b> — всё работает прямо в Telegram: быстро, просто, без лишнего\n\n"
        f"Здесь нет лишней суеты — только азарт, стиль и удовольствие от игры.\n"
        f"Запускаем удачу! 🌟"
    )

roulette_long_text = (
    "🎰 <b>Раздел рулетка</b>\n\n"
    "Добро пожаловать в фруктовую рулетку!\n"
    "Испытай свою удачу и попробуй собрать одинаковые символы в средней строке.\n\n"
    "💡 <b>Правила игры:</b>\n"
    "• 3 одинаковых фрукта → выигрыш ×2\n"
    "• 3 звезды ⭐ → выигрыш ×3\n"
    "• 3 семёрки 7️⃣ → джекпот ×5\n"
    "• Любая неполная комбинация → выигрыш отсутствует\n\n"
    "Цена одного спина — <b>1⭐</b> (Telegram Stars).\n"
    "После оплаты вы увидите анимацию барабанов и результат. Удачи! 🍀"
)

profile_long_text = (
    "👤 <b>Профиль</b>\n\n"
    "Здесь отображается ваша основная информация и баланс.\n\n"
)

# ----------------- Хэндлеры бота -----------------
@bot.message_handler(commands=['start'])
def start(message):
    name = message.from_user.first_name or "игрок"
    bot.send_message(message.chat.id, welcome_text(name), reply_markup=main_menu_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "play")
def play(call):
    bot.edit_message_text(
        roulette_long_text,
        call.message.chat.id, call.message.message_id,
        reply_markup=roulette_kb(), parse_mode="HTML"
    )

# Оплата звездами (Stars)
@bot.callback_query_handler(func=lambda call: call.data == "spin_pay")
def spin_pay(call):
    prices = [LabeledPrice(label="Один спин 🎰", amount=1)]  # 1 Star
    try:
        bot.send_invoice(
            call.message.chat.id,
            title="🎰 Спин",
            description="Крути рулетку за 1⭐",
            invoice_payload="spin_slot",
            provider_token="",  # для Stars обычно пусто/поставляется BotFather (используй тестовый режим)
            currency="XTR",
            prices=prices
        )
    except Exception as e:
        bot.answer_callback_query(call.id, "Ошибка при создании счёта: " + str(e), show_alert=True)
        return
    bot.answer_callback_query(call.id)

@bot.pre_checkout_query_handler(func=lambda query: True)
def checkout(pre_checkout_query: PreCheckoutQuery):
    # Подтверждаем предоплату
    bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@bot.message_handler(content_types=['successful_payment'])
def got_payment(message):
    # Приход успешного платежа от Telegram
    sp = message.successful_payment
    if not sp:
        return
    if sp.invoice_payload != "spin_slot":
        return
    user_id = message.from_user.id
    # Запускаем спин в отдельном потоке, чтобы не блокировать webhook
    threading.Thread(target=do_spin, args=(message.chat.id, user_id)).start()

def do_spin(chat_id, user_id):
    # Создаём сообщение-анимацию
    try:
        msg = bot.send_message(chat_id, "…БАРАБАНЫ КРУТЯТСЯ… 🎰")
    except Exception:
        return

    # Анимация (несколько кадров)
    frames = [spin_once() for _ in range(3)]
    try:
        for frame in frames:
            bot.edit_message_text(matrix_to_text(frame), chat_id, msg.message_id)
            time.sleep(0.6)
    except Exception:
        pass

    # Финальный результат
    final = spin_once()
    result, mult = eval_middle_row(final)

    # Обновляем баланс: списываем 1⭐ и добавляем выигрыш (виртуальные монеты)
    bet = 1
    bal = get_balance(user_id)
    bal -= bet
    if result != "lose":
        win = bet * mult
        bal += win
    set_balance(user_id, bal)

    text = make_result_text(final, result, mult, bal)
    try:
        bot.edit_message_text(text, chat_id, msg.message_id, reply_markup=result_kb(), parse_mode="HTML")
    except Exception:
        # если не удалось отредактировать — отправляем новое сообщение
        bot.send_message(chat_id, text, reply_markup=result_kb(), parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: call.data == "profile")
def profile(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    bot.edit_message_text(
        profile_long_text +
        f"\n🆔 <b>Ваш ID:</b> {uid}\n"
        f"💰 <b>Ваш текущий баланс:</b> {bal}⭐️\n\n"
        f"Здесь вы можете отслеживать состояние аккаунта и баланс.\n"
        f"Возвращайтесь в игры, проверяйте результаты и ловите удачу! ✨🎰",
        call.message.chat.id, call.message.message_id, reply_markup=profile_kb(), parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back(call):
    name = call.from_user.first_name or "игрок"
    bot.edit_message_text(welcome_text(name), call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb(), parse_mode="HTML")

# ----------------- Flask webhook endpoint -----------------
@app.route("/" + TOKEN, methods=["POST"])
def webhook():
    if request.headers.get("content-type") != "application/json":
        abort(403)
    json_string = request.stream.read().decode("utf-8")
    try:
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
    except Exception as e:
        print("Ошибка обработки апдейта:", e)
    return "OK", 200

@app.route("/")
def index():
    return "StarryCasino бот работает", 200

# ----------------- Запуск: установка webhook и старт Flask -----------------
if __name__ == "__main__":
    # Попытка автоматически установить webhook для Render
    RENDER_HOST = os.getenv("RENDER_EXTERNAL_HOSTNAME")
    PORT = int(os.getenv("PORT", "10000"))

    if RENDER_HOST:
        webhook_url = f"https://{RENDER_HOST}/{TOKEN}"
        try:
            bot.remove_webhook()
        except Exception:
            pass
        try:
            ok = bot.set_webhook(url=webhook_url)
            print("Webhook установлен:", webhook_url, ok)
        except Exception as e:
            print("Не удалось установить webhook автоматически:", e)
            print("Установите webhook вручную через BotFather/Telegram API.")
    else:
        print("RENDER_EXTERNAL_HOSTNAME не задан — пропущена автоматическая установка webhook.")
        print("При использовании Render установите переменную окружения RENDER_EXTERNAL_HOSTNAME.")

    # Запускаем Flask (Render ожидает привязки к PORT)
    app.run(host="0.0.0.0", port=PORT)
