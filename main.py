import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
import json
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Update, ChatPermissions

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
SUB_CHANNEL = os.getenv("SUB_CHANNEL", "@vzref2") 
DB_PATH = os.getenv("DB_PATH", "data.db")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023")) 
LOG_CHANNEL = 4902536707  # ID для уведомлений о новых пользователях (канал или приватный чат)
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_STATUSES = ("administrator", "creator")
MAX_LOG_ENTRIES = 10

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Локальное хранилище для пошаговых действий администратора (state machine)
_local_memory = {} 
# Кэш для юзернейма бота
BOT_USERNAME = None 

# --- ЛОКАЛИЗАЦИЯ (ЯЗЫКОВОЙ СЛОВАРЬ) ---
# Ключ - код языка ('ru', 'en', 'uk'), Значение - словарь строк
STRINGS = {
    'ru': {
        "welcome_private": "👋 <b>Приветствую, {user_name}!</b>\n\nЯ — автоматизированная система модерации чатов.\nИспользуйте меню ниже для управления ботом:",
        "menu_add_group": "➕ Добавить в группу",
        "menu_settings": "⚙️ Настройки группы",
        "menu_languages": "🌐 Язык",
        "menu_admin": "🔒 Админ меню",
        "lang_changed": "✅ Язык изменен на **{lang}**.",
        "lang_choose": "🌐 <b>Выберите язык / Choose Language / Оберіть мову:</b>",
        "lang_back": "⬅️ Назад",
        "lang_title_ru": "🇷🇺 Русский",
        "lang_title_en": "🇬🇧 English",
        "lang_title_uk": "🇺🇦 Українська",
        "admin_panel_title": "<b>🎛 Панель Администратора</b>\nГлавное меню управления ботом.",
        "no_rights": "⛔ У вас нет прав доступа к этому меню. Вы не владелец бота.",
        "group_welcome": "👋 Привет! Я — <b>{bot_name}</b>.\n\nЯ помогаю управлять группой и подписками. Чтобы настроить меня, перейдите в ЛС.",
        "group_go_private": "🤖 Перейти в ЛС для настройки",
        "setup_info": "ℹ️ <b>Использование:</b>\n<code>/setup @channel [время]</code>\n\nПример: <code>/setup @MyChannel 1d</code>",
        "setup_error_time": "⚠️ <b>Ошибка:</b> Неверный формат времени. Используйте: <code>30m</code>, <code>1h</code>, <code>5d</code> и т.д.",
        "setup_error_not_channel": "⚠️ <b>Ошибка:</b> Это не канал или супергруппа.",
        "setup_error_unknown_channel": "⚠️ <b>Ошибка:</b> Я не вижу этот канал. Убедитесь, что он существует и его юзернейм корректен.",
        "setup_success": "✅ <b>Канал добавлен!</b>\nТеперь подписка на <b>{channel}</b> обязательна {info}.",
        "setup_info_forever": "<b>навсегда</b>",
        "setup_info_until": "до <b>{date}</b>",
        "unsetup_usage": "ℹ️ <b>Использование:</b> <code>/unsetup @channel</code>\n\n<i>В этом чате нет активных требований подписки.</i>",
        "unsetup_list": "ℹ️ <b>Текущие обязательные подписки:</b>\n{channels}\n\nВведите команду с юзернеймом для удаления.",
        "unsetup_deleted": "🗑 <b>Требование подписки на {channel} удалено.</b>",
        "unsetup_not_found": "❌ <b>Ошибка:</b> Подписка на {channel} не найдена в списке обязательных для этого чата.",
        "cmd_no_reply": "↩️ Ответьте на сообщение пользователя.",
        "cmd_no_id_reply": "ℹ️ ID или реплай.",
        "no_admin_rights": "⛔ Только администраторы могут использовать эту команду.",
        "ban_success": "⛔ <b>Забанен:</b> {user_name}",
        "ban_error": "❌ Ошибка бана: {error}",
        "unban_success": "🕊 <b>Разбанен:</b> <code>{user_id}</code>",
        "unban_error": "❌ Ошибка разбана: {error}",
        "mute_error_time": "⚠️ Неверный формат времени. Используйте: <code>30m</code>, <code>1h</code>, <code>5d</code>.",
        "mute_success": "🔇 <b>Мут на {duration}:</b> {user_name}\nАвтоматический размут: {date}",
        "mute_error": "❌ Ошибка мьюта: {error}",
        "unmute_success": "🔊 <b>Мут снят</b> с {user_name}.",
        "unmute_error": "❌ Ошибка размута: {error}",
        "warn_reason": "Нарушение правил чата",
        "warn_limit_ban": "⛔ <b>Бан за варны ({count}/{limit}):</b> {user_name}\nПричина: {reason}",
        "warn_added": "⚠️ <b>Варн ({count}/{limit}):</b> {user_name}\nПричина: {reason}",
        "kick_success": "👢 <b>Кикнут:</b> {user_name}.",
        "kick_error": "❌ Ошибка кика: {error}",
        "sub_access_denied": "🚫 <b>Доступ ограничен, {user_name}!</b>\n\nДля того чтобы писать в этот чат, необходимо подписаться на следующие каналы.",
        "sub_button_text": "👉 Подписаться на {channel}",
        "sub_button_verify": "✅ Я подписался",
        "sub_verified": "✅ Доступ разрешен! Можете писать в чат.",
        "sub_not_all": "❌ Вы подписались не на все каналы! Повторите проверку после подписки.",
        "settings_info": "⚙️ <b>Настройки группы</b>\n\nЗдесь в будущем будут настройки фильтров, приветствий и прочего. Для управления подписками используйте /setup в нужном чате.",
        # Новые строки для ОП
        "op_public_text": "✅ Функция проверки подписки на публичные каналы/чаты 🛡️\n\n▸ Шаг 1: Добавьте меня в ваш чат как администратора. Используйте эту ссылку для удобства! 🔗\n▸ Шаг 2: Добавьте меня в администраторы канала/чата для проверки. Поделитесь ссылкой с админом. 📩\n▸ Шаг 3: В вашем чате введите: <code>/setup @channel</code> 🚀\n\n⛔️ Для отключения:\n▸ <code>/unsetup @channel</code> ❌\n\n➕ Макс. 5 проверок одновременно!\n❌ Для отключения всех: <code>/unsetup</code>\n\n💡 Команда <code>/status</code> покажет активные проверки и таймеры. ⏰\n\nВопросы? Пишите в поддержку @support_chat. 📞",
        "op_private_text": "📢 Проверка подписки для приватных каналов/чатов 🔒\n\nШаг 1: Узнайте ID приватного канала (например, -1001234567890). 🆔\nШаг 2: В вашем чате введите: <code>/setup -1001234567890</code> 🚀\n\nЧтобы отключить: <code>/unsetup -1001234567890</code> ❌\n\n💡 Используйте <code>/status</code> для меню просмотра и редактирования проверок. 📋",
        "op_invite_text": "🔗 Проверка подписки на пригласительные ссылки 📩\n\nШаг 1: Узнайте ID приватного канала. 🆔\nШаг 2: В чате: <code>/setup -1001234567890 https://t.me/+invite_link</code> 🚀\n\nОтключить: <code>/unsetup -1001234567890</code> ❌\n\nМожно задать цель подписок: <code>/setup -1001234567890 https://t.me/+invite_link 100</code> 🎯\n\n🕒 Таймер: <code>/setup -1001234567890 https://t.me/+invite_link 1d</code> ⏰ (s/m/h/d)\n\n💡 <code>/status</code> для управления. 📋",
        "no_active_subs": "📋 Нет активных проверок на подписку. 🚫"
    },
    'en': {
        # ... (оставить как есть, добавить аналогично если нужно, но фокус на ru)
    },
    'uk': {
        # ... 
    },
}
DEFAULT_LANG = 'ru' # Язык по умолчанию
LANGUAGES = {'ru': 'Русский', 'en': 'English', 'uk': 'Українська'} # Отображаемые названия

def get_string(user_id, key):
    """Получает строку локализации для пользователя."""
    lang_code = get_user_language(user_id)
    return STRINGS.get(lang_code, STRINGS[DEFAULT_LANG]).get(key, STRINGS[DEFAULT_LANG].get(key, f"MISSING STRING: {key}"))

# --- БАЗА ДАННЫХ ---
def get_db_connection():
    """Получает соединение с базой данных."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    """Инициализирует все необходимые таблицы."""
    with get_db_connection() as conn:
        # Таблица для обязательных подписок
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
        # НОВАЯ ТАБЛИЦА: для хранения языка пользователя
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_language (
                user_id INTEGER PRIMARY KEY NOT NULL,
                lang_code TEXT DEFAULT 'ru'
            )
        """)
        conn.commit()

def get_user_language(user_id):
    """Получает код языка для пользователя."""
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT lang_code FROM user_language WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row['lang_code'] if row and row['lang_code'] in STRINGS else DEFAULT_LANG

def set_user_language(user_id, lang_code):
    """Устанавливает код языка для пользователя."""
    if lang_code not in STRINGS:
        lang_code = DEFAULT_LANG
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO user_language (user_id, lang_code) VALUES (?, ?)", (user_id, lang_code))
        conn.commit()
    return lang_code

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
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "навсегда"

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
            cursor = conn.execute("SELECT id FROM members WHERE user_id = ? AND chat_id = ?", (user.id, chat_id))
            exists = cursor.fetchone()
            
            username = user.username or ""
            first_name = user.first_name or ""
            last_name = user.last_name or ""

            if exists:
                conn.execute("""
                    UPDATE members SET 
                    username = ?, first_name = ?, last_name = ?, messages_count = messages_count + 1, last_seen = ? 
                    WHERE id = ?
                """, (username, first_name, last_name, get_iso_now(), exists['id']))
            else:
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
                expired_mutes = conn.execute("SELECT id, chat_id, user_id, expires_at FROM mutes WHERE expires_at IS NOT NULL").fetchall()
                current_time = datetime.utcnow()
                
                for mute in expired_mutes:
                    expiry = parse_iso_datetime(mute['expires_at'])
                    if expiry and expiry <= current_time:
                        try:
                            bot.restrict_chat_member(
                                mute['chat_id'], 
                                mute['user_id'], 
                                permissions=ChatPermissions(
                                    can_send_messages=True,
                                    can_send_media_messages=True,
                                    can_send_other_messages=True,
                                    can_add_web_page_previews=True
                                )
                            )
                            user_lang = get_user_language(mute['user_id'])
                            unmute_msg = get_string(mute['user_id'], "unmute_success").replace("{user_name}", str(mute['user_id']))
                            bot.send_message(
                                mute['chat_id'], 
                                f"🔊 {unmute_msg} (авто-размут).",
                                disable_notification=True
                            )
                            log_system_action(mute['chat_id'], mute['user_id'], "UNMUTE_AUTO", f"Авто-размут после {format_readable_date(mute['expires_at'])}")
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
    user_lang = get_user_language(user_id)
    username = get_bot_username()
    markup = InlineKeyboardMarkup()
    
    add_url = f"https://t.me/{username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat+promote_members"
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_add_group"), url=add_url))
    
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_settings"), callback_data="settings_menu"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_languages"), callback_data="languages_menu"))
    
    if user_id == ADMIN_ID:
        markup.add(InlineKeyboardButton(get_string(user_id, "menu_admin"), callback_data="adm_main_menu"))
        
    return markup

def generate_settings_keyboard(user_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
    return markup

def generate_languages_keyboard(user_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton(get_string(user_id, "lang_title_ru"), callback_data="lang_select:ru"),
        InlineKeyboardButton(get_string(user_id, "lang_title_en"), callback_data="lang_select:en")
    )
    markup.row(
        InlineKeyboardButton(get_string(user_id, "lang_title_uk"), callback_data="lang_select:uk")
    )
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
    return markup

def generate_main_admin_keyboard(user_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
        InlineKeyboardButton("📡 Рассылка", callback_data="adm_broadcast")
    )
    markup.row(
        InlineKeyboardButton("📋 Логи системы", callback_data="adm_logs"),
        InlineKeyboardButton("🛡 Управление подписками", callback_data="adm_manage_subs")
    )
    markup.row(
        InlineKeyboardButton("👤 Проверка пользователей", callback_data="adm_user_check")
    )
    markup.row(
        InlineKeyboardButton("🛡️ ОП (Проверка подписки)", callback_data="adm_op_check")
    )
    markup.add(InlineKeyboardButton("❌ Закрыть", callback_data="close_panel"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
    return markup

def generate_op_menu(user_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("📢 Публичные чаты/группы", callback_data="public_op")
    )
    markup.row(
        InlineKeyboardButton("🔒 Приватные чаты/группы", callback_data="private_op")
    )
    markup.row(
        InlineKeyboardButton("🔗 ОП (Пригласительная ссылка)", callback_data="invite_op")
    )
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="adm_main_menu"))
    return markup

def generate_back_button(user_id, callback_data="adm_main_menu"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data=callback_data))
    return markup

def generate_management_keyboard(user_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📋 Показать все подписки", callback_data="mng_show_subs"))
    markup.add(InlineKeyboardButton("➕ Добавить подписку (через /setup в чате)", callback_data="mng_info_add"))
    markup.add(InlineKeyboardButton("➖ Удалить подписку (по ID)", callback_data="mng_del_sub_start"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="adm_main_menu"))
    return markup

def generate_subscription_keyboard(user_id, missing_channels):
    markup = InlineKeyboardMarkup()
    for channel in missing_channels:
        clean_name = channel.replace("@", "")
        markup.add(InlineKeyboardButton(get_string(user_id, "sub_button_text").format(channel=channel), url=f"https://t.me/{clean_name}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "sub_button_verify"), callback_data="verify_subscription"))
    return markup

def generate_delete_subscription_keyboard(user_id, subs):
    markup = InlineKeyboardMarkup()
    for sub in subs:
        chat_name = f"Chat_{sub['chat_id']}"
        try:
            chat_info = bot.get_chat(sub['chat_id'])
            chat_name = sanitize_text(chat_info.title)
        except Exception:
            pass

        display_name = f"[{sub['id']}] {sub['channel']} в {chat_name}"
        markup.add(InlineKeyboardButton(display_name, callback_data=f"mng_del_sub:{sub['id']}"))
    
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="adm_manage_subs"))
    return markup

# --- ЛОГИКА ПРОВЕРКИ ПОДПИСОК ---
def get_required_subs_for_chat(chat_id):
    """Получает список активных обязательных каналов с expires для чата."""
    with get_db_connection() as conn:
        current_time = get_iso_now()
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND expires IS NOT NULL AND expires <= ?", (chat_id, current_time))
        conn.commit()
        rows = conn.execute("SELECT channel, expires FROM required_subs WHERE chat_id = ?", (chat_id,)).fetchall()
    return rows

def get_required_channels_for_chat(chat_id):
    rows = get_required_subs_for_chat(chat_id)
    return [row['channel'] for row in rows]

def check_subscription_status(user_id, channel):
    try:
        status = bot.get_chat_member(channel, user_id).status
        return status not in ['left', 'kicked']
    except Exception as e:
        print(f"Error checking sub for {user_id} on {channel}: {e}")
        return False 

# --- ОБРАБОТЧИК CALLBACK (КНОПОК) ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query_handler(call: CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data
    user_lang = get_user_language(user_id)

    if data == "main_menu":
        _local_memory.pop(user_id, None)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=get_string(user_id, "welcome_private").format(user_name=sanitize_text(call.from_user.first_name)),
            reply_markup=generate_start_keyboard(user_id)
        )
        return

    if data == "settings_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=get_string(user_id, "settings_info"),
            reply_markup=generate_settings_keyboard(user_id)
        )
        return

    if data == "languages_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=get_string(user_id, "lang_choose"),
            reply_markup=generate_languages_keyboard(user_id)
        )
        return
    
    if data.startswith("lang_select:"):
        new_lang_code = data.split(":")[1]
        set_user_language(user_id, new_lang_code)
        lang_name = LANGUAGES.get(new_lang_code, 'Unknown')
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=get_string(user_id, "welcome_private").format(user_name=sanitize_text(call.from_user.first_name)) + "\n\n" + get_string(user_id, "lang_changed").format(lang=lang_name),
            reply_markup=generate_start_keyboard(user_id)
        )
        bot.answer_callback_query(call.id, get_string(user_id, "lang_changed").format(lang=lang_name).replace("**", ""), show_alert=True)
        return
    
    if data == "close_panel":
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            bot.answer_callback_query(call.id, "Панель закрыта.", show_alert=False)
        return

    if data == "verify_subscription":
        required_channels = get_required_channels_for_chat(call.message.chat.id)
        still_missing = [channel for channel in required_channels if not check_subscription_status(user_id, channel)]
        
        if not still_missing:
            try:
                bot.delete_message(call.message.chat.id, msg_id)
                bot.answer_callback_query(call.id, get_string(user_id, "sub_verified"), show_alert=False)
            except Exception:
                bot.answer_callback_query(call.id, get_string(user_id, "sub_verified"), show_alert=False)
        else:
            bot.answer_callback_query(call.id, get_string(user_id, "sub_not_all"), show_alert=True)
        return

    if user_id != ADMIN_ID:
        bot.answer_callback_query(call.id, get_string(user_id, "no_rights"), show_alert=True)
        return
    
    _local_memory.pop(user_id, None) 

    if data == "adm_main_menu":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=get_string(user_id, "admin_panel_title"),
            reply_markup=generate_main_admin_keyboard(user_id)
        )

    elif data == "adm_stats":
        with get_db_connection() as conn:
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
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=stats_text, reply_markup=generate_back_button(user_id))

    elif data == "adm_logs":
        with get_db_connection() as conn:
            logs = conn.execute(f"SELECT action_type, details, created_at FROM system_logs ORDER BY id DESC LIMIT {MAX_LOG_ENTRIES}").fetchall()
        
        log_text = f"<b>📋 Последние {MAX_LOG_ENTRIES} действий системы:</b>\n\n"
        if not logs:
            log_text += "<i>Логи пока пусты.</i>"
        else:
            for log in logs:
                dt = format_readable_date(log['created_at'])
                details = sanitize_text(log['details'])
                log_text += f"🔹 <code>{dt}</code>\n   └ <b>{log['action_type']}</b>: {details[:60]}{'...' if len(details) > 60 else ''}\n"
        
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=log_text, reply_markup=generate_back_button(user_id))

    elif data == "adm_manage_subs":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🛡 Управление обязательными подписками</b>\n\nЗдесь вы можете посмотреть и удалить активные требования подписки.",
            reply_markup=generate_management_keyboard(user_id)
        )

    elif data == "mng_info_add":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>ℹ️ Добавление подписки</b>\n\n"
                 "Чтобы добавить обязательную подписку для группы, вам нужно использовать команду <code>/setup</code> <b>в самой группе</b>, где бот является администратором.\n\n"
                 "<b>Формат:</b> <code>/setup @username_канала [время_действия]</code>\n"
                 "Пример: <code>/setup @MyChannel 1d</code> (на 1 день)\n"
                 "Пример: <code>/setup @MyChannel</code> (навсегда)",
            reply_markup=generate_back_button(user_id, "adm_manage_subs")
        )

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
            reply_markup=generate_back_button(user_id, "adm_manage_subs")
        )

    elif data == "mng_del_sub_start":
        with get_db_connection() as conn:
            subs = conn.execute("SELECT id, chat_id, channel, expires FROM required_subs ORDER BY id DESC LIMIT 50").fetchall()
        
        if not subs:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_id, 
                text="<b>❌ Нет подписок для удаления.</b>", 
                reply_markup=generate_back_button(user_id, "adm_manage_subs")
            )
            return
            
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>➖ Выберите подписку для удаления:</b>\n\n<i>Отображаются последние 50 записей.</i>",
            reply_markup=generate_delete_subscription_keyboard(user_id, subs)
        )

    elif data.startswith("mng_del_sub:"):
        sub_id = data.split(":")[1]
        try:
            sub_id = int(sub_id)
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Некорректный ID.", show_alert=True)
            return

        with get_db_connection() as conn:
            cursor = conn.execute("SELECT chat_id, channel FROM required_subs WHERE id = ?", (sub_id,))
            sub_info = cursor.fetchone()
            
            if sub_info:
                conn.execute("DELETE FROM required_subs WHERE id = ?", (sub_id,))
                conn.commit()
                log_system_action(sub_info['chat_id'], user_id, "DEL_SUB", f"Удалена подписка [ID:{sub_id}] {sub_info['channel']}")
                bot.answer_callback_query(call.id, f"✅ Подписка [ID:{sub_id}] удалена.", show_alert=False)
            else:
                bot.answer_callback_query(call.id, f"❌ Подписка [ID:{sub_id}] не найдена.", show_alert=True)
                
        call.data = "adm_manage_subs"
        callback_query_handler(call) 

    elif data == "adm_broadcast":
        _local_memory.pop(user_id, None)
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>📡 Режим рассылки</b>\n\nОтправьте сообщение (текст, фото, видео, анимация), и оно будет разослано всем уникальным пользователям из базы данных.\n\n<i>Нажмите 'Назад' для отмены.</i>",
            reply_markup=generate_back_button(user_id)
        )
        _local_memory[user_id] = "waiting_broadcast"

    elif data == "adm_user_check":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>👤 Проверка пользователя</b>\n\nОтправьте ID пользователя для просмотра статистики.",
            reply_markup=generate_back_button(user_id)
        )
        _local_memory[user_id] = "waiting_user_id"

    elif data == "adm_op_check":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="<b>🛡️ ОП (Проверка подписки)</b>\n\nВыберите тип:",
            reply_markup=generate_op_menu(user_id)
        )

    elif data in ["public_op", "private_op", "invite_op"]:
        if data == "public_op":
            text = get_string(user_id, "op_public_text")
            back_data = "adm_op_check"
        elif data == "private_op":
            text = get_string(user_id, "op_private_text")
            back_data = "adm_op_check"
        elif data == "invite_op":
            text = get_string(user_id, "op_invite_text")
            back_data = "adm_op_check"
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=text,
            reply_markup=generate_back_button(user_id, back_data)
        )

# --- ОБРАБОТЧИКИ СООБЩЕНИЙ ---
@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_broadcast", content_types=['text', 'photo', 'video', 'animation', 'sticker', 'document'])
def process_broadcast(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return
    _local_memory.pop(user_id, None) 
    
    bot.send_message(user_id, "⏳ <b>Начинаю рассылку...</b> Это может занять время.")
    
    success_count = 0
    fail_count = 0
    
    with get_db_connection() as conn:
        users = conn.execute("SELECT DISTINCT user_id FROM members").fetchall()
    
    for user_row in users:
        target_id = user_row['user_id']
        if target_id == user_id: continue

        try:
            bot.copy_message(target_id, message.chat.id, message.message_id)
            success_count += 1
            time.sleep(0.05)
        except Exception:
            fail_count += 1
    
    result_message = f"✅ <b>Рассылка завершена!</b>\n\nУспешно: {success_count}\nОшибок: {fail_count}"
    bot.send_message(user_id, result_message)
    log_system_action(user_id, user_id, "BROADCAST_END", f"Успешно: {success_count}, Ошибок: {fail_count}")

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_user_id", content_types=['text'])
def process_user_check(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return
    _local_memory.pop(user_id, None)
    
    try:
        target_id = int(message.text.strip())
    except ValueError:
        bot.reply_to(message, "❌ Некорректный ID. Попробуйте снова.")
        return
    
    with get_db_connection() as conn:
        member_rows = conn.execute("SELECT chat_id, messages_count, last_seen FROM members WHERE user_id = ?", (target_id,)).fetchall()
    
    if not member_rows:
        bot.reply_to(message, f"❌ Пользователь {target_id} не найден в базе.")
        return
    
    try:
        user_info = bot.get_user(target_id)
        name = get_full_user_name(user_info)
        username = user_info.username or "нет"
    except Exception:
        name = "Неизвестно"
        username = "нет"
    
    text = f"👤 Пользователь: {name} @{username} ID: {target_id}\n\n"
    
    for row in member_rows:
        try:
            chat_info = bot.get_chat(row['chat_id'])
            chat_name = chat_info.title or "Приватный чат"
            member = bot.get_chat_member(row['chat_id'], target_id)
            status = member.status  # member, administrator, creator etc.
        except Exception:
            chat_name = "Неизвестный чат"
            status = "неизвестно"
        
        warns_count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (row['chat_id'], target_id)).fetchone()[0]
        mute = conn.execute("SELECT expires_at FROM mutes WHERE chat_id = ? AND user_id = ?", (row['chat_id'], target_id)).fetchone()
        mute_str = f"Мут до {format_readable_date(mute['expires_at'])}" if mute else "Нет мьюта"
        
        required_channels = get_required_channels_for_chat(row['chat_id'])
        subs_status = "\n".join([f"{ch}: {'✅' if check_subscription_status(target_id, ch) else '❌'}" for ch in required_channels]) or "Нет обязательных подписок"
        
        text += f"💬 Чат: {chat_name} (ID: {row['chat_id']})\n"
        text += f"Статус: {status}\n"
        text += f"Сообщений: {row['messages_count']}\n"
        text += f"Последняя активность: {format_readable_date(row['last_seen'])}\n"
        text += f"Варны: {warns_count}\n"
        text += f"Мут: {mute_str}\n"
        text += f"Подписки:\n{subs_status}\n\n"
    
    bot.reply_to(message, text)

# --- КОМАНДЫ ---
@bot.message_handler(commands=['start'])
def command_start_handler(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)
    
    if message.chat.type in ['group', 'supergroup']:
        bot_info = bot.get_me()
        
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass
        
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(get_string(user_id, "group_go_private"), url=f"https://t.me/{bot_info.username}?start=settings"))
        
        bot.send_message(
            message.chat.id,
            get_string(user_id, "group_welcome").format(bot_name=bot_info.first_name),
            reply_markup=kb,
        )
        return

    if message.chat.type == 'private':
        welcome_msg = get_string(user_id, "welcome_private").format(user_name=sanitize_text(get_full_user_name(message.from_user)))
        bot.send_message(
            message.chat.id, 
            welcome_msg, 
            reply_markup=generate_start_keyboard(user_id)
        )
        # Уведомление о новом пользователе
        name = get_full_user_name(message.from_user)
        username = message.from_user.username or "нет"
        try:
            bot.send_message(LOG_CHANNEL, f"Новый пользователь: {name} @{username} ID: {user_id}")
        except Exception as e:
            print(f"Error sending to log channel: {e}")

@bot.message_handler(commands=['setup'])
def command_setup(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)
    
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "ℹ️ Эта команда работает только в группах.")
        return
        
    if not check_admin_rights(message.chat.id, user_id): 
        bot.reply_to(message, get_string(user_id, "no_admin_rights"))
        return
        
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, get_string(user_id, "setup_info"))
        return
        
    channel = args[1]
    duration_str = args[2] if len(args) > 2 else None
    expiry_iso = None
    
    if duration_str:
        delta = parse_time_string(duration_str)
        if delta: 
            expiry_iso = (datetime.utcnow() + delta).isoformat()
        else:
            bot.reply_to(message, get_string(user_id, "setup_error_time"))
            return

    try:
        chat_info = bot.get_chat(channel)
        if chat_info.type not in ['channel', 'supergroup']:
             bot.reply_to(message, get_string(user_id, "setup_error_not_channel"))
             return
    except Exception as e:
        bot.reply_to(message, get_string(user_id, "setup_error_unknown_channel"))
        log_system_action(message.chat.id, user_id, "SETUP_FAIL", f"Не удалось добавить канал {channel}. Ошибка: {e}")
        return
        
    with get_db_connection() as conn:
        conn.execute("INSERT INTO required_subs (chat_id, channel, expires, added_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, channel, expiry_iso, user_id, get_iso_now()))
        conn.commit()
        
    if expiry_iso:
        info = get_string(user_id, "setup_info_until").format(date=format_readable_date(expiry_iso))
    else:
        info = get_string(user_id, "setup_info_forever")
        
    bot.reply_to(message, get_string(user_id, "setup_success").format(channel=channel, info=info))
    log_system_action(message.chat.id, user_id, "SETUP_ADD", f"Добавлен канал: {channel} {info}")

@bot.message_handler(commands=['unsetup'])
def command_unsetup(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)
    
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "ℹ️ Эта команда работает только в группах.")
        return
        
    if not check_admin_rights(message.chat.id, user_id): 
        bot.reply_to(message, get_string(user_id, "no_admin_rights"))
        return
        
    args = message.text.split()
    if len(args) < 2:
        required_rows = get_required_subs_for_chat(message.chat.id)
        if not required_rows:
            bot.reply_to(message, get_string(user_id, "unsetup_usage"))
            return
        
        list_text = "\n".join([row['channel'] for row in required_rows])
        bot.reply_to(message, get_string(user_id, "unsetup_list").format(channels=list_text))
        return
        
    channel = args[1]
    with get_db_connection() as conn:
        cursor = conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel))
        conn.commit()
        
    if cursor.rowcount > 0:
        bot.reply_to(message, get_string(user_id, "unsetup_deleted").format(channel=channel))
        log_system_action(message.chat.id, user_id, "SETUP_DEL", f"Удален канал: {channel}")
    else:
        bot.reply_to(message, get_string(user_id, "unsetup_not_found").format(channel=channel))

@bot.message_handler(commands=['status'])
def command_status(message):
    if message.chat.type not in ['group', 'supergroup']:
        return
    
    user_id = message.from_user.id
    if not check_admin_rights(message.chat.id, user_id):
        return
    
    required_rows = get_required_subs_for_chat(message.chat.id)
    if not required_rows:
        bot.reply_to(message, get_string(user_id, "no_active_subs"))
        return
    
    text = f"📋 Активные проверки ({len(required_rows)}):\n"
    for i, row in enumerate(required_rows, 1):
        exp_str = f"— до {format_readable_date(row['expires'])}" if row['expires'] else "— навсегда"
        ch = row['channel'].lstrip('@')
        text += f"{i}. {row['channel']} {exp_str}\n/unsetup {ch} — Убрать ОП\n———————————————\n"
    
    bot.reply_to(message, text)

@bot.message_handler(commands=['ban'])
def command_ban(message):
    # ... (оставить как есть)

@bot.message_handler(commands=['unban'])
def command_unban(message):
    # ... 

@bot.message_handler(commands=['mute'])
def command_mute(message):
    # ... 

@bot.message_handler(commands=['unmute'])
def command_unmute(message):
    # ... 

@bot.message_handler(commands=['warn'])
def command_warn(message):
    # ... 

@bot.message_handler(commands=['kick'])
def command_kick(message):
    # ... 

# --- ОБЩИЙ ОБРАБОТЧИК СООБЩЕНИЙ В ГРУППЕ ---
@bot.message_handler(func=lambda m: m.chat.type in ['group', 'supergroup'])
def group_message_processor(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    update_user_activity(message.from_user, message.chat.id)
    
    if check_admin_rights(message.chat.id, user_id) or message.from_user.is_bot:
        return

    required_channels = get_required_channels_for_chat(message.chat.id)
    if not required_channels:
        return

    missing_channels = [channel for channel in required_channels if not check_subscription_status(user_id, channel)]
    
    if missing_channels:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            pass 
        
        warning_text = get_string(user_id, "sub_access_denied").format(user_name=sanitize_text(get_full_user_name(message.from_user)))
        
        try:
            bot.send_message(
                message.chat.id,
                warning_text,
                reply_markup=generate_subscription_keyboard(user_id, missing_channels),
                disable_notification=True,
            )
        except Exception:
            pass

# --- ЗАПУСК ---
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook_receiver():
    try:
        json_update = request.get_data().decode("utf-8")
        update = Update.de_json(json_update)
        bot.process_new_updates([update])
    except Exception as e:
        print(f"Error processing update: {e}")
    return "OK", 200

@app.route("/", methods=["GET"])
def health_check():
    return "Service is Running", 200

def setup_webhook_connection():
    try:
        bot.remove_webhook()
        time.sleep(1)
        full_webhook_url = f"{WEBHOOK_HOST.rstrip('/')}/{TOKEN}"
        bot.set_webhook(url=full_webhook_url)
        print(f"Webhook set to: {full_webhook_url}")
    except Exception as e:
        print(f"Failed to set webhook: {e}")

if __name__ == "__main__":
    print("Initializing Database...")
    initialize_database()
    
    print("Starting background unmute worker...")
    worker_thread = threading.Thread(target=background_unmute_worker, daemon=True)
    worker_thread.start()
    
    print("Setting up webhook...")
    setup_webhook_connection()
    
    print(f"Starting Flask server on port {PORT}...")
    app.run(host="0.0.0.0", port=PORT)
