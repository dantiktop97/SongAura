import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import json
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Update

# --- КОНФИГУРАЦИЯ ---
# ВАЖНО: Замените "YOUR_TOKEN_HERE" на ваш реальный токен
TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
# Это основной, глобальный канал (используется для примера, но лучше управлять через /setup в чатах)
SUB_CHANNEL = os.getenv("SUB_CHANNEL", "@vzref2") 
DB_PATH = os.getenv("DB_PATH", "data.db")
# ВАЖНО: Убедитесь, что тут ваш цифровой ID
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023")) 
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_STATUSES = ("administrator", "creator")
MAX_LOG_ENTRIES = 10 # Количество логов для отображения

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Локальное хранилище для пошаговых действий администратора (state machine)
_local_memory = {} 
# Кэш для юзернейма бота
BOT_USERNAME = None 

# --- БАЗА ДАННЫХ ---
def get_db_connection():
    """Получает соединение с базой данных."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Инициализирует все необходимые таблицы."""
    with get_db_connection() as conn:
        # Таблица для обязательных подписок (привязана к конкретному чату)
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
        # Таблица для отслеживания активности участников
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
        # Таблица для предупреждений (варнов)
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
        # Таблица для отслеживания мьютов
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mutes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                expires_at TEXT,
                UNIQUE(chat_id, user_id)
            )
        """)
        # Таблица для системных логов
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
    """Возвращает текущее время в UTC ISO формате."""
    return datetime.utcnow().isoformat()

def parse_iso_datetime(iso_str):
    """Преобразует ISO строку в datetime объект."""
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None

def format_readable_date(iso_str):
    """Форматирует ISO строку в читаемую дату."""
    dt = parse_iso_datetime(iso_str)
    # Формат: 22.11.2025 18:27 UTC
    return dt.strftime("%d.%m.%Y %H:%M UTC") if dt else "Бессрочно"

def sanitize_text(text):
    """Экранирует специальные символы HTML."""
    if not text: return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def get_full_user_name(user):
    """Получает полное имя пользователя."""
    if user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.first_name

def check_admin_rights(chat_id, user_id):
    """Проверяет права администратора в чате или совпадение с ADMIN_ID."""
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ADMIN_STATUSES
    except Exception:
        # Если чат не найден или бот не админ, возвращаем False
        return False

def log_system_action(chat_id, user_id, action, details=""):
    """Записывает системное действие в лог."""
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
    """Обновляет активность пользователя в базе данных."""
    try:
        with get_db_connection() as conn:
            # Ищем существующую запись
            cursor = conn.execute("SELECT id FROM members WHERE user_id = ? AND chat_id = ?", (user.id, chat_id))
            exists = cursor.fetchone()
            
            username = user.username or ""
            first_name = user.first_name or ""
            last_name = user.last_name or ""

            if exists:
                # Обновляем активность
                conn.execute("""
                    UPDATE members SET 
                    username = ?, first_name = ?, last_name = ?, messages_count = messages_count + 1, last_seen = ? 
                    WHERE id = ?
                """, (username, first_name, last_name, get_iso_now(), exists['id']))
            else:
                # Вставляем новую запись
                conn.execute("""
                    INSERT INTO members (user_id, chat_id, username, first_name, last_name, messages_count, last_seen)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                """, (user.id, chat_id, username, first_name, last_name, get_iso_now()))
            conn.commit()
    except Exception as e:
        print(f"Activity Update Error: {e}")

def parse_time_string(time_str):
    """Парсит строку времени (e.g., '30m', '1d') в timedelta."""
    regex = re.match(r"(\d+)([smhd])", time_str.lower())
    if not regex: return None
    value, unit = int(regex.group(1)), regex.group(2)
    if value <= 0: return None
    if unit == 's': return timedelta(seconds=value)
    if unit == 'm': return timedelta(minutes=value)
    if unit == 'h': return timedelta(hours=value)
    if unit == 'd': return timedelta(days=value)
    return None

def background_unmute_worker():
    """Фоновая задача для автоматического размута пользователей."""
    while True:
        try:
            with get_db_connection() as conn:
                # Выбираем все мьюты, которые не истекли (чтобы избежать лишних запросов)
                expired_mutes = conn.execute("SELECT id, chat_id, user_id, expires_at FROM mutes WHERE expires_at IS NOT NULL").fetchall()
                current_time = datetime.utcnow()
                
                for mute in expired_mutes:
                    expiry = parse_iso_datetime(mute['expires_at'])
                    if expiry and expiry <= current_time:
                        try:
                            # Пытаемся размутить
                            bot.restrict_chat_member(
                                mute['chat_id'], 
                                mute['user_id'], 
                                can_send_messages=True,
                                can_send_media_messages=True,
                                can_send_other_messages=True,
                                can_add_web_page_previews=True
                            )
                            # Отправляем уведомление
                            bot.send_message(
                                mute['chat_id'], 
                                f"🔊 <b>Время истекло.</b> Пользователь <a href='tg://user?id={mute['user_id']}'>{mute['user_id']}</a> размучен.",
                                disable_notification=True
                            )
                            log_system_action(mute['chat_id'], mute['user_id'], "UNMUTE_AUTO", f"Автоматический размут. Истекло в {format_readable_date(mute['expires_at'])}")
                        except Exception as e:
                            print(f"Failed to unmute {mute['user_id']}: {e}")
                            # Логируем ошибку, но все равно удаляем из списка, чтобы не повторять попытку
                        finally:
                            # Удаляем из таблицы мьютов
                            conn.execute("DELETE FROM mutes WHERE id = ?", (mute['id'],))
                conn.commit()
        except Exception as e:
            print(f"Worker Error: {e}")
        time.sleep(20)

# --- ГЕНЕРАТОРЫ КЛАВИАТУР ---

def get_bot_username():
    """Получает и кэширует юзернейм бота."""
    global BOT_USERNAME
    if BOT_USERNAME is None:
        try:
            BOT_USERNAME = bot.get_me().username
        except:
            return "bot_username"
    return BOT_USERNAME

def generate_start_keyboard(user_id):
    """Главное меню при команде /start в ЛС."""
    username = get_bot_username()
    markup = InlineKeyboardMarkup()
    
    # URL для добавления бота в группу с правами
    add_url = f"https://t.me/{username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat+promote_members"
    markup.add(InlineKeyboardButton("➕ Добавить в группу", url=add_url))
    
    markup.add(InlineKeyboardButton("⚙️ Настройки группы (демо)", callback_data="settings_menu"))
    markup.add(InlineKeyboardButton("🌐 Languages (демо)", callback_data="languages_menu"))
    
    # Админ меню (только для владельца)
    if user_id == ADMIN_ID:
        markup.add(InlineKeyboardButton("🔒 Админ меню", callback_data="adm_main_menu"))
        
    return markup

def generate_settings_keyboard():
    """Клавиатура настроек (демо)."""
    markup = InlineKeyboardMarkup()
    # Здесь могут быть другие настройки
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return markup

def generate_languages_keyboard():
    """Клавиатура выбора языка (демо)."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")
    )
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="main_menu"))
    return markup

def generate_main_admin_keyboard():
    """Главное меню администратора."""
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
        InlineKeyboardButton("📡 Рассылка", callback_data="adm_broadcast")
    )
    markup.row(
        InlineKeyboardButton("📋 Логи системы", callback_data="adm_logs"),
        InlineKeyboardButton("🛡 Управление подписками", callback_data="adm_manage_subs")
    )
    markup.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_panel"))
    markup.add(InlineKeyboardButton("⬅️ В главное меню", callback_data="main_menu"))
    return markup

def generate_management_keyboard():
    """Меню управления подписками (глобальное)."""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📋 Показать все подписки", callback_data="mng_show_subs"))
    markup.add(InlineKeyboardButton("➕ Добавить подписку (через /setup в чате)", callback_data="mng_info_add"))
    markup.add(InlineKeyboardButton("➖ Удалить подписку (по ID)", callback_data="mng_del_sub_start"))
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="adm_main_menu"))
    return markup

def generate_back_button(callback_data="adm_main_menu"):
    """Генерирует кнопку "Назад"."""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Вернуться назад", callback_data=callback_data))
    return markup

def generate_subscription_keyboard(missing_channels):
    """Клавиатура для проверки подписки в чате."""
    markup = InlineKeyboardMarkup()
    for channel in missing_channels:
        # Убеждаемся, что в URL нет символа '@'
        clean_name = channel.replace("@", "")
        markup.add(InlineKeyboardButton(f"👉 Подписаться на {channel}", url=f"https://t.me/{clean_name}"))
    markup.add(InlineKeyboardButton("✅ Я подписался", callback_data="verify_subscription"))
    return markup

def generate_delete_subscription_keyboard(subs):
    """Клавиатура для выбора подписки на удаление."""
    markup = InlineKeyboardMarkup()
    for sub in subs:
        chat_name = f"Chat_{sub['chat_id']}"
        try:
            # Пытаемся получить имя чата
            chat_info = bot.get_chat(sub['chat_id'])
            chat_name = sanitize_text(chat_info.title)
        except Exception:
            pass # Если не удалось, оставляем ID

        display_name = f"[{sub['id']}] {sub['channel']} в {chat_name}"
        markup.add(InlineKeyboardButton(display_name, callback_data=f"mng_del_sub:{sub['id']}"))
    
    markup.add(InlineKeyboardButton("⬅️ Назад", callback_data="adm_manage_subs"))
    return markup

# --- ЛОГИКА ПРОВЕРКИ ПОДПИСОК ---

def get_required_channels_for_chat(chat_id):
    """Получает список активных обязательных каналов для чата."""
    with get_db_connection() as conn:
        current_time = get_iso_now()
        # Удаляем просроченные подписки
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND expires IS NOT NULL AND expires <= ?", (chat_id, current_time))
        conn.commit()
        # Возвращаем активные
        rows = conn.execute("SELECT channel FROM required_subs WHERE chat_id = ?", (chat_id,)).fetchall()
    return [row['channel'] for row in rows]

def check_subscription_status(user_id, channel):
    """Проверяет статус подписки пользователя на канал."""
    try:
        # get_chat_member вызовет ошибку, если канал приватный и бот не админ
        status = bot.get_chat_member(channel, user_id).status
        return status not in ['left', 'kicked']
    except Exception as e:
        # В случае ошибки (например, бот не в канале), предполагаем, что подписка не проверена/недействительна
        print(f"Error checking sub for {user_id} on {channel}: {e}")
        # Если бот не может проверить, он должен считать, что пользователь не подписан.
        return False 

# --- ОБРАБОТЧИК CALLBACK (КНОПОК) ---

@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data

    # --- ОБЩИЕ КНОПКИ ---
    
    if data == "main_menu":
        # Очистка локальной памяти при возврате в главное меню
        _local_memory.pop(user_id, None)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"👋 <b>Приветствую, {sanitize_text(call.from_user.first_name)}!</b>\n\nВыберите действие:",
            reply_markup=generate_start_keyboard(user_id)
        )
        return

    if data == "settings_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="⚙️ <b>Настройки группы (демо)</b>\n\nЗдесь в будущем будут настройки фильтров, приветствий и прочего. Для управления подписками используйте /setup в нужном чате.",
            reply_markup=generate_settings_keyboard()
        )
        return

    if data == "languages_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="🌐 <b>Выберите язык / Choose Language (демо):</b>",
            reply_markup=generate_languages_keyboard()
        )
        return
    
    if data in ["lang_ru", "lang_en"]:
        lang = "Русский" if data == "lang_ru" else "English"
        bot.answer_callback_query(call.id, f"✅ Язык изменен на {lang} (демо)", show_alert=False)
        return
    
    if data == "close_panel":
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            bot.answer_callback_query(call.id, "Панель закрыта.", show_alert=False)
        return

    # --- КНОПКИ ПОДПИСКИ В ГРУППЕ ---

    if data == "verify_subscription":
        # Проверка подписок в чате, откуда пришел callback
        required_channels = get_required_channels_for_chat(call.message.chat.id)
        still_missing = []
        for channel in required_channels:
            if not check_subscription_status(user_id, channel):
                still_missing.append(channel)
        
        if not still_missing:
            try:
                # Удаляем сообщение с требованием подписки
                bot.delete_message(call.message.chat.id, msg_id)
                bot.answer_callback_query(call.id, "✅ Доступ разрешен! Можете писать в чат.", show_alert=False)
            except Exception:
                bot.answer_callback_query(call.id, "✅ Доступ разрешен!", show_alert=False)
        else:
            bot.answer_callback_query(call.id, "❌ Вы подписались не на все каналы! Повторите проверку после подписки.", show_alert=True)
        return

    # --- АДМИН ПАНЕЛЬ (ПРОВЕРКА) ---

    # Проверка на админа для всех действий ниже
    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ У вас нет прав доступа к этому меню. Вы не владелец бота.", show_alert=True)
        return
    
    # Очистка состояния перед входом в меню
    _local_memory.pop(user_id, None) 

    # --- АДМИН: ГЛАВНОЕ МЕНЮ ---
    if data == "adm_main_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🎛 Панель Администратора</b>\nГлавное меню управления ботом.",
            reply_markup=generate_main_admin_keyboard()
        )

    # --- АДМИН: СТАТИСТИКА ---
    elif data == "adm_stats":
        with get_db_connection() as conn:
            # Общая статистика
            users_count = conn.execute("SELECT COUNT(DISTINCT user_id) FROM members").fetchone()[0]
            chats_count = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM required_subs").fetchone()[0]
            total_messages = conn.execute("SELECT SUM(messages_count) FROM members").fetchone()[0] or 0
            warns_count = conn.execute("SELECT COUNT(*) FROM warns").fetchone()[0]
            active_mutes = conn.execute("SELECT COUNT(*) FROM mutes").fetchone()[0]
            subs_count = conn.execute("SELECT COUNT(*) FROM required_subs").fetchone()[0]

        stats_text = (
            "<b>📊 Статистика проекта</b>\n\n"
            f"👤 Всего уникальных пользователей: <b>{users_count}</b>\n"
            f"💬 Чатов с активными подписками: <b>{chats_count}</b>\n"
            f"✉️ Общее кол-во сообщений (в базе): <b>{total_messages}</b>\n"
            f"🔗 Активных подписок: <b>{subs_count}</b>\n"
            f"🔇 Активных мьютов (в базе): <b>{active_mutes}</b>\n"
            f"⚠️ Выдано предупреждений: <b>{warns_count}</b>\n"
            f"🕒 Время сервера: <code>{get_iso_now()}</code>"
        )
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=stats_text, reply_markup=generate_back_button())

    # --- АДМИН: ЛОГИ ---
    elif data == "adm_logs":
        with get_db_connection() as conn:
            logs = conn.execute(f"SELECT action_type, details, created_at FROM system_logs ORDER BY id DESC LIMIT {MAX_LOG_ENTRIES}").fetchall()
        
        log_text = f"<b>📋 Последние {MAX_LOG_ENTRIES} действий системы:</b>\n\n"
        if not logs:
            log_text += "<i>Логи пока пусты.</i>"
        else:
            for log in logs:
                dt = format_readable_date(log['created_at'])
                # Обрезаем детали до 60 символов
                details = sanitize_text(log['details'])
                log_text += f"🔹 <code>{dt}</code>\n   └ <b>{log['action_type']}</b>: {details[:60]}{'...' if len(details) > 60 else ''}\n"
        
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=log_text, reply_markup=generate_back_button())

    # --- АДМИН: МЕНЮ УПРАВЛЕНИЯ ПОДПИСКАМИ ---
    elif data == "adm_manage_subs":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🛡 Управление обязательными подписками</b>\n\nЗдесь вы можете посмотреть и удалить активные требования подписки.",
            reply_markup=generate_management_keyboard()
        )

    elif data == "mng_info_add":
        # Сообщение-инструкция для добавления подписки
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>ℹ️ Добавление подписки</b>\n\n"
                 "Чтобы добавить обязательную подписку для группы, вам нужно использовать команду <code>/setup</code> <b>в самой группе</b>, где бот является администратором.\n\n"
                 "<b>Формат:</b> <code>/setup @username_канала [время_действия]</code>\n"
                 "Пример: <code>/setup @MyChannel 1d</code> (на 1 день)\n"
                 "Пример: <code>/setup @MyChannel</code> (навсегда)",
            reply_markup=generate_back_button("adm_manage_subs")
        )

    # --- АДМИН: ПОКАЗАТЬ ВСЕ ПОДПИСКИ ---
    elif data == "mng_show_subs":
        with get_db_connection() as conn:
            subs = conn.execute("SELECT id, chat_id, channel, expires FROM required_subs ORDER BY chat_id, channel").fetchall()

        sub_list_text = "<b>📋 Активные требования подписок:</b>\n\n"
        if not subs:
            sub_list_text += "<i>Нет активных требований подписки ни в одном из чатов.</i>"
        else:
            current_chat_id = None
            for sub in subs:
                if sub['chat_id'] != current_chat_id:
                    current_chat_id = sub['chat_id']
                    try:
                        chat_info = bot.get_chat(current_chat_id)
                        chat_name = sanitize_text(chat_info.title)
                    except Exception:
                        chat_name = f"Неизвестный чат ({current_chat_id})"
                    
                    sub_list_text += f"\n--- 👥 <b>{chat_name}</b> (ID: <code>{current_chat_id}</code>) ---\n"
                
                expiry_str = format_readable_date(sub['expires'])
                sub_list_text += f"• <code>[ID:{sub['id']}]</code> <b>{sub['channel']}</b> (до: {expiry_str})\n"

        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg_id, 
            text=sub_list_text, 
            reply_markup=generate_back_button("adm_manage_subs")
        )

    # --- АДМИН: НАЧАТЬ УДАЛЕНИЕ ПОДПИСКИ ---
    elif data == "mng_del_sub_start":
        with get_db_connection() as conn:
            subs = conn.execute("SELECT id, chat_id, channel, expires FROM required_subs ORDER BY id DESC LIMIT 50").fetchall()
        
        if not subs:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_id, 
                text="<b>❌ Нет подписок для удаления.</b>", 
                reply_markup=generate_back_button("adm_manage_subs")
            )
            return
            
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>➖ Выберите подписку для удаления:</b>\n\n<i>Отображаются последние 50 записей.</i>",
            reply_markup=generate_delete_subscription_keyboard(subs)
        )

    # --- АДМИН: ФАКТИЧЕСКОЕ УДАЛЕНИЕ ПОДПИСКИ ---
    elif data.startswith("mng_del_sub:"):
        sub_id = data.split(":")[1]
        try:
            sub_id = int(sub_id)
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Некорректный ID.", show_alert=True)
            return

        with get_db_connection() as conn:
            # Получаем информацию для лога
            cursor = conn.execute("SELECT chat_id, channel FROM required_subs WHERE id = ?", (sub_id,))
            sub_info = cursor.fetchone()
            
            if sub_info:
                conn.execute("DELETE FROM required_subs WHERE id = ?", (sub_id,))
                conn.commit()
                log_system_action(sub_info['chat_id'], user_id, "DEL_SUB", f"Удалена подписка [ID:{sub_id}] {sub_info['channel']}")
                bot.answer_callback_query(call.id, f"✅ Подписка [ID:{sub_id}] удалена.", show_alert=False)
            else:
                bot.answer_callback_query(call.id, f"❌ Подписка [ID:{sub_id}] не найдена.", show_alert=True)
                
        # Перезагружаем меню управления подписками
        call.data = "adm_manage_subs"
        callback_query_handler(call) # Вызываем обработчик для обновления меню

    # --- АДМИН: РАССЫЛКА (НАЧАЛО) ---
    elif data == "adm_broadcast":
        # Очистка состояния перед входом в меню
        _local_memory.pop(user_id, None)
        
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>📡 Режим рассылки</b>\n\nОтправьте сообщение (текст, фото, видео, анимация), и оно будет разослано всем уникальным пользователям из базы данных.\n\n<i>Нажмите 'Назад' для отмены.</i>",
            reply_markup=generate_back_button()
        )
        # Устанавливаем состояние ожидания
        _local_memory[user_id] = "waiting_broadcast"

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ В ЛС ---

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_broadcast", content_types=['text', 'photo', 'video', 'animation', 'sticker', 'document'])
def process_broadcast(message):
    """Обрабатывает сообщение для рассылки."""
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return

    # Удаляем состояние, чтобы избежать повторной обработки
    _local_memory.pop(user_id, None) 
    
    # Отправляем подтверждение о начале
    bot.send_message(user_id, "⏳ <b>Начинаю рассылку...</b> Это может занять время.")
    
    success_count = 0
    fail_count = 0
    
    with get_db_connection() as conn:
        # Получаем всех уникальных пользователей, которым когда-либо писал бот
        users = conn.execute("SELECT DISTINCT user_id FROM members").fetchall()
    
    # Асинхронная отправка (хотя time.sleep немного замедляет процесс, это защищает от флуд-лимитов)
    for user_row in users:
        target_id = user_row['user_id']
        if target_id == user_id: # Не отправляем самому себе повторно
            continue

        try:
            bot.copy_message(target_id, message.chat.id, message.message_id)
            success_count += 1
            time.sleep(0.04) # Небольшая задержка для соблюдения лимитов
        except Exception:
            fail_count += 1
    
    result_message = f"✅ <b>Рассылка завершена!</b>\n\nУспешно: {success_count}\nОшибок (заблокировали/удалили): {fail_count}"
    bot.send_message(user_id, result_message)
    log_system_action(user_id, user_id, "BROADCAST_END", f"Рассылка завершена. Успешно: {success_count}, Ошибок: {fail_count}")

# --- КОМАНДЫ ДЛЯ ЧАТА ---

@bot.message_handler(commands=['start'])
def command_start_handler(message):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    
    # 1. Логика для ГРУППЫ
    if message.chat.type in ['group', 'supergroup']:
        bot_info = bot.get_me()
        
        # Пытаемся удалить команду /start, чтобы не засорять чат
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("🤖 Перейти в ЛС для настройки", url=f"https://t.me/{bot_info.username}?start=settings"))
        
        bot.send_message(
            message.chat.id,
            f"👋 Привет! Я — <b>{bot_info.first_name}</b>.\n\n"
            "Я помогаю управлять группой и подписками. Чтобы настроить меня, перейдите в ЛС.",
            reply_markup=kb,
            parse_mode="HTML"
        )
        return

    # 2. Логика для ЛИЧНЫХ СООБЩЕНИЙ (Меню пользователя/админа)
    if message.chat.type == 'private':
        welcome_msg = (
            f"👋 <b>Приветствую, {sanitize_text(get_full_user_name(message.from_user))}!</b>\n\n"
            "Я — автоматизированная система модерации чатов.\n"
            "Используйте меню ниже для управления ботом:"
        )
        bot.send_message(
            message.chat.id, 
            welcome_msg, 
            reply_markup=generate_start_keyboard(user_id)
        )

@bot.message_handler(commands=['setup'])
def command_setup(message):
    """Добавляет обязательный канал для подписки в чате."""
    if not check_admin_rights(message.chat.id, message.from_user.id): 
        bot.reply_to(message, "⛔ Только администраторы могут использовать эту команду.")
        return
        
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "ℹ️ <b>Использование:</b>\n<code>/setup @channel [время]</code>\n\nПример: <code>/setup @MyChannel 1d</code>")
        return
        
    channel = args[1]
    duration_str = args[2] if len(args) > 2 else None
    expiry_iso = None
    
    if duration_str:
        delta = parse_time_string(duration_str)
        if delta: 
            expiry_iso = (datetime.utcnow() + delta).isoformat()
        else:
            bot.reply_to(message, "⚠️ <b>Ошибка:</b> Неверный формат времени. Используйте: <code>30m</code>, <code>1h</code>, <code>5d</code> и т.д.")
            return

    try:
        # Проверяем существование канала и права бота (боту не обязательно быть админом, чтобы проверять подписку)
        chat_info = bot.get_chat(channel)
        if chat_info.type not in ['channel', 'supergroup']:
             bot.reply_to(message, "⚠️ <b>Ошибка:</b> Это не канал или супергруппа.")
             return
    except Exception as e:
        bot.reply_to(message, f"⚠️ <b>Ошибка:</b> Я не вижу этот канал. Убедитесь, что он существует и его юзернейм корректен.")
        log_system_action(message.chat.id, message.from_user.id, "SETUP_FAIL", f"Не удалось добавить канал {channel}. Ошибка: {e}")
        return
        
    with get_db_connection() as conn:
        conn.execute("INSERT INTO required_subs (chat_id, channel, expires, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, channel, expiry_iso, message.from_user.id, get_iso_now()))
        conn.commit()
        
    info = f"до <b>{format_readable_date(expiry_iso)}</b>" if expiry_iso else "<b>навсегда</b>"
    bot.reply_to(message, f"✅ <b>Канал добавлен!</b>\nТеперь подписка на <b>{channel}</b> обязательна {info}.")
    log_system_action(message.chat.id, message.from_user.id, "SETUP_ADD", f"Добавлен канал: {channel} {info}")

@bot.message_handler(commands=['unsetup'])
def command_unsetup(message):
    """Удаляет обязательный канал для подписки из чата."""
    if not check_admin_rights(message.chat.id, message.from_user.id): 
        bot.reply_to(message, "⛔ Только администраторы могут использовать эту команду.")
        return
        
    args = message.text.split()
    if len(args) < 2:
        # Показываем список текущих подписок, чтобы админ мог выбрать
        required_channels = get_required_channels_for_chat(message.chat.id)
        if not required_channels:
            bot.reply_to(message, "ℹ️ <b>Использование:</b> <code>/unsetup @channel</code>\n\n<i>В этом чате нет активных требований подписки.</i>")
            return
        
        list_text = "ℹ️ <b>Текущие обязательные подписки:</b>\n" + "\n".join(required_channels)
        bot.reply_to(message, list_text + "\n\nВведите команду с юзернеймом для удаления.")
        return
        
    channel = args[1]
    with get_db_connection() as conn:
        cursor = conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel))
        conn.commit()
        
    if cursor.rowcount > 0:
        bot.reply_to(message, f"🗑 <b>Требование подписки на {channel} удалено.</b>")
        log_system_action(message.chat.id, message.from_user.id, "SETUP_DEL", f"Удален канал: {channel}")
    else:
        bot.reply_to(message, f"❌ <b>Ошибка:</b> Подписка на {channel} не найдена в списке обязательных для этого чата.")

@bot.message_handler(commands=['ban'])
def command_ban(message):
    """Банит пользователя по реплаю."""
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение пользователя, которого хотите забанить.")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    
    target_user = message.reply_to_message.from_user
    
    try:
        # 1. Бан пользователя
        bot.ban_chat_member(message.chat.id, target_user.id)
        # 2. Удаление исходного сообщения
        try:
            bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
        # 3. Ответ с подтверждением
        bot.reply_to(message, f"⛔ <b>Забанен:</b> {sanitize_text(get_full_user_name(target_user))}")
        log_system_action(message.chat.id, message.from_user.id, "BAN", f"Забанен {target_user.id} ({get_full_user_name(target_user)})")
    except Exception as e: 
        bot.reply_to(message, f"❌ Ошибка бана: {e}")

@bot.message_handler(commands=['unban'])
def command_unban(message):
    """Разбанивает пользователя по реплаю или ID."""
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.text.split()) > 1:
        try:
            target_id = int(message.text.split()[1])
        except ValueError:
            bot.reply_to(message, "ℹ️ ID или реплай.")
            return

    if not target_id:
        bot.reply_to(message, "ℹ️ ID или реплай.")
        return

    try:
        bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        bot.reply_to(message, f"🕊 <b>Разбанен:</b> <code>{target_id}</code>")
        log_system_action(message.chat.id, message.from_user.id, "UNBAN", f"Разбанен {target_id}")
    except Exception as e: 
        bot.reply_to(message, f"❌ Ошибка разбана: {e}")

@bot.message_handler(commands=['mute'])
def command_mute(message):
    """Мьютит пользователя на заданное время по реплаю."""
    if not message.reply_to_message:
        bot.reply_to(message, "↩️ Ответьте на сообщение. Пример: <code>/mute 1h</code>")
        return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    
    args = message.text.split()
    duration = args[1] if len(args) > 1 else "1h"
    delta = parse_time_string(duration)
    
    if not delta: 
        bot.reply_to(message, "⚠️ Неверный формат времени. Используйте: <code>30m</code>, <code>1h</code>, <code>5d</code>.")
        return
        
    target = message.reply_to_message.from_user
    until = datetime.utcnow() + delta
    
    try:
        # 1. Ограничение прав в Telegram
        bot.restrict_chat_member(message.chat.id, target.id, until_date=until.timestamp(), can_send_messages=False)
        
        # 2. Сохранение мьюта в БД
        with get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO mutes (chat_id, user_id, expires_at) VALUES (?, ?, ?)", 
                (message.chat.id, target.id, until.isoformat()))
            conn.commit()
            
        # 3. Удаление исходного сообщения
        try:
            bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
            
        bot.reply_to(message, f"🔇 <b>Мут на {duration}:</b> {sanitize_text(get_full_user_name(target))}\nАвтоматический размут: {format_readable_date(until.isoformat())}")
        log_system_action(message.chat.id, message.from_user.id, "MUTE", f"Замучен {target.id} на {duration}")
    except Exception as e: 
        bot.reply_to(message, f"❌ Ошибка мьюта: {e}")

@bot.message_handler(commands=['unmute'])
def command_unmute(message):
    """Снимает мьют с пользователя по реплаю."""
    if not message.reply_to_message: return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    
    target = message.reply_to_message.from_user
    
    try:
        # 1. Снятие ограничений в Telegram
        bot.restrict_chat_member(message.chat.id, target.id, can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True)
        
        # 2. Удаление из БД
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
            conn.commit()
            
        bot.reply_to(message, f"🔊 <b>Мут снят</b> с {sanitize_text(get_full_user_name(target))}.")
        log_system_action(message.chat.id, message.from_user.id, "UNMUTE", f"Размучен {target.id}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка размута: {e}")

@bot.message_handler(commands=['warn'])
def command_warn(message):
    """Выдает предупреждение (варн) пользователю по реплаю."""
    if not message.reply_to_message: return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    
    target = message.reply_to_message.from_user
    reason = " ".join(message.text.split()[1:]) or "Нарушение правил чата"
    limit = 3 # Лимит варнов перед баном

    with get_db_connection() as conn:
        # 1. Добавление варна
        conn.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, target.id, message.from_user.id, reason, get_iso_now()))
        conn.commit()
        # 2. Получение текущего количества варнов
        count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id)).fetchone()[0]
    
    # 3. Удаление исходного сообщения
    try:
        bot.delete_message(message.chat.id, message.reply_to_message.message_id)
    except Exception:
        pass

    if count >= limit:
        # Если превышен лимит - бан
        try:
            bot.ban_chat_member(message.chat.id, target.id)
            bot.reply_to(message, f"⛔ <b>Бан за варны ({count}/{limit}):</b> {sanitize_text(get_full_user_name(target))}\nПричина: {reason}")
            # Очистка варнов после бана
            with get_db_connection() as conn:
                conn.execute("DELETE FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
                conn.commit()
            log_system_action(message.chat.id, message.from_user.id, "BAN_BY_WARN", f"Забанен {target.id} по лимиту варнов: {reason}")
        except Exception as e: 
            bot.reply_to(message, f"❌ Ошибка бана: {e}")
    else:
        bot.reply_to(message, f"⚠️ <b>Варн ({count}/{limit}):</b> {sanitize_text(get_full_user_name(target))}\nПричина: {reason}")
        log_system_action(message.chat.id, message.from_user.id, "WARN_ADD", f"Варн для {target.id}: {reason}. Всего: {count}")

@bot.message_handler(commands=['kick'])
def command_kick(message):
    """Кикает пользователя по реплаю."""
    if not message.reply_to_message: return
    if not check_admin_rights(message.chat.id, message.from_user.id): return
    
    target = message.reply_to_message.from_user
    
    try:
        # Кик - это временный бан, после которого сразу следует разбан.
        bot.ban_chat_member(message.chat.id, target.id)
        # Удаление исходного сообщения
        try:
            bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
        # Разбан, чтобы пользователь мог вернуться по ссылке
        bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True) 
        
        bot.reply_to(message, f"👢 <b>Кикнут:</b> {sanitize_text(get_full_user_name(target))}.")
        log_system_action(message.chat.id, message.from_user.id, "KICK", f"Кикнут {target.id}")
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка кика: {e}")

# --- ОБЩИЙ ОБРАБОТЧИК СООБЩЕНИЙ В ГРУППЕ (ПРОВЕРКА ПОДПИСКИ) ---

@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def group_message_processor(message):
    """
    Основной обработчик сообщений в группе. 
    Обновляет активность и проверяет подписки.
    """
    # 1. Обновление активности
    update_user_activity(message.from_user, message.chat.id)
    
    # 2. Проверка на админа или бота - им разрешено
    if check_admin_rights(message.chat.id, message.from_user.id) or message.from_user.is_bot:
        return

    # 3. Получение обязательных каналов для этого чата
    required_channels = get_required_channels_for_chat(message.chat.id)
    if not required_channels:
        return

    # 4. Проверка статуса подписки
    missing_channels = []
    for channel in required_channels:
        if not check_subscription_status(message.from_user.id, channel):
            missing_channels.append(channel)
    
    # 5. Если есть пропущенные каналы - удаляем сообщение и отправляем предупреждение
    if missing_channels:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            # Бот не смог удалить сообщение (нет прав, слишком старое)
            pass 
        
        warning_text = (
            f"🚫 <b>Доступ ограничен, {sanitize_text(get_full_user_name(message.from_user))}!</b>\n\n"
            "Для того чтобы писать в этот чат, необходимо подписаться на следующие каналы."
        )
        
        try:
            # Отправляем сообщение с кнопками подписки
            bot.send_message(
                message.chat.id,
                warning_text,
                reply_markup=generate_subscription_keyboard(missing_channels),
                disable_notification=True,
                parse_mode="HTML"
            )
        except Exception:
            # Невозможно отправить сообщение (например, пользователь заблокировал бота)
            pass

# --- ЗАПУСК ВЕБХУКА И СЕРВЕРА ---

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_receiver():
    """Принимает обновления от Telegram через вебхук."""
    try:
        json_update = request.get_data().decode("utf-8")
        update = Update.de_json(json_update)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Error processing update: {e}")
    return "OK", 200

@app.route("/", methods=["GET"])
def health_check():
    """Проверка работоспособности сервиса."""
    return "Service is Running", 200

def setup_webhook_connection():
    """Настраивает вебхук для бота."""
    try:
        # Сначала удаляем старый
        bot.remove_webhook()
        time.sleep(1)
        # Затем устанавливаем новый
        full_webhook_url = f"{WEBHOOK_HOST.rstrip('/')}/{TOKEN}"
        bot.set_webhook(url=full_webhook_url)
        print(f"Webhook set to: {full_webhook_url}")
    except Exception as e:
        print(f"Failed to set webhook: {e}")

if __name__ == "__main__":
    print("Initializing Database...")
    initialize_database()
    
    print("Starting background unmute worker...")
    # Запускаем фоновую задачу размута
    worker_thread = threading.Thread(target=background_unmute_worker, daemon=True)
    worker_thread.start()
    
    print("Setting up webhook...")
    # Настраиваем вебхук
    setup_webhook_connection()
    
    print(f"Starting Flask server on port {PORT}...")
    # Запускаем Flask сервер
    app.run(host="0.0.0.0", port=PORT)

