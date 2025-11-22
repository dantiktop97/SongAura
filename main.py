import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Update, ChatPermissions

TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023")) 
LOG_CHANNEL = 4902536707  
DB_PATH = os.getenv("DB_PATH", "data.db")
ADMIN_STATUSES = ("administrator", "creator")
MAX_LOG_ENTRIES = 10

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

_local_memory = {} 
BOT_USERNAME = None 

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
    },
    'en': {
        "welcome_private": "👋 <b>Hello, {user_name}!</b>\n\nI am an automated chat moderation system.\nUse the menu below to manage the bot:",
        "menu_add_group": "➕ Add to Group",
        "menu_settings": "⚙️ Group Settings",
        "menu_languages": "🌐 Language",
        "menu_admin": "🔒 Admin Menu",
        "lang_changed": "✅ Language changed to **{lang}**.",
        "lang_choose": "🌐 <b>Select Language / Виберіть мову:</b>",
        "lang_back": "⬅️ Back",
        "lang_title_ru": "🇷🇺 Russian",
        "lang_title_en": "🇬🇧 English",
        "lang_title_uk": "🇺🇦 Українська",
        "admin_panel_title": "<b>🎛 Administrator Panel</b>\nMain bot management menu.",
        "no_rights": "⛔ You do not have access rights to this menu. You are not the bot owner.",
        "group_welcome": "👋 Hi! I'm <b>{bot_name}</b>.\n\nI help manage the group and subscriptions. To configure me, go to my private chat.",
        "group_go_private": "🤖 Go to Private Chat for setup",
        "setup_info": "ℹ️ <b>Usage:</b>\n<code>/setup @channel [time]</code>\n\nExample: <code>/setup @MyChannel 1d</code>",
        "setup_error_time": "⚠️ <b>Error:</b> Invalid time format. Use: <code>30m</code>, <code>1h</code>, <code>5d</code>, etc.",
        "setup_error_not_channel": "⚠️ <b>Error:</b> This is not a channel or supergroup.",
        "setup_error_unknown_channel": "⚠️ <b>Error:</b> I cannot see this channel. Make sure it exists and the username is correct.",
        "setup_success": "✅ <b>Channel added!</b>\nSubscription to <b>{channel}</b> is now mandatory {info}.",
        "setup_info_forever": "<b>forever</b>",
        "setup_info_until": "until <b>{date}</b>",
        "unsetup_usage": "ℹ️ <b>Usage:</b> <code>/unsetup @channel</code>\n\n<i>There are no active subscription requirements in this chat.</i>",
        "unsetup_list": "ℹ️ <b>Current mandatory subscriptions:</b>\n{channels}\n\nEnter the command with the username to remove.",
        "unsetup_deleted": "🗑 <b>Subscription requirement for {channel} removed.</b>",
        "unsetup_not_found": "❌ <b>Error:</b> Subscription to {channel} not found in the mandatory list for this chat.",
        "cmd_no_reply": "↩️ Reply to the user's message.",
        "cmd_no_id_reply": "ℹ️ ID or Reply.",
        "no_admin_rights": "⛔ Only administrators can use this command.",
        "ban_success": "⛔ <b>Banned:</b> {user_name}",
        "ban_error": "❌ Ban error: {error}",
        "unban_success": "🕊 <b>Unbanned:</b> <code>{user_id}</code>",
        "unban_error": "❌ Unban error: {error}",
        "mute_error_time": "⚠️ Invalid time format. Use: <code>30m</code>, <code>1h</code>, <code>5d</code>.",
        "mute_success": "🔇 <b>Mute for {duration}:</b> {user_name}\nAutomatic unmute: {date}",
        "mute_error": "❌ Mute error: {error}",
        "unmute_success": "🔊 <b>Mute removed</b> from {user_name}.",
        "unmute_error": "❌ Unmute error: {error}",
        "warn_reason": "Chat rules violation",
        "warn_limit_ban": "⛔ <b>Ban for warns ({count}/{limit}):</b> {user_name}\nReason: {reason}",
        "warn_added": "⚠️ <b>Warn ({count}/{limit}):</b> {user_name}\nReason: {reason}",
        "kick_success": "👢 <b>Kicked:</b> {user_name}.",
        "kick_error": "❌ Kick error: {error}",
        "sub_access_denied": "🚫 <b>Access denied, {user_name}!</b>\n\nTo be able to write in this chat, you must subscribe to the following channels.",
        "sub_button_text": "👉 Subscribe to {channel}",
        "sub_button_verify": "✅ I have subscribed",
        "sub_verified": "✅ Access granted! You can now write in the chat.",
        "sub_not_all": "❌ You haven't subscribed to all channels! Recheck after subscribing.",
        "settings_info": "⚙️ <b>Group Settings</b>\n\nFuture settings for filters, greetings, and more will be here. Use /setup in the desired chat to manage subscriptions.",
    },
    'uk': {
        "welcome_private": "👋 <b>Вітаю, {user_name}!</b>\n\nЯ — автоматизована система модерації чатів.\nВикористовуйте меню нижче для керування ботом:",
        "menu_add_group": "➕ Додати до групи",
        "menu_settings": "⚙️ Налаштування групи",
        "menu_languages": "🌐 Мова",
        "menu_admin": "🔒 Адмін меню",
        "lang_changed": "✅ Мову змінено на **{lang}**.",
        "lang_choose": "🌐 <b>Оберіть мову / Choose Language / Выберите язык:</b>",
        "lang_back": "⬅️ Назад",
        "lang_title_ru": "🇷🇺 Російська",
        "lang_title_en": "🇬🇧 Англійська",
        "lang_title_uk": "🇺🇦 Українська",
        "admin_panel_title": "<b>🎛 Панель Адміністратора</b>\nГоловне меню керування ботом.",
        "no_rights": "⛔ Ви не маєте прав доступу до цього меню. Ви не власник бота.",
        "group_welcome": "👋 Привіт! Я — <b>{bot_name}</b>.\n\nЯ допомагаю керувати групою та підписками. Щоб налаштувати мене, перейдіть до ЛС.",
        "group_go_private": "🤖 Перейти до ЛС для налаштування",
        "setup_info": "ℹ️ <b>Використання:</b>\n<code>/setup @channel [час]</code>\n\nПриклад: <code>/setup @MyChannel 1d</code>",
        "setup_error_time": "⚠️ <b>Помилка:</b> Невірний формат часу. Використовуйте: <code>30m</code>, <code>1h</code>, <code>5d</code> тощо.",
        "setup_error_not_channel": "⚠️ <b>Помилка:</b> Це не канал або супергрупа.",
        "setup_error_unknown_channel": "⚠️ <b>Помилка:</b> Я не бачу цей канал. Переконайтеся, що він існує і його юзернейм коректний.",
        "setup_success": "✅ <b>Канал додано!</b>\nТепер підписка на <b>{channel}</b> обов'язкова {info}.",
        "setup_info_forever": "<b>назавжди</b>",
        "setup_info_until": "до <b>{date}</b>",
        "unsetup_usage": "ℹ️ <b>Використання:</b> <code>/unsetup @channel</code>\n\n<i>У цьому чаті немає активних вимог підписки.</i>",
        "unsetup_list": "ℹ️ <b>Поточні обов'язкові підписки:</b>\n{channels}\n\nВведіть команду з юзернеймом для видалення.",
        "unsetup_deleted": "🗑 <b>Вимога підписки на {channel} видалено.</b>",
        "unsetup_not_found": "❌ <b>Помилка:</b> Підписку на {channel} не знайдено у списку обов'язкових для цього чату.",
        "cmd_no_reply": "↩️ Відповіжте на повідомлення користувача.",
        "cmd_no_id_reply": "ℹ️ ID або відповідь.",
        "no_admin_rights": "⛔ Тільки адміністратори можуть використовувати цю команду.",
        "ban_success": "⛔ <b>Забанено:</b> {user_name}",
        "ban_error": "❌ Помилка бану: {error}",
        "unban_success": "🕊 <b>Розбанено:</b> <code>{user_id}</code>",
        "unban_error": "❌ Помилка розбану: {error}",
        "mute_error_time": "⚠️ Невірний формат часу. Використовуйте: <code>30m</code>, <code>1h</code>, <code>5d</code>.",
        "mute_success": "🔇 <b>Мут на {duration}:</b> {user_name}\nАвтоматичний розмут: {date}",
        "mute_error": "❌ Помилка муту: {error}",
        "unmute_success": "🔊 <b>Мут знято</b> з {user_name}.",
        "unmute_error": "❌ Помилка розмуту: {error}",
        "warn_reason": "Порушення правил чату",
        "warn_limit_ban": "⛔ <b>Бан за варни ({count}/{limit}):</b> {user_name}\nПричина: {reason}",
        "warn_added": "⚠️ <b>Варн ({count}/{limit}):</b> {user_name}\nПричина: {reason}",
        "kick_success": "👢 <b>Кікнуто:</b> {user_name}.",
        "kick_error": "❌ Помилка кіку: {error}",
        "sub_access_denied": "🚫 <b>Доступ обмежено, {user_name}!</b>\n\nЩоб мати можливість писати в цей чат, необхідно підписатися на наступні канали.",
        "sub_button_text": "👉 Підписатися на {channel}",
        "sub_button_verify": "✅ Я підписався",
        "sub_verified": "✅ Доступ дозволено! Можете писати в чат.",
        "sub_not_all": "❌ Ви підписалися не на всі канали! Повторіть перевірку після підписки.",
        "settings_info": "⚙️ <b>Налаштування групи</b>\n\nТут будуть майбутні налаштування фільтрів, привітань тощо. Використовуйте /setup у потрібному чаті для керування підписками.",
    },
}
DEFAULT_LANG = 'ru'
LANGUAGES = {'ru': 'Русский', 'en': 'English', 'uk': 'Українська'} 

def get_string(user_id, key):
    lang_code = get_user_language(user_id)
    return STRINGS.get(lang_code, STRINGS[DEFAULT_LANG]).get(key, STRINGS[DEFAULT_LANG].get(key, f"MISSING STRING: {key}"))

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
                expires_at TEXT,
                UNIQUE(chat_id, user_id)
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_language (
                user_id INTEGER PRIMARY KEY NOT NULL,
                lang_code TEXT DEFAULT 'ru'
            )
        """)
        conn.commit()

def get_user_language(user_id):
    with get_db_connection() as conn:
        cursor = conn.execute("SELECT lang_code FROM user_language WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        return row['lang_code'] if row and row['lang_code'] in STRINGS else DEFAULT_LANG

def set_user_language(user_id, lang_code):
    if lang_code not in STRINGS:
        lang_code = DEFAULT_LANG
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO user_language (user_id, lang_code) VALUES (?, ?)", (user_id, lang_code))
        conn.commit()
    return lang_code

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

def get_full_user_name(user):
    if user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.first_name

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
                            unmute_msg = get_string(user_lang, "unmute_success").replace("Мут снят", "Время истекло").replace("unmute_success", "Mute Expired") 
                            
                            bot.send_message(
                                mute['chat_id'], 
                                f"🔊 <b>{unmute_msg}</b> Пользователь <a href='tg://user?id={mute['user_id']}'>{mute['user_id']}</a> размучен.",
                                disable_notification=True
                            )
                            log_system_action(mute['chat_id'], mute['user_id'], "UNMUTE_AUTO", f"Автоматический размут. Истекло в {format_readable_date(mute['expires_at'])}")
                        except Exception as e:
                            print(f"Failed to unmute {mute['user_id']}: {e}")
                        finally:
                            conn.execute("DELETE FROM mutes WHERE id = ?", (mute['id'],))
                conn.commit()
        except Exception as e:
            print(f"Worker Error: {e}")
        time.sleep(20)

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
    user_lang = get_user_language(user_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
    return markup

def generate_languages_keyboard(user_id):
    user_lang = get_user_language(user_id)
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
    user_lang = get_user_language(user_id)
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
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back").replace("Назад", "В главное меню"), callback_data="main_menu"))
    return markup

def generate_management_keyboard(user_id):
    user_lang = get_user_language(user_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📋 Показать все подписки", callback_data="mng_show_subs"))
    markup.add(InlineKeyboardButton("➕ Добавить подписку (через /setup в чате)", callback_data="mng_info_add"))
    markup.add(InlineKeyboardButton("➖ Удалить подписку (по ID)", callback_data="mng_del_sub_start"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="adm_main_menu"))
    return markup

def generate_back_button(user_id, callback_data="adm_main_menu"):
    user_lang = get_user_language(user_id)
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back").replace("Назад", "Вернуться назад"), callback_data=callback_data))
    return markup

def generate_subscription_keyboard(user_id, missing_channels):
    user_lang = get_user_language(user_id)
    markup = InlineKeyboardMarkup()
    for channel in missing_channels:
        clean_name = channel.replace("@", "")
        markup.add(InlineKeyboardButton(get_string(user_id, "sub_button_text").format(channel=channel), url=f"https://t.me/{clean_name}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "sub_button_verify"), callback_data="verify_subscription"))
    return markup

def generate_delete_subscription_keyboard(user_id, subs):
    user_lang = get_user_language(user_id)
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
    except Exception as e:
        print(f"Error checking sub for {user_id} on {channel}: {e}")
        return False 

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
        still_missing = []
        for channel in required_channels:
            if not check_subscription_status(user_id, channel):
                still_missing.append(channel)
        
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
            time.sleep(0.04)
        except Exception:
            fail_count += 1
    
    result_message = f"✅ <b>Рассылка завершена!</b>\n\nУспешно: {success_count}\nОшибок (заблокировали/удалили): {fail_count}"
    bot.send_message(user_id, result_message)
    log_system_action(user_id, user_id, "BROADCAST_END", f"Рассылка завершена. Успешно: {success_count}, Ошибок: {fail_count}")

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
        required_channels = get_required_channels_for_chat(message.chat.id)
        if not required_channels:
            bot.reply_to(message, get_string(user_id, "unsetup_usage"))
            return
        
        list_text = "\n".join(required_channels)
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

@bot.message_handler(commands=['ban'])
def command_ban(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)
    
    if message.chat.type not in ['group', 'supergroup']: return
    if not message.reply_to_message:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return
    if not check_admin_rights(message.chat.id, user_id): return
    
    target_user = message.reply_to_message.from_user
    
    try:
        bot.ban_chat_member(message.chat.id, target_user.id)
        try:
            bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
            
        user_name = sanitize_text(get_full_user_name(target_user))
        bot.reply_to(message, get_string(user_id, "ban_success").format(user_name=user_name))
        log_system_action(message.chat.id, user_id, "BAN", f"Забанен {target_user.id} ({user_name})")
    except Exception as e: 
        bot.reply_to(message, get_string(user_id, "ban_error").format(error=e))

@bot.message_handler(commands=['unban'])
def command_unban(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    if message.chat.type not in ['group', 'supergroup']: return
    if not check_admin_rights(message.chat.id, user_id): return
    
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif len(message.text.split()) > 1:
        try:
            target_id = int(message.text.split()[1])
        except ValueError:
            bot.reply_to(message, get_string(user_id, "cmd_no_id_reply"))
            return

    if not target_id:
        bot.reply_to(message, get_string(user_id, "cmd_no_id_reply"))
        return

    try:
        bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
        bot.reply_to(message, get_string(user_id, "unban_success").format(user_id=target_id))
        log_system_action(message.chat.id, user_id, "UNBAN", f"Разбанен {target_id}")
    except Exception as e: 
        bot.reply_to(message, get_string(user_id, "unban_error").format(error=e))

@bot.message_handler(commands=['mute'])
def command_mute(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    if message.chat.type not in ['group', 'supergroup']: return
    if not message.reply_to_message:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply") + ". Пример: <code>/mute 1h</code>")
        return
    if not check_admin_rights(message.chat.id, user_id): return
    
    args = message.text.split()
    duration = args[1] if len(args) > 1 else "1h"
    delta = parse_time_string(duration)
    
    if not delta: 
        bot.reply_to(message, get_string(user_id, "mute_error_time"))
        return
        
    target = message.reply_to_message.from_user
    until = datetime.utcnow() + delta
    
    try:
        bot.restrict_chat_member(message.chat.id, target.id, until_date=until.timestamp(), 
            permissions=ChatPermissions(can_send_messages=False))
        
        with get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO mutes (chat_id, user_id, expires_at) VALUES (?, ?, ?)", 
                (message.chat.id, target.id, until.isoformat()))
            conn.commit()
            
        try:
            bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
            
        user_name = sanitize_text(get_full_user_name(target))
        date_str = format_readable_date(until.isoformat())
        bot.reply_to(message, get_string(user_id, "mute_success").format(duration=duration, user_name=user_name, date=date_str))
        log_system_action(message.chat.id, user_id, "MUTE", f"Замучен {target.id} на {duration}")
    except Exception as e: 
        bot.reply_to(message, get_string(user_id, "mute_error").format(error=e))

@bot.message_handler(commands=['unmute'])
def command_unmute(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    if message.chat.type not in ['group', 'supergroup']: return
    if not message.reply_to_message:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return
    if not check_admin_rights(message.chat.id, user_id): return
    
    target = message.reply_to_message.from_user
    
    try:
        bot.restrict_chat_member(message.chat.id, target.id, 
            permissions=ChatPermissions(can_send_messages=True, can_send_media_messages=True, can_send_other_messages=True, can_add_web_page_previews=True))
        
        with get_db_connection() as conn:
            conn.execute("DELETE FROM mutes WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
            conn.commit()
            
        user_name = sanitize_text(get_full_user_name(target))
        bot.reply_to(message, get_string(user_id, "unmute_success").format(user_name=user_name))
        log_system_action(message.chat.id, user_id, "UNMUTE", f"Размучен {target.id}")
    except Exception as e:
        bot.reply_to(message, get_string(user_id, "unmute_error").format(error=e))

@bot.message_handler(commands=['warn'])
def command_warn(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    if message.chat.type not in ['group', 'supergroup']: return
    if not message.reply_to_message:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return
    if not check_admin_rights(message.chat.id, user_id): return
    
    target = message.reply_to_message.from_user
    reason_default = get_string(user_id, "warn_reason")
    reason = " ".join(message.text.split()[1:]) or reason_default
    limit = 3 

    with get_db_connection() as conn:
        conn.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (message.chat.id, target.id, user_id, reason, get_iso_now()))
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id)).fetchone()[0]
    
    try:
        bot.delete_message(message.chat.id, message.reply_to_message.message_id)
    except Exception:
        pass

    user_name = sanitize_text(get_full_user_name(target))
    if count >= limit:
        try:
            bot.ban_chat_member(message.chat.id, target.id)
            bot.reply_to(message, get_string(user_id, "warn_limit_ban").format(count=count, limit=limit, user_name=user_name, reason=reason))
            with get_db_connection() as conn:
                conn.execute("DELETE FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target.id))
                conn.commit()
            log_system_action(message.chat.id, user_id, "BAN_BY_WARN", f"Забанен {target.id} по лимиту варнов: {reason}")
        except Exception as e: 
            bot.reply_to(message, get_string(user_id, "ban_error").format(error=e))
    else:
        bot.reply_to(message, get_string(user_id, "warn_added").format(count=count, limit=limit, user_name=user_name, reason=reason))
        log_system_action(message.chat.id, user_id, "WARN_ADD", f"Варн для {target.id}: {reason}. Всего: {count}")

@bot.message_handler(commands=['kick'])
def command_kick(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    if message.chat.type not in ['group', 'supergroup']: return
    if not message.reply_to_message:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return
    if not check_admin_rights(message.chat.id, user_id): return
    
    target = message.reply_to_message.from_user
    
    try:
        bot.ban_chat_member(message.chat.id, target.id)
        try:
            bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        except Exception:
            pass
        bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True) 
        
        user_name = sanitize_text(get_full_user_name(target))
        bot.reply_to(message, get_string(user_id, "kick_success").format(user_name=user_name))
        log_system_action(message.chat.id, user_id, "KICK", f"Кикнут {target.id}")
    except Exception as e:
        bot.reply_to(message, get_string(user_id, "kick_error").format(error=e))

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

    missing_channels = []
    for channel in required_channels:
        if not check_subscription_status(user_id, channel):
            missing_channels.append(channel)
    
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
