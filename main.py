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

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
SUB_CHANNEL = os.getenv("SUB_CHANNEL", "@vzref2")
DB_PATH = os.getenv("DB_PATH", "data.db")
# Убедись, что тут твой цифровой ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023")) 
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_STATUSES = ("administrator", "creator")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

_local_memory = {}
# Кэш для юзернейма бота, чтобы не запрашивать API постоянно
BOT_USERNAME = None 

# --- БАЗА ДАННЫХ ---
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

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
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

# --- ГЕНЕРАТОРЫ КЛАВИАТУР ---

def get_bot_username():
    global BOT_USERNAME
    if BOT_USERNAME is None:
        try:
            BOT_USERNAME = bot.get_me().username
        except:
            return "bot_username"
    return BOT_USERNAME

def generate_start_keyboard(user_id):
    """Главное меню при команде /start в ЛС"""
    username = get_bot_username()
    markup = InlineKeyboardMarkup()
    
    # 1. Добавить в группу (Сразу с правами админа)
    add_url = f"https://t.me/{username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat+promote_members"
    markup.add(InlineKeyboardButton("➕ Добавить в группу", url=add_url))
    
    # 2. Настройки группы и Языки
    markup.add(InlineKeyboardButton("⚙️ Настройки группы", callback_data="settings_menu"))
    markup.add(InlineKeyboardButton("🌐 Languages", callback_data="languages_menu"))
    
    # 3. Админ меню (только для владельца)
    if user_id == ADMIN_ID:
        markup.add(InlineKeyboardButton("🔒 Админ меню", callback_data="adm_main_menu"))
        
    return markup

def generate_settings_keyboard():
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return markup

def generate_languages_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return markup

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
    markup.add(InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu"))
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

# --- ОБРАБОТЧИКИ КОМАНД ---

@bot.message_handler(commands=['start'])
def command_start_handler(message):
    user_id = message.from_user.id
    
    # 1. Логика для ГРУППЫ
    if message.chat.type in ['group', 'supergroup']:
        bot_info = bot.get_me()
        
        # Пытаемся удалить команду /start, чтобы не засорять чат
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        
        # Отправляем сообщение "Я бот..."
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🤖 Перейти в ЛС для настройки", url=f"https://t.me/{bot_info.username}?start=settings"))
        
        bot.send_message(
            message.chat.id,
            f"👋 Привет! Я — <b>{bot_info.first_name}</b>.\n\n"
            "Я помогаю управлять группами и подписками.\n"
            "Чтобы настроить меня или изменить язык, напишите мне в личные сообщения.",
            reply_markup=kb
        )
        return

    # 2. Логика для ЛИЧНЫХ СООБЩЕНИЙ (Меню пользователя/админа)
    if message.chat.type == 'private':
        welcome_msg = (
            f"👋 <b>Приветствую, {sanitize_text(message.from_user.first_name)}!</b>\n\n"
            "Я — автоматизированная система модерации чатов.\n"
            "Используйте меню ниже для управления ботом:"
        )
        bot.send_message(
            message.chat.id, 
            welcome_msg, 
            reply_markup=generate_start_keyboard(user_id)
        )

# --- ОБРАБОТЧИК CALLBACK (КНОПОК) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    # --- ОБЩИЕ КНОПКИ ---
    
    # Главное меню (возврат)
    if data == "main_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"👋 <b>Приветствую, {sanitize_text(call.from_user.first_name)}!</b>\n\nВыберите действие:",
            reply_markup=generate_start_keyboard(user_id)
        )
        return

    # Настройки группы
    if data == "settings_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="⚙️ <b>Настройки группы</b>\n\nЗдесь в будущем будут настройки фильтров, приветствий и прочего.",
            reply_markup=generate_settings_keyboard()
        )
        return

    # Языки
    if data == "languages_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="🌐 <b>Выберите язык / Choose Language:</b>",
            reply_markup=generate_languages_keyboard()
        )
        return
    
    if data in ["lang_ru", "lang_en"]:
        lang = "Русский" if data == "lang_ru" else "English"
        bot.answer_callback_query(call.id, f"✅ Язык изменен на {lang} (демо)", show_alert=False)
        return

    # --- КНОПКИ ПОДПИСКИ ---

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

    # --- АДМИН ПАНЕЛЬ ---

    # Закрыть панель
    if data == "close_panel":
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
        return

    # Проверка на админа для всех действий ниже
    if "adm_" in data and user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ У вас нет прав доступа к этому меню.", show_alert=True)
        return

    if data == "adm_main_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🎛 Панель Администратора</b>\nГлавное меню управления ботом.",
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

# --- ЛОГИКА ПРОВЕРКИ ПОДПИСОК ---

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

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---

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
    
    # Если админ или бот - игнор проверок
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

# --- АДМИН КОМАНДЫ (SETUP, BAN, MUTE и т.д.) ---
# Оставлены без изменений, так как они работают корректно

@bot.message_handler(commands=['setup'])
def command_setup(message):
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "ℹ️ <b>Использование:</b>\n<code>/setup @channel [время]</code>")
        return
    channel = args[1]
    duration_str = args[2] if len(args) > 2 else None
    expiry_iso = None
    if duration_str:
        delta = parse_time_string(duration_str)
        if delta: expiry_iso = (datetime.utcnow() + delta).isoformat()
    try:
        bot.get_chat(channel)
    except:
        bot.reply_to(message, "⚠️ <b>Ошибка:</b> Я не вижу этот канал.")
        return
    with get_db_connection() as conn:
        conn.execute("INSERT INTO required_subs (chat_id, channel, expires, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, channel, expiry_iso, message.from_user.id, get_iso_now()))
        conn.commit()
    info = f"до <b>{format_readable_date(expiry_iso)}</b>" if expiry_iso else "<b>навсегда</b>"
    bot.reply_to(message, f"✅ <b>Канал добавлен!</b>\nПодписка на {channel} {info}.")

@bot.message_handler(commands=['unsetup'])
def command_unsetup(message):
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "ℹ️ Пример: <code>/unsetup @channel</code>")
        return
    channel = args[1]
    with get_db_connection() as conn:
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel))
        conn.commit()
    bot.reply_to(message, f"🗑 <b>Требование подписки на {channel} удалено.</b>")

@bot.message_handler(commands=['ban'])
def command_ban(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    target_user = message.reply_to_message.from_user
    try:
        bot.ban_chat_member(message.chat.id, target_user.id)
        bot.reply_to(message, f"⛔ <b>Забанен:</b> {sanitize_text(target_user.full_name)}")
    except: bot.reply_to(message, "❌ Ошибка бана.")

@bot.message_handler(commands=['unban'])
def command_unban(message):
    if not message.reply_to_message and len(message.text.split()) < 2:
        bot.reply_to(message, "ℹ️ ID или реплай.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    target_id = message.reply_to_message.from_user.id if message.reply_to_message else message.text.split()[1]
    try:
        bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        bot.reply_to(message, f"🕊 <b>Разбанен:</b> {target_id}")
    except: bot.reply_to(message, "❌ Ошибка разбана.")

@bot.message_handler(commands=['mute'])
def command_mute(message):
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    args = message.text.split()
    duration = args[1] if len(args) > 1 else "1h"
    delta = parse_time_string(duration)
    if not delta: return
    target = message.reply_to_message.from_user
    until = datetime.utcnow() + delta
    try:
        bot.restrict_chat_member(message.chat.id, target.id, until_date=until.timestamp(), can_send_messages=False)
        with get_db_connection() as conn:
            conn.execute("INSERT INTO mutes (chat_id, user_id, expires_at) VALUES (?, ?, ?)", (message.chat.id, target.id, until.isoformat()))
            conn.commit()
        bot.reply_to(message, f"🔇 <b>Мут на {duration}:</b> {sanitize_text(target.full_name)}")
    except Exception as e: bot.reply_to(message, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['unmute'])
def command_unmute(message):
    if not message.reply_to_message: return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    target = message.reply_to_message.from_user
    try:
        bot.restrict_chat_member(message.chat.id, target.id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
            conn.commit()
        bot.reply_to(message, "🔊 <b>Мут снят.</b>")
    except: pass

@bot.message_handler(commands=['warn'])
def command_warn(message):
    if not message.reply_to_message: return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    target = message.reply_to_message.from_user
    reason = " ".join(message.text.split()[1:]) or "Нарушение"
    with get_db_connection() as conn:
        conn.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, target.id, message.from_user.id, reason, get_iso_now()))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id)).fetchone()[0]
    limit = 3
    if count >= limit:
        try:
            bot.ban_chat_member(message.chat.id, target.id)
            bot.reply_to(message, f"⛔ <b>Бан за варны ({count}/{limit}):</b> {sanitize_text(target.full_name)}")
            with get_db_connection() as conn:
                conn.execute("DELETE FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
                conn.commit()
        except: pass
    else:
        bot.reply_to(message, f"⚠️ <b>Варн ({count}/{limit}):</b> {sanitize_text(target.full_name)}\nПричина: {reason}")

@bot.message_handler(commands=['kick'])
def command_kick(message):
    if not message.reply_to_message: return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    try:
        bot.unban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        bot.reply_to(message, "👢 <b>Кикнут.</b>")
    except: pass

# --- ЗАПУСК ---

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
    
    # Запускаем фоновую задачу размута
    worker_thread = threading.Thread(target=background_unmute_worker, daemon=True)
    worker_thread.start()
    
    # Настраиваем вебхук
    setup_webhook_connection()
    
    # Запускаем Flask сервер
    app.run(host="0.0.0.0", port=PORT)
