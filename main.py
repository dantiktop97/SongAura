#!/usr/bin/env python3
import os
import random
import time
import sqlite3
import threading
import traceback
from typing import List, Tuple, Optional

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice

# ====== Настройки и секреты из окружения ======
TOKEN = os.getenv("STAR") or os.getenv("BOT_TOKEN") or ""
DB_PATH = os.getenv("DB_PATH", "stars.db")
SPIN_COST_STARS = int(os.getenv("SPIN_COST_STARS", "1"))
# Провайдер оставляем пустым для поведения "как у друга"
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "").strip()
SPIN_PRICE_AMOUNT = int(os.getenv("SPIN_PRICE_AMOUNT", "100"))  # для реальной оплаты (минимальные ед.)
CURRENCY = os.getenv("CURRENCY", "RUB")

# Один админ через ADMIN_ID
_admin_id_raw = os.getenv("ADMIN_ID", "").strip()
try:
    ADMIN_IDS: List[int] = [int(_admin_id_raw)] if _admin_id_raw else []
except ValueError:
    ADMIN_IDS = []

if not TOKEN:
    raise SystemExit("Требуется токен бота в переменной окружения STAR или BOT_TOKEN")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ====== Состояния ======
spin_locks = set()                   # chat_id блокировки
pending_actions = {}                 # user_id -> action
# Когда используется нативный инвойс, сохраняем сообщение инвойса для редактирования
pending_spin_invoice = {}            # user_id -> {"chat_id": int, "msg_id": int}

# ====== DB (sqlite) ======
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS balances (
        user_id INTEGER PRIMARY KEY,
        stars INTEGER NOT NULL
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS star_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        change INTEGER NOT NULL,
        reason TEXT,
        ts INTEGER NOT NULL,
        ext_charge_id TEXT
    );
    """)
    conn.commit()
    conn.close()

def get_balance(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT stars FROM balances WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0]) if row else 0

def set_balance(user_id: int, stars: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO balances(user_id, stars) VALUES(?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET stars=excluded.stars;",
        (user_id, int(stars))
    )
    conn.commit()
    conn.close()

def change_balance(user_id: int, delta: int, reason: str = "", ext_charge_id: Optional[str] = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT stars FROM balances WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    prev = int(row[0]) if row else 0
    new = prev + int(delta)
    if new < 0:
        conn.close()
        raise ValueError("Insufficient balance")
    cur.execute(
        "INSERT INTO balances(user_id, stars) VALUES(?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET stars=excluded.stars;",
        (user_id, new)
    )
    cur.execute(
        "INSERT INTO star_logs(user_id, change, reason, ts, ext_charge_id) VALUES(?, ?, ?, ?, ?);",
        (user_id, int(delta), reason, int(time.time()), ext_charge_id)
    )
    conn.commit()
    conn.close()
    return new

# ====== Рулетка ======
SYMBOLS: List[Tuple[str, int]] = [
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
    kb.add(InlineKeyboardButton(f"🎟️ СПИН ({SPIN_COST_STARS} ⭐️)", callback_data="spin"))
    kb.add(InlineKeyboardButton("👤 ПРОФИЛЬ", callback_data="profile"))
    if ADMIN_IDS:
        kb.add(InlineKeyboardButton("🔧 Админ", callback_data="admin"))
    return kb

def roulette_kb():
    kb = InlineKeyboardMarkup()
    # при отсутствии PROVIDER_TOKEN кнопка будет открывать наш локальный "инвойс"
    kb.add(InlineKeyboardButton(f"🎟️ СПИН ({SPIN_COST_STARS} ⭐️)", callback_data="spin"))
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

def admin_kb():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("➕ Выдать звёзды", callback_data="admin_give"))
    kb.add(InlineKeyboardButton("📋 Логи (последние 10)", callback_data="admin_logs"))
    kb.add(InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"))
    return kb

# ====== Хэндлеры ======
@bot.message_handler(commands=['start'])
def handle_start(message):
    name = message.from_user.first_name or "игрок"
    text = (
        f"✨ Привет, <b>{name}</b>! Добро пожаловать в <b>StarryCasino</b>.\n\n"
        f"Нажми <b>ИГРАТЬ</b>, чтобы открыть рулетку и потратить {SPIN_COST_STARS} ⭐️ на спин."
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu_kb())

@bot.callback_query_handler(func=lambda c: c.data == "play")
def cb_play(call):
    bot.edit_message_text(
        "🎰 <b>Раздел рулетка</b>\n\n"
        "Испытай свою удачу: собери одинаковые символы в средней строке.\n\n"
        "💡 Правила:\n"
        "• 3 одинаковых фрукта → ×2\n"
        "• 3 звезды ⭐ → ×3\n"
        "• 3 семёрки 7️⃣ → джекпот ×5",
        call.message.chat.id, call.message.message_id, reply_markup=roulette_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "profile")
def cb_profile(call):
    uid = call.from_user.id
    bal = get_balance(uid)
    bot.edit_message_text(
        f"👤 <b>Профиль</b>\n\n🆔 <b>{uid}</b>\n💰 <b>Баланс:</b> {bal} ⭐️",
        call.message.chat.id, call.message.message_id, reply_markup=profile_kb(), parse_mode="HTML"
    )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "back_to_main")
def cb_back(call):
    handle_start(call.message)
    bot.answer_callback_query(call.id)

# ====== Админка ======
@bot.callback_query_handler(func=lambda c: c.data == "admin")
def cb_admin(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
        return
    bot.edit_message_text("🔧 Админ-панель", call.message.chat.id, call.message.message_id, reply_markup=admin_kb())
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_give")
def cb_admin_give(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
        return
    bot.send_message(call.message.chat.id, "Отправь в чате: <user_id> <количество_звёзд>\nНапример: 123456789 5")
    pending_actions[call.from_user.id] = "await_admin_give"
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data == "admin_logs")
def cb_admin_logs(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "Нет прав", show_alert=True)
        return
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, user_id, change, reason, ts, ext_charge_id FROM star_logs ORDER BY id DESC LIMIT 10")
    rows = cur.fetchall()
    conn.close()
    lines = []
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(r[4]))
        lines.append(f"{r[0]} | user:{r[1]} | change:{r[2]} | {r[3]} | {ts} | charge:{r[5] or '-'}")
    text = "Последние логи:\n" + ("\n".join(lines) if lines else "Нет записей")
    bot.send_message(call.message.chat.id, text)
    bot.answer_callback_query(call.id)

# ====== SPIN: поведение с провайдером и без ======
@bot.callback_query_handler(func=lambda c: c.data == "spin")
def cb_spin(call):
    uid = call.from_user.id
    chat_id = call.message.chat.id

    if chat_id in spin_locks:
        bot.answer_callback_query(call.id, "Спин уже выполняется в этом чате. Подождите.", show_alert=False)
        return

    # Если настроен провайдер — отправляем реальный инвойс
    if PROVIDER_TOKEN:
        prices = [LabeledPrice(label="★1", amount=SPIN_PRICE_AMOUNT)]
        payload = f"spin:{uid}"
        try:
            invoice_msg = bot.send_invoice(
                chat_id=chat_id,
                title="Покупка спина",
                description="Оплата за один спин",
                invoice_payload=payload,
                provider_token=PROVIDER_TOKEN,
                currency=CURRENCY,
                prices=prices
            )
        except TypeError:
            invoice_msg = bot.send_invoice(
                chat_id=chat_id,
                title="Покупка спина",
                description="Оплата за один спин",
                payload=payload,
                provider_token=PROVIDER_TOKEN,
                currency=CURRENCY,
                prices=prices
            )
        try:
            if invoice_msg is not None:
                pending_spin_invoice[uid] = {"chat_id": invoice_msg.chat.id, "msg_id": invoice_msg.message_id}
            else:
                pending_spin_invoice[uid] = {"chat_id": chat_id, "msg_id": call.message.message_id}
        except Exception:
            pending_spin_invoice[uid] = {"chat_id": chat_id, "msg_id": call.message.message_id}

        bot.answer_callback_query(call.id)
        return

    # Если провайдера нет — показываем собственный "инвойс" и кнопку оплатить
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton(f"Оплатить {SPIN_COST_STARS} ⭐️", callback_data=f"fake_pay_spin:{uid}"))
    kb.add(InlineKeyboardButton("Отмена", callback_data="fake_pay_cancel"))
    try:
        bot.edit_message_text(
            f"💳 Оплата спина\n\nСтоимость: {SPIN_COST_STARS} ⭐️\nНажмите Оплатить, чтобы подтвердить списание {SPIN_COST_STARS} ⭐️ со своего баланса.",
            chat_id, call.message.message_id, reply_markup=kb
        )
    except Exception:
        bot.send_message(chat_id,
            f"💳 Оплата спина\n\nСтоимость: {SPIN_COST_STARS} ⭐️\nНажмите Оплатить, чтобы подтвердить списание {SPIN_COST_STARS} ⭐️ со своего баланса.",
            reply_markup=kb
        )
    bot.answer_callback_query(call.id)

@bot.callback_query_handler(func=lambda c: c.data and c.data.startswith("fake_pay_spin:"))
def cb_fake_pay_spin_confirm(call):
    # callback_data = fake_pay_spin:<uid_in_payload>
    parts = call.data.split(":", 1)
    try:
        target_uid = int(parts[1])
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка данных платежа.", show_alert=True)
        return

    user_id = call.from_user.id
    if user_id != target_uid:
        bot.answer_callback_query(call.id, "Платёж можно подтвердить только со своего аккаунта.", show_alert=True)
        return

    bal = get_balance(user_id)
    if bal < SPIN_COST_STARS:
        bot.answer_callback_query(call.id, "У вас недостаточно звёзд для оплаты.", show_alert=True)
        # показать предложение обратиться к админу можно тут
        return

    # генерируем внешний charge id вида fake-<timestamp>-<uid> для логов
    ext_charge_id = f"fake-{int(time.time())}-{user_id}"

    try:
        new_bal = change_balance(user_id, -SPIN_COST_STARS, reason="fake_pay_spin", ext_charge_id=ext_charge_id)
    except Exception:
        bot.answer_callback_query(call.id, "Ошибка при списании. Попробуйте позже.", show_alert=True)
        return

    # Сохраним место сообщения для спина (используем текущее сообщение)
    try:
        pending_spin_invoice[user_id] = {"chat_id": call.message.chat.id, "msg_id": call.message.message_id}
    except Exception:
        pending_spin_invoice[user_id] = {"chat_id": call.message.chat.id, "msg_id": call.message.message_id}

    bot.answer_callback_query(call.id, f"Оплата {SPIN_COST_STARS} ⭐️ подтверждена. Запускаю спин.")
    # короткая заметка-чек в чате
    bot.send_message(user_id, f"✅ Оплата принята. ChargeID: {ext_charge_id}. Списано {SPIN_COST_STARS} ⭐️.")

    # Запускаем анимацию спина
    thread = threading.Thread(target=_run_spin_animation_after_payment, args=(call.message.chat.id, call.message.message_id, user_id))
    thread.start()

@bot.callback_query_handler(func=lambda c: c.data == "fake_pay_cancel")
def cb_fake_pay_cancel(call):
    try:
        # вернуть в меню рулетки
        bot.edit_message_text("Отменено. Возвращаю в меню.", call.message.chat.id, call.message.message_id, reply_markup=main_menu_kb())
    except Exception:
        pass
    bot.answer_callback_query(call.id, "Отменено")

# ====== PreCheckout и successful_payment для реальных провайдеров ======
@bot.pre_checkout_query_handler(func=lambda query: True)
def process_pre_checkout_query(pre_checkout_q):
    try:
        bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)
    except Exception:
        pass

@bot.message_handler(content_types=['successful_payment'])
def handle_successful_payment(message):
    sp = message.successful_payment
    payload = getattr(sp, "invoice_payload", None) or getattr(sp, "payload", None) or ""
    user_id = message.from_user.id
    # логируем внешний charge id и зачисляем звезду
    ext_id = getattr(sp, "telegram_payment_charge_id", None)
    # если payload spin: — запуск спина
    # зачисляем 1 звезду на баланс (эквивалент оплаты)
    try:
        change_balance(user_id, 1, reason="real_payment_credit_star", ext_charge_id=ext_id)
    except Exception:
        pass

    if payload.startswith("spin:"):
        pending = pending_spin_invoice.pop(user_id, None)
        if pending:
            chat_id = pending["chat_id"]; msg_id = pending["msg_id"]
        else:
            sent = bot.send_message(user_id, "✅ Оплата получена. Запускаю спин...")
            chat_id = sent.chat.id; msg_id = sent.message_id
        threading.Thread(target=_run_spin_animation_after_payment, args=(chat_id, msg_id, user_id)).start()
    else:
        bot.send_message(user_id, "✅ Оплата получена и 1 ★ зачислена на баланс.")

# ====== Запуск спина и начисление выигрыша ======
def _run_spin_animation_after_payment(chat_id: int, msg_id: int, user_id: int):
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
        win = mult if result != "lose" else 0
        if win:
            try:
                change_balance(user_id, win, reason="spin_win")
            except Exception:
                pass

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

# ====== Обработка текстовых сообщений (админ/баланс) ======
@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_text(message):
    uid = message.from_user.id
    txt = (message.text or "").strip()

    if pending_actions.get(uid) == "await_admin_give":
        parts = txt.split()
        if len(parts) != 2:
            bot.reply_to(message, "Неправильный формат. Отправь: <user_id> <количество_звёзд>")
            return
        try:
            target = int(parts[0])
            amount = int(parts[1])
        except ValueError:
            bot.reply_to(message, "ID и количество должны быть числами.")
            pending_actions.pop(uid, None)
            return
        try:
            new_bal = change_balance(target, amount, reason=f"admin_give_by_{uid}")
        except Exception as e:
            bot.reply_to(message, f"Ошибка при выдаче: {e}")
            pending_actions.pop(uid, None)
            return
        bot.reply_to(message, f"Выдано {amount} ⭐️ пользователю {target}. Новый баланс: {new_bal} ⭐️")
        try:
            bot.send_message(target, f"Вам зачислено {amount} ⭐️. Новый баланс: {new_bal} ⭐️")
        except Exception:
            pass
        pending_actions.pop(uid, None)
        return

    if txt.startswith("/balance"):
        bal = get_balance(uid)
        bot.reply_to(message, f"💰 Ваш баланс: {bal} ⭐️")
        return

    if txt.startswith("/give") and uid in ADMIN_IDS:
        parts = txt.split()
        if len(parts) != 3:
            bot.reply_to(message, "Использование: /give <user_id> <amount>")
            return
        try:
            target = int(parts[1])
            amount = int(parts[2])
        except ValueError:
            bot.reply_to(message, "ID и количество должны быть числами.")
            return
        try:
            new_bal = change_balance(target, amount, reason=f"admin_give_by_{uid}")
        except Exception as e:
            bot.reply_to(message, f"Ошибка при выдаче: {e}")
            return
        bot.reply_to(message, f"Выдано {amount} ⭐️ пользователю {target}. Новый баланс: {new_bal} ⭐️")
        try:
            bot.send_message(target, f"Вам зачислено {amount} ⭐️. Новый баланс: {new_bal} ⭐️")
        except Exception:
            pass
        return

# ====== Запуск ======
if __name__ == "__main__":
    init_db()
    try:
        print("Bot started")
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception as e:
        print("Polling stopped:", e)
        traceback.print_exc()
