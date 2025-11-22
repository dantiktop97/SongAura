import os
import re
import sqlite3
import threading
import time
import json
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
SUB_CHANNEL = os.getenv("SUB_CHANNEL", "@vzref2")
DB_PATH = os.getenv("DB_PATH", "data.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_STATUSES = ("administrator", "creator")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

_local_memory = {}

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS required_subs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                channel TEXT NOT NULL,
                expires TEXT,
                added_by INTEGER,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                messages_count INTEGER DEFAULT 0,
                last_seen TEXT,
                UNIQUE(user_id, chat_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                admin_id INTEGER,
                reason TEXT,
                created_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                expires_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                action_type TEXT,
                details TEXT,
                created_at TEXT
            )
        """)
        conn.commit()

def get_iso_now():
    return datetime.utcnow().isoformat()

def parse_iso_datetime(iso_str):
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None

def format_readable_date(iso_str):
    dt = parse_iso_datetime(iso_str)
    return dt.strftime("%d.%m.%Y %H:%M UTC") if dt else "Бессрочно"

def sanitize_text(text):
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def check_admin_rights(chat_id, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ADMIN_STATUSES
    except Exception:
        return False

def log_system_action(chat_id, user_id, action, details=""):
    try:
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO system_logs (chat_id, user_id, action_type, details, created_at) VALUES (?, ?, ?, ?, ?)",
                (chat_id, user_id, action, details, get_iso_now())
            )
            conn.commit()
    except Exception as e:
        print(f"Logging Error: {e}")

def update_user_activity(user, chat_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.execute("SELECT id FROM members WHERE user_id = ? AND chat_id = ?", (user.id, chat_id))
            exists = cursor.fetchone()
            if exists:
                conn.execute("""
                    UPDATE members SET 
                    username = ?, first_name = ?, last_name = ?, messages_count = messages_count + 1, last_seen = ? 
                    WHERE id = ?
                """, (user.username, user.first_name, user.last_name, get_iso_now(), exists['id']))
            else:
                conn.execute("""
                    INSERT INTO members (user_id, chat_id, username, first_name, last_name, messages_count, last_seen)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                """, (user.id, chat_id, user.username, user.first_name, user.last_name, get_iso_now()))
            conn.commit()
    except Exception:
        pass

def parse_time_string(time_str):
    regex = re.match(r"(\d+)([smhd])", time_str.lower())
    if not regex: return None
    value, unit = int(regex.group(1)), regex.group(2)
    if unit == 's': return timedelta(seconds=value)
    if unit == 'm': return timedelta(minutes=value)
    if unit == 'h': return timedelta(hours=value)
    if unit == 'd': return timedelta(days=value)
    return None

def background_unmute_worker():
    while True:
        try:
            with get_db_connection() as conn:
                expired_mutes = conn.execute("SELECT id, chat_id, user_id, expires_at FROM mutes WHERE expires_at IS NOT NULL").fetchall()
                current_time = datetime.utcnow()
                
                for mute in expired_mutes:
                    expiry = parse_iso_datetime(mute['expires_at'])
                    if expiry and expiry <= current_time:
                        try:
                            bot.restrict_chat_member(
                                mute['chat_id'], 
                                mute['user_id'], 
                                can_send_messages=True,
                                can_send_media_messages=True,
                                can_send_other_messages=True,
                                can_add_web_page_previews=True
                            )
                            bot.send_message(mute['chat_id'], f"🔊 <b>Время истекло.</b> Пользователь <a href='tg://user?id={mute['user_id']}'>{mute['user_id']}</a> размучен.")
                        except Exception as e:
                            print(f"Failed to unmute {mute['user_id']}: {e}")
                        finally:
                            conn.execute("DELETE FROM mutes WHERE id = ?", (mute['id'],))
                conn.commit()
        except Exception as e:
            print(f"Worker Error: {e}")
        time.sleep(20)

def generate_main_admin_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
        InlineKeyboardButton("📡 Рассылка", callback_data="adm_broadcast")
    )
    markup.row(
        InlineKeyboardButton("📋 Логи системы", callback_data="adm_logs"),
        InlineKeyboardButton("🛡 Управление", callback_data="adm_manage")
    )
    markup.add(InlineKeyboardButton("❌ Закрыть панель", callback_data="close_panel"))
    return markup

def generate_management_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("➕ Добавить подписку", callback_data="mng_add_sub"))
    markup.add(InlineKeyboardButton("➖ Удалить подписку", callback_data="mng_del_sub"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="adm_main_menu"))
    return markup

def generate_back_button(callback_data="adm_main_menu"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Вернуться назад", callback_data=callback_data))
    return markup

def generate_subscription_keyboard(missing_channels):
    markup = InlineKeyboardMarkup()
    for channel in missing_channels:
        clean_name = channel.replace("@", "")
        markup.add(InlineKeyboardButton(f"👉 Подписаться на {channel}", url=f"https://t.me/{clean_name}"))
    markup.add(InlineKeyboardButton("✅ Я подписался", callback_data="verify_subscription"))
    return markup

@bot.message_handler(commands=['start'])
def command_start_handler(message):
    if message.chat.type != 'private':
        return 
    
    if message.from_user.id == ADMIN_ID:
        bot.send_message(
            message.chat.id,
            "<b>🎛 Панель Администратора</b>\nДобро пожаловать в центр управления ботом.",
            reply_markup=generate_main_admin_keyboard()
        )
    else:
        welcome_msg = (
            f"👋 <b>Приветствую, {sanitize_text(message.from_user.first_name)}!</b>\n\n"
            "Я — автоматизированная система модерации чатов.\n"
            "Мои возможности:\n"
            "• 🛡 Фильтрация спама и проверка подписок\n"
            "• 👮 Система предупреждений и банов\n"
            "• 📊 Сбор статистики активности\n\n"
            "Для начала работы добавьте меня в свой чат и назначьте администратором."
        )
        add_kb = InlineKeyboardMarkup()
        add_kb.add(InlineKeyboardButton("➕ Добавить в группу", url=f"https://t.me/{bot.get_me().username}?startgroup=true"))
        bot.send_message(message.chat.id, welcome_msg, reply_markup=add_kb)

@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    if data == "verify_subscription":
        required_channels = get_required_channels_for_chat(chat_id)
        still_missing = []
        for channel in required_channels:
            if not check_subscription_status(user_id, channel):
                still_missing.append(channel)
        
        if not still_missing:
            try:
                bot.delete_message(chat_id, msg_id)
                bot.answer_callback_query(call.id, "✅ Доступ разрешен!", show_alert=False)
            except:
                pass
        else:
            bot.answer_callback_query(call.id, "❌ Вы подписались не на все каналы!", show_alert=True)
        return

    if data == "close_panel":
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
        return

    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ У вас нет прав доступа к этому меню.", show_alert=True)
        return

    if data == "adm_main_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🎛 Панель Администратора</b>\nГлавное меню.",
            reply_markup=generate_main_admin_keyboard()
        )

    elif data == "adm_stats":
        with get_db_connection() as conn:
            users_count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM members").fetchone()[0]
            chats_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM members").fetchone()[0]
            warns_count = conn.execute("SELECT COUNT(*) FROM warns").fetchone()[0]
            logs_count = conn.execute("SELECT COUNT(*) FROM system_logs").fetchone()[0]
        
        stats_text = (
            "<b>📊 Статистика проекта</b>\n\n"
            f"👤 Всего уникальных пользователей: <b>{users_count}</b>\n"
            f"💬 Активных чатов: <b>{chats_count}</b>\n"
            f"⚠️ Выдано предупреждений: <b>{warns_count}</b>\n"
            f"📝 Записей в логах: <b>{logs_count}</b>\n"
            f"🕒 Время сервера: <code>{get_iso_now()}</code>"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=stats_text, reply_markup=generate_back_button())

    elif data == "adm_logs":
        with get_db_connection() as conn:
            logs = conn.execute("SELECT action_type, details, created_at FROM system_logs ORDER BY id DESC LIMIT 8").fetchall()
        
        log_text = "<b>📋 Последние действия системы:</b>\n\n"
        for log in logs:
            dt = format_readable_date(log['created_at'])
            log_text += f"🔹 <code>{dt}</code> | <b>{log['action_type']}</b>\n   └ {sanitize_text(log['details'][:40])}\n"
        
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=log_text, reply_markup=generate_back_button())

    elif data == "adm_manage":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🛡 Управление модулями</b>\nЗдесь вы можете управлять глобальными настройками.",
            reply_markup=generate_management_keyboard()
        )
    
    elif data == "adm_broadcast":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>📡 Режим рассылки</b>\n\nОтправьте сообщение (текст, фото, видео), и оно будет разослано всем пользователям из базы данных.\n\n<i>Нажмите 'Назад' для отмены.</i>",
            reply_markup=generate_back_button()
        )
        _local_memory[user_id] = "waiting_broadcast"

def get_required_channels_for_chat(chat_id):
    with get_db_connection() as conn:
        current_time = get_iso_now()
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND expires IS NOT NULL AND expires <= ?", (chat_id, current_time))
        conn.commit()
        rows = conn.execute("SELECT channel FROM required_subs WHERE chat_id = ?", (chat_id,)).fetchall()
    return [row['channel'] for row in rows]

def check_subscription_status(user_id, channel):
    try:
        status = bot.get_chat_member(channel, user_id).status
        return status not in ['left', 'kicked']
    except Exception:
        return False 

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_broadcast", content_types=['text', 'photo', 'video', 'animation'])
def process_broadcast(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return

    _local_memory.pop(user_id, None)
    bot.send_message(user_id, "⏳ <b>Начинаю рассылку...</b>")
    
    success_count = 0
    fail_count = 0
    
    with get_db_connection() as conn:
        users = conn.execute("SELECT DISTINCT user_id FROM members").fetchall()
    
    for user_row in users:
        target_id = user_row['user_id']
        try:
            bot.copy_message(target_id, message.chat.id, message.message_id)
            success_count += 1
            time.sleep(0.05) 
        except Exception:
            fail_count += 1
    
    bot.send_message(user_id, f"✅ <b>Рассылка завершена!</b>\n\nУспешно: {success_count}\nОшибок: {fail_count}")

@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def group_message_processor(message):
    update_user_activity(message.from_user, message.chat.id)
    
    if check_admin_rights(message.chat.id, message.from_user.id) or message.from_user.is_bot:
        return

    required_channels = get_required_channels_for_chat(message.chat.id)
    if not required_channels:
        return

    missing_channels = []
    for channel in required_channels:
        if not check_subscription_status(message.from_user.id, channel):
            missing_channels.append(channel)
    
    if missing_channels:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        warning_text = (
            f"🚫 <b>Доступ ограничен, {sanitize_text(message.from_user.first_name)}!</b>\n\n"
            "Для того чтобы писать в этот чат, необходимо подписаться на наших партнеров."
        )
        
        try:
            bot.send_message(
                message.chat.id,
                warning_text,
                reply_markup=generate_subscription_keyboard(missing_channels)
            )
        except:
            pass

@bot.message_handler(commands=['setup'])
def command_setup(message):
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "ℹ️ <b>Использование:</b>\n<code>/setup @channel [время]</code>\n\nПример: <code>/setup @news 24h</code>")
        return
    
    channel = args[1]
    duration_str = args[2] if len(args) > 2 else None
    expiry_iso = None
    
    if duration_str:
        delta = parse_time_string(duration_str)
        if delta:
            expiry_iso = (datetime.utcnow() + delta).isoformat()
    
    try:
        bot.get_chat(channel)
    except:
        bot.reply_to(message, "⚠️ <b>Ошибка:</b> Я не вижу этот канал. Сделайте меня там админом или проверьте юзернейм.")
        return

    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO required_subs (chat_id, channel, expires, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, channel, expiry_iso, message.from_user.id, get_iso_now())
        )
        conn.commit()
    
    info = f"до <b>{format_readable_date(expiry_iso)}</b>" if expiry_iso else "<b>навсегда</b>"
    bot.reply_to(message, f"✅ <b>Канал добавлен!</b>\nТеперь пользователи обязаны подписаться на {channel} {info}.")
    log_system_action(message.chat.id, message.from_user.id, "SETUP_SUB", f"Added {channel}")

@bot.message_handler(commands=['unsetup'])
def command_unsetup(message):
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return
        
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "ℹ️ Укажите канал для удаления: <code>/unsetup @channel</code>")
        return

    channel = args[1]
    with get_db_connection() as conn:
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel))
        conn.commit()
    
    bot.reply_to(message, f"🗑 <b>Требование подписки на {channel} удалено.</b>")
    log_system_action(message.chat.id, message.from_user.id, "UNSETUP_SUB", f"Removed {channel}")

@bot.message_handler(commands=['ban'])
def command_ban(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ <b>Ответьте на сообщение</b> пользователя, которого нужно забанить.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return

    target_user = message.reply_to_message.from_user
    try:
        bot.ban_chat_member(message.chat.id, target_user.id)
        bot.reply_to(message, f"⛔ <b>Пользователь забанен!</b>\n👤 Имя: {sanitize_text(target_user.full_name)}\n🆔 ID: <code>{target_user.id}</code>")
        log_system_action(message.chat.id, message.from_user.id, "BAN", f"Banned user {target_user.id}")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Ошибка:</b> Не удалось забанить. Возможно, у бота нет прав или пользователь админ.")

@bot.message_handler(commands=['unban'])
def command_unban(message):
    if not message.reply_to_message:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "ℹ️ Ответьте на сообщение или укажите ID: <code>/unban 123456789</code>")
            return
        target_id = args[1]
    else:
        target_id = message.reply_to_message.from_user.id

    if not check_admin_rights(message.chat.id, message.from_user.id):
        return

    try:
        bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        bot.reply_to(message, f"🕊 <b>Пользователь разбанен.</b>\nID: <code>{target_id}</code>")
        log_system_action(message.chat.id, message.from_user.id, "UNBAN", f"Unbanned user {target_id}")
    except Exception:
        bot.reply_to(message, "❌ Ошибка при разбане.")

@bot.message_handler(commands=['mute'])
def command_mute(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение пользователя.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return

    args = message.text.split()
    duration_str = args[1] if len(args) > 1 else "1h"
    delta = parse_time_string(duration_str)
    
    if not delta:
        bot.reply_to(message, "⚠️ Неверный формат времени. Используйте: 10m, 2h, 1d.")
        return
        
    target_user = message.reply_to_message.from_user
    until_date = datetime.utcnow() + delta
    
    try:
        bot.restrict_chat_member(
            message.chat.id,
            target_user.id,
            until_date=until_date.timestamp(),
            can_send_messages=False
        )
        
        with get_db_connection() as conn:
            conn.execute(
                "INSERT INTO mutes (chat_id, user_id, expires_at) VALUES (?, ?, ?)",
                (message.chat.id, target_user.id, until_date.isoformat())
            )
            conn.commit()

        bot.reply_to(message, f"🔇 <b>Пользователь обеззвучен.</b>\n⏳ Срок: {duration_str}\n👤 Имя: {sanitize_text(target_user.full_name)}")
        log_system_action(message.chat.id, message.from_user.id, "MUTE", f"Muted {target_user.id} for {duration_str}")
    except Exception as e:
        bot.reply_to(message, f"❌ Не удалось выдать мут: {e}")

@bot.message_handler(commands=['unmute'])
def command_unmute(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение пользователя.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return
    
    target_user = message.reply_to_message.from_user
    try:
        bot.restrict_chat_member(
            message.chat.id,
            target_user.id,
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (message.chat.id, target_user.id))
            conn.commit()

        bot.reply_to(message, "🔊 <b>Мут снят досрочно.</b>")
    except Exception:
        bot.reply_to(message, "❌ Ошибка снятия мута.")

@bot.message_handler(commands=['warn'])
def command_warn(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return

    target_user = message.reply_to_message.from_user
    reason = " ".join(message.text.split()[1:]) or "Нарушение правил"

    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, target_user.id, message.from_user.id, reason, get_iso_now())
        )
        conn.commit()
        
        warn_count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target_user.id)).fetchone()[0]

    limit = 3
    if warn_count >= limit:
        try:
            bot.ban_chat_member(message.chat.id, target_user.id)
            bot.reply_to(message, f"⛔ <b>Авто-бан!</b>\nПользователь {sanitize_text(target_user.full_name)} достиг лимита предупреждений ({warn_count}/{limit}).")
            
            with get_db_connection() as conn:
                conn.execute("DELETE FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target_user.id))
                conn.commit()
                
            log_system_action(message.chat.id, message.from_user.id, "BAN_WARN", f"Auto-ban for {target_user.id}")
        except:
            bot.reply_to(message, "❌ Не удалось выдать авто-бан (права?).")
    else:
        bot.reply_to(message, f"⚠️ <b>Предупреждение выдано!</b>\n👤 Пользователь: {sanitize_text(target_user.full_name)}\n📄 Причина: {reason}\n🔢 Счет: <b>{warn_count}/{limit}</b>")
        log_system_action(message.chat.id, message.from_user.id, "WARN", f"Warned {target_user.id} ({warn_count})")

@bot.message_handler(commands=['kick'])
def command_kick(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id):
        return

    target_user = message.reply_to_message.from_user
    try:
        bot.unban_chat_member(message.chat.id, target_user.id)
        bot.reply_to(message, f"👢 <b>Пользователь кикнут.</b>\nОн может вернуться по ссылке.")
        log_system_action(message.chat.id, message.from_user.id, "KICK", f"Kicked {target_user.id}")
    except Exception:
        bot.reply_to(message, "❌ Не удалось кикнуть.")

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_receiver():
    json_update = request.get_data().decode("utf-8")
    update = telebot.types.Update.de_json(json_update)
    bot.process_new_updates([update])
    return "OK", 200

@app.route("/", methods=["GET"])
def health_check():
    return "Service is Running", 200

def setup_webhook_connection():
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=f"{WEBHOOK_HOST.rstrip('/')}/{TOKEN}")

if __name__ == "__main__":
    initialize_database()
    
    worker_thread = threading.Thread(target=background_unmute_worker, daemon=True)
    worker_thread.start()
    
    setup_webhook_connection()
    
    app.run(host="0.0.0.0", port=PORT)
