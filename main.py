import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Update, ChatPermissions, ReplyKeyboardRemove

TOKEN = os.getenv("PLAY") or "YOUR_TOKEN_HERE"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
LOG_CHANNEL = 4902536707  
DB_PATH = os.getenv("DB_PATH", "data.db")
ADMIN_STATUSES = ("administrator", "creator")
MAX_LOG_ENTRIES = 10
BOT_USERNAME = "Subscribe_piarbot"
MAX_SUBS = 5  # Максимум проверок ОП

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

_local_memory = {}  # Локальная память для состояний

STRINGS = {
    'ru': {
        "welcome_private": "👋 <b>Добро пожаловать, {user_name}!</b>\n\n<b>SUB PR — бот для управления подписками, безопасностью чатов и модерацией.</b>\n\n<b>Функции:</b>\n- Настройка проверок подписки (ОП)\n- Анти-флуд\n- Авто-удаление сообщений\n- Модерация (бан/кик/мут/варн)\n- Приветствия и правила\n- Поддержка\n- Профиль\n- Информация\n- Выбор языка\n\nИспользуйте меню ниже для управления ботом:",
        "menu_add_group": "➕ Добавить в группу",
        "menu_settings": "⚙ Настройки группы",
        "menu_auto_delete": "🧹 Авто-удаление",
        "menu_welcome_rules": "📝 Приветствия и правила",
        "menu_info": "💬 Информация",
        "menu_support": "🛟 Поддержка",
        "menu_profile": "👤 Профиль",
        "menu_languages": "🌍 Язык",
        "menu_admin": "🔒 Админ меню",
        "menu_user_check": "🔍 Проверка пользователя",
        "menu_group_settings": "⚙️ Настройки групп",
        "menu_manage_subs": "🛡 Управление подписками",
        "lang_changed": "✅ Язык изменен на **{lang}**.",
        "lang_choose": "🌐 <b>Выберите язык / Choose Language / Оберіть мову:</b>",
        "lang_back": "🔙 Назад",
        "lang_title_ru": "🇷🇺 Русский",
        "lang_title_en": "🇺🇸 English",
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
        "ban_success": "⛔ <b>Забанен:</b> {user_name}\nПричина: {reason}",
        "ban_error": "❌ Ошибка бана: {error}",
        "unban_success": "🕊 <b>Разбанен:</b> <code>{user_id}</code>",
        "unban_error": "❌ Ошибка разбана: {error}",
        "mute_error_time": "⚠️ Неверный формат времени. Используйте: <code>30m</code>, <code>1h</code>, <code>5d</code>.",
        "mute_success": "🔇 <b>Мут на {duration}:</b> {user_name}\nАвтоматический размут: {date}\nПричина: {reason}",
        "mute_error": "❌ Ошибка мьюта: {error}",
        "unmute_success": "🔊 <b>Мут снят</b> с {user_name}.",
        "unmute_error": "❌ Ошибка размута: {error}",
        "warn_reason": "Нарушение правил чата",
        "warn_limit_ban": "⛔ <b>Бан за варны ({count}/{limit}):</b> {user_name}\nПричина: {reason}",
        "warn_added": "⚠️ <b>Варн ({count}/{limit}):</b> {user_name}\nПричина: {reason}",
        "kick_success": "👢 <b>Кикнут:</b> {user_name}.\nПричина: {reason}",
        "kick_error": "❌ Ошибка кика: {error}",
        "sub_access_denied": "🚫 <b>Доступ ограничен, {user_name}!</b>\n\nДля того чтобы писать в этот чат, необходимо подписаться на следующие каналы.",
        "sub_button_text": "👉 Подписаться на {channel}",
        "sub_button_verify": "✅ Я подписался",
        "sub_verified": "✅ Доступ разрешен! Можете писать в чат.",
        "sub_not_all": "❌ Вы подписались не на все каналы! Повторите проверку после подписки.",
        "settings_info": "⚙️ <b>Настройки группы</b>\n\nЗдесь вы можете настроить фильтры, приветствия и подписки. Используйте /setup в чате.",
        "support_prompt": "📞 <b>Поддержка</b>\n\nНапишите ваше сообщение для поддержки:",
        "support_received": "✅ Ваше сообщение отправлено в поддержку! Ожидайте ответа.",
        "support_from_user": "📩 Сообщение от пользователя {user_name} (@{username}, ID: {user_id}):\n\n{text}",
        "support_reply": "Ответить",
        "support_dismiss": "Отклонить",
        "support_response": "📨 <b>Ответ от поддержки:</b>\n\n{text}",
        "user_check_prompt": "🔍 <b>Проверка пользователя</b>\n\nВведите ID или @username:",
        "user_check_not_found": "❌ Пользователь не найден.",
        "user_check_info": "<b>Информация о пользователе:</b>\nID: {user_id}\nИмя: {first_name}\nФамилия: {last_name}\nUsername: @{username}\n\n<b>Чаты:</b>\n{chats}\n\n<b>Варны:</b> {warns}\n<b>Мьюты:</b> {mutes}",
        "group_settings_title": "<b>⚙️ Настройки групп</b>\n\nВыберите группу:",
        "group_settings_details": "<b>Настройки для {chat_title} (ID: {chat_id})\nТип: {chat_type}\nСтатус: {status}\nДобавил: {added_by}</b>\n\n<b>Функции:</b>\n- ОП (Публичный канал): {op_pub}\n- ОП (Приватный канал): {op_priv}\n- ОП (Инвайт-ссылка): {op_inv}\n- Анти-флуд: {flood}\n- Авто-удаление сообщений: {auto_del}\n- Приветствие новых участников: {welcome}\n- Правила группы: {rules}\n- Служебные сообщения: {service}",
        "anti_flood_on": "✅ Антифлуд включен.",
        "anti_flood_off": "❌ Антифлуд выключен.",
        "set_welcome_success": "✅ Приветствие установлено.",
        "set_rules_success": "✅ Правила установлены.",
        "rules": "<b>Правила чата:</b>\n{text}",
        "welcome_new_member": "👋 Добро пожаловать, {user_name}!\n\n{rules}",
        "no_bot_admin": "<b>⚠️ Бот не админ в {channel}.</b>\n\n<b>Добавьте в админы сначала.</b>",
        "status_text": "<b>📋 Активные проверки:</b>\n\n{list}",
        "status_empty": "<i>Нет активных проверок.</i>",
        "profile_text": "<b>💳 Ваш профиль</b>\n━━━━━━━━━━━━━━━\n🆔 ID: {user_id}\n👤 Ник: @{username}\n📅 Регистрация: {reg_date}\n━━━━━━━━━━━━━━━\n<b>Ваши активные чаты:</b>\n{chats}",
        "op_public": "✅ <b>Функция проверки подписки на публичные каналы/чаты 🛡️</b>\n\n"
                     "▸ <b>Шаг 1:</b> Добавьте меня в админы канала/чата для проверки.\n"
                     "▸ <b>Шаг 2:</b> В вашем чате: <code>/setup @channel</code> и время (60s, 60m, 24h, 1d).\n\n"
                     "<b>⛔ Для отключения:</b> <code>/unsetup @channel</code> ❌\n\n"
                     "<b>➕ Макс. 5 проверок!</b>\n\n"
                     "<b>💡 /status</b> покажет активные проверки и таймеры. ⏰\n\n"
                     "<b>Вопросы? В поддержку 📞</b>",
        "op_private": "<b>📢 Проверка подписки для приватных каналов/чатов:</b>\n\n"
                      "<b>Шаг 1:</b> Узнайте ID приватного канала.\n"
                      "<b>Шаг 2:</b> В чате: <code>/setup 1001994526641</code>\n\n"
                      "<b>Отключить:</b> <code>/unsetup 1001994526641</code>\n\n"
                      "<b>💡 /status</b> для меню просмотра и редактирования.",
        "op_invite": "<b>🔗 Проверка подписки на пригласительные ссылки.</b>\n\n"
                     "<b>Шаг 1:</b> Узнайте ID приватного канала.\n"
                     "<b>Шаг 2:</b> <code>/setup 1001994526641 https://t.me/+Link</code>\n\n"
                     "<b>Отключить:</b> <code>/unsetup 1001994526641</code>\n\n"
                     "<b>Лимит подписок:</b> <code>/setup ... 100</code>\n"
                     "<b>Таймер:</b> <code>/setup ... 1d</code> (s/m/h/d)\n\n"
                     "<b>💡 /status</b> для управления.",
        "op_error": "❌ Я не могу установить проверку подписки. Причина: я не администратор канала/чата {channel}.",
        "op_max": "❌ Превышено максимальное количество проверок (5). Удалите старые через /unsetup.",
        "op_invalid_format": "❌ Неправильный формат команды. Используйте /setup @channel или /setup ID [ссылка] [лимит] [время].",
        "op_group_list": "<b>Список ваших групп:</b>\n\n{chats}",
        "antiflood_menu": "<b>🚫 Анти-флуд</b>\n\nВыберите лимит:\n- 3 сообщения / 5 сек\n- 5 сообщений / 10 сек\n- 10 сообщений / 30 сек\n\nДействие: {action}",
        "antiflood_action_warn": "⚠ Предупреждение",
        "antiflood_action_mute": "🔇 Мут",
        "antiflood_action_delete": "🧹 Удаление сообщений",
        "antiflood_action_off": "❌ Отключить",
        "antiflood_set": "✅ Анти-флуд установлен: {limit} сообщений / {time} сек. Действие: {action}.",
        "autodel_menu": "<b>🧹 Авто-удаление</b>\n\nВыберите тип сообщений для удаления:\n- ОП\n- Анти-флуд\n- Служебные (покинул, присоединился, закрепил, смена фото/названия, уведомления Telegram, сообщения бота)\n\nТаймер: {timer}",
        "autodel_timer_10s": "10s",
        "autodel_timer_30s": "30s",
        "autodel_timer_1m": "1m",
        "autodel_timer_15m": "15m",
        "autodel_timer_1h": "1h",
        "autodel_timer_1d": "1d",
        "autodel_timer_instant": "Моментально",
        "autodel_set": "✅ Авто-удаление установлено для {types} с таймером {timer}.",
        "welcome_rules_menu": "<b>📝 Приветствия и правила</b>\n\nРедактируйте приветствие: /set_welcome текст\nПравила: /set_rules текст\nАвто-удаление приветствий: {auto_del}",
        "info_text": "📢 <b>SUB PR — мощный бот для защиты и управления вашими чатами</b>\n\n🔹 Подписка на каналы и чаты (ОП) — публичные, приватные и по инвайт-ссылке  \n🔹 Анти-флуд с гибкими настройками  \n🔹 Модерация: бан, кик, мут, варн (через команды или свайп по сообщению)  \n🔹 Авто-удаление служебных сообщений, ОП и анти-флуда  \n🔹 Красивые приветствия и правила  \n🔹 Удобная панель управления прямо в Telegram  \n🔹 Поддержка 24/7  \n🔹 Многоязычный интерфейс  \n\n🔔 <b>Официальный канал с обновлениями, новостями и полезными материалами:</b>  \n👉 https://t.me/sub_pr  \n\n💡 По всем вопросам — пишите в [Поддержку] в главном меню",
        "adm_stats": "<b>📊 Статистика</b>\n\nВсего пользователей: {users}\nАктивные чаты: {chats}\nСообщений в базе: {msgs}\nАктивных подписок: {subs}\nАктивных мьютов: {mutes}\nПредупреждений: {warns}\nВремя сервера: {time}",
        "adm_broadcast_prompt": "<b>📡 Рассылка</b>\n\nОтправьте текст, фото, видео или анимацию для рассылки всем пользователям.",
        "adm_logs": "<b>📋 Логи системы</b>\n\nПоследние 10 действий:\n{logs}",
        "adm_group_manage": "<b>🛠 Управление группами</b>\n\nВыберите группу для настройки.",
        "adm_group_logs": "<b>📝 Логи групп</b>\n\n{logs}",
        "adm_create_func": "<b>Создать функцию</b>\n\nВ разработке.",
        "service_msgs_menu": "<b>Служебные сообщения</b>\n\nВыберите, что удалять: покинул, присоединился, закрепил, смена фото/названия, уведомления Telegram, сообщения бота.",
        "op_invalid_id": "❌ Неправильный ID канала. Должен начинаться с -100 или быть числом.",
        "op_invite_limit": "Опционально: количество подписок: /setup ID ссылка 100",
        "log_entry": "Админ: {admin}\nЦель: {target}\nДействие: {action}\nСрок: {term}\nПричина: {reason}\nЧат: {chat}\nДата: {date}",
    },
    # Добавьте переводы для en и uk аналогично, но для краткости оставим ru как базовый
    'en': {  # Placeholder, скопируйте и переведите из ru
        # ...
    },
    'uk': {  # Placeholder
        # ...
    },
}

DEFAULT_LANG = 'ru'
LANGUAGES = {'ru': 'Русский', 'en': 'English', 'uk': 'Українська'}
LANG_FLAGS = {'ru': '🇷🇺', 'en': '🇺🇸', 'uk': '🇺🇦'}

def get_string(user_id, key):
    lang_code = get_user_language(user_id)
    return STRINGS.get(lang_code, STRINGS[DEFAULT_LANG]).get(key, f"MISSING: {key}")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def initialize_database():
    with get_db_connection() as conn:
        # Существующие таблицы + новые для авто-удаления, анти-флуда, служебных сообщений
        conn.execute("""
        CREATE TABLE IF NOT EXISTS required_subs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            channel TEXT NOT NULL,
            expires TEXT,
            added_by INTEGER,
            created_at TEXT,
            type TEXT DEFAULT 'public',  -- public, private, invite
            invite_link TEXT,
            sub_limit INTEGER
        )
        """)
        # ... (остальные таблицы без изменений)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS antiflood_settings (
            chat_id INTEGER PRIMARY KEY,
            msg_limit INTEGER DEFAULT 5,
            time_sec INTEGER DEFAULT 10,
            action TEXT DEFAULT 'mute'  -- warn, mute, delete, off
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS autodel_settings (
            chat_id INTEGER PRIMARY KEY,
            types TEXT,  -- comma-separated: op, flood, service
            timer TEXT DEFAULT '10s'  -- 10s,30s,1m,15m,1h,1d,instant
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS service_msgs (
            chat_id INTEGER PRIMARY KEY,
            delete_left BOOLEAN DEFAULT 1,
            delete_joined BOOLEAN DEFAULT 1,
            delete_pinned BOOLEAN DEFAULT 1,
            delete_photo_change BOOLEAN DEFAULT 1,
            delete_title_change BOOLEAN DEFAULT 1,
            delete_tg_notif BOOLEAN DEFAULT 1,
            delete_bot_msgs BOOLEAN DEFAULT 1
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS mod_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            admin_id INTEGER,
            target_id INTEGER,
            action TEXT,
            term TEXT,
            reason TEXT,
            date TEXT
        )
        """)
        conn.commit()

# ... (остальные функции без изменений, такие как get_user_language, set_user_language, etc.)

def generate_start_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    add_url = f"https://t.me/{BOT_USERNAME}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat+promote_members"
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_profile"), callback_data="profile"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_add_group"), url=add_url),
               InlineKeyboardButton(get_string(user_id, "menu_settings"), callback_data="group_settings"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_auto_delete"), callback_data="auto_delete"),
               InlineKeyboardButton(get_string(user_id, "menu_welcome_rules"), callback_data="welcome_rules"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_info"), callback_data="info"),
               InlineKeyboardButton(get_string(user_id, "menu_support"), callback_data="support"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_languages"), callback_data="languages"))
    if user_id == ADMIN_ID:
        markup.add(InlineKeyboardButton(get_string(user_id, "menu_admin"), callback_data="adm_main"))
    return markup

# Добавьте новые генераторы клавиатур для подменю
def generate_group_settings_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    with get_db_connection() as conn:
        chats = conn.execute("SELECT DISTINCT chat_id, chat_title FROM user_groups WHERE user_id = ?", (user_id,)).fetchall()
    if chats:
        for chat in chats:
            markup.add(InlineKeyboardButton(chat['chat_title'] or f"Chat {chat['chat_id']}", callback_data=f"group_set:{chat['chat_id']}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
    return markup

def generate_group_detail_keyboard(user_id, chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("ОП (Публичный)", callback_data=f"op_pub:{chat_id}"),
               InlineKeyboardButton("ОП (Приватный)", callback_data=f"op_priv:{chat_id}"))
    markup.add(InlineKeyboardButton("ОП (Инвайт-ссылка)", callback_data=f"op_inv:{chat_id}"),
               InlineKeyboardButton("Анти-флуд", callback_data=f"flood:{chat_id}"))
    markup.add(InlineKeyboardButton("Авто-удаление", callback_data=f"autodel:{chat_id}"),
               InlineKeyboardButton("Приветствия и правила", callback_data=f"welcome:{chat_id}"))
    markup.add(InlineKeyboardButton("Служебные сообщения", callback_data=f"service:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="group_settings"))
    return markup

def generate_antiflood_keyboard(user_id, chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("3/5", callback_data=f"flood_set:3_5:{chat_id}"),
               InlineKeyboardButton("5/10", callback_data=f"flood_set:5_10:{chat_id}"))
    markup.add(InlineKeyboardButton("10/30", callback_data=f"flood_set:10_30:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "antiflood_action_warn"), callback_data=f"flood_act:warn:{chat_id}"),
               InlineKeyboardButton(get_string(user_id, "antiflood_action_mute"), callback_data=f"flood_act:mute:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "antiflood_action_delete"), callback_data=f"flood_act:delete:{chat_id}"),
               InlineKeyboardButton(get_string(user_id, "antiflood_action_off"), callback_data=f"flood_act:off:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data=f"group_set:{chat_id}"))
    return markup

def generate_autodel_keyboard(user_id, chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("ОП", callback_data=f"autodel_type:op:{chat_id}"),
               InlineKeyboardButton("Анти-флуд", callback_data=f"autodel_type:flood:{chat_id}"))
    markup.add(InlineKeyboardButton("Служебные", callback_data=f"autodel_type:service:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "autodel_timer_10s"), callback_data=f"autodel_timer:10s:{chat_id}"),
               InlineKeyboardButton(get_string(user_id, "autodel_timer_30s"), callback_data=f"autodel_timer:30s:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "autodel_timer_1m"), callback_data=f"autodel_timer:1m:{chat_id}"),
               InlineKeyboardButton(get_string(user_id, "autodel_timer_15m"), callback_data=f"autodel_timer:15m:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "autodel_timer_1h"), callback_data=f"autodel_timer:1h:{chat_id}"),
               InlineKeyboardButton(get_string(user_id, "autodel_timer_1d"), callback_data=f"autodel_timer:1d:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "autodel_timer_instant"), callback_data=f"autodel_timer:instant:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data=f"group_set:{chat_id}"))
    return markup

def generate_welcome_rules_keyboard(user_id, chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("Редактировать приветствие", callback_data=f"welcome_edit:{chat_id}"),
               InlineKeyboardButton("Авто-удаление приветствий", callback_data=f"welcome_del:{chat_id}"))
    markup.add(InlineKeyboardButton("/rules", callback_data=f"rules_show:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data=f"group_set:{chat_id}"))
    return markup

def generate_service_msgs_keyboard(user_id, chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    # Кнопки для toggle каждого типа служебных сообщений
    markup.add(InlineKeyboardButton("Покинул", callback_data=f"service_left:{chat_id}"),
               InlineKeyboardButton("Присоединился", callback_data=f"service_joined:{chat_id}"))
    markup.add(InlineKeyboardButton("Закрепил", callback_data=f"service_pinned:{chat_id}"),
               InlineKeyboardButton("Смена фото/названия", callback_data=f"service_change:{chat_id}"))
    markup.add(InlineKeyboardButton("Уведомления Telegram", callback_data=f"service_tg:{chat_id}"),
               InlineKeyboardButton("Сообщения бота", callback_data=f"service_bot:{chat_id}"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data=f"group_set:{chat_id}"))
    return markup

def generate_adm_main_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(InlineKeyboardButton("📊 Статистика", callback_data="adm_stats"),
               InlineKeyboardButton("📡 Рассылка", callback_data="adm_broadcast"))
    markup.add(InlineKeyboardButton("📋 Логи системы", callback_data="adm_logs"),
               InlineKeyboardButton("🛠 Управление группами", callback_data="adm_groups"))
    markup.add(InlineKeyboardButton("📝 Логи групп", callback_data="adm_group_logs"),
               InlineKeyboardButton("Создать функцию", callback_data="adm_create_func"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
    return markup

# ... (остальные generate_ функции без изменений)

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

    if data == "profile":
        with get_db_connection() as conn:
            reg = conn.execute("SELECT created_at FROM first_start WHERE user_id = ?", (user_id,)).fetchone()
            reg_date = format_readable_date(reg['created_at']) if reg else "Неизвестно"
            groups = conn.execute("SELECT chat_title FROM user_groups WHERE user_id = ?", (user_id,)).fetchall()
            chats_list = "\n".join([f"• <a href=\"https://t.me/joinchat/{g['chat_title']}\">{g['chat_title']}</a>" for g in groups]) or "Нет"  # Пример с ссылками
        username = call.from_user.username or "нет"
        text = get_string(user_id, "profile_text").format(user_id=user_id, username=username, reg_date=reg_date, chats=chats_list)
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=markup)
        return

    if data == "group_settings":
        chats_text = ""
        with get_db_connection() as conn:
            chats = conn.execute("SELECT chat_id, chat_title FROM user_groups WHERE user_id = ?", (user_id,)).fetchall()
            chats_text = "\n".join([f"• <a href=\"https://t.me/joinchat/{chat['chat_id']}\">{chat['chat_title']}</a> [Настроить]" for chat in chats]) or "Нет активных чатов."
        bot.edit_message_text(
            get_string(user_id, "op_group_list").format(chats=chats_text),
            chat_id, msg_id,
            reply_markup=generate_group_settings_keyboard(user_id)
        )
        return

    if data.startswith("group_set:"):
        target_chat_id = int(data.split(":")[1])
        with get_db_connection() as conn:
            chat = bot.get_chat(target_chat_id)
            chat_type = "Публичный" if chat.type == "group" else "Приватный"
            status = "Вы — создатель" if chat.permissions.can_change_info else "Администратор"
            added_by = conn.execute("SELECT added_by FROM required_subs WHERE chat_id = ? LIMIT 1", (target_chat_id,)).fetchone()
            added_by = f"<a href=\"tg://user?id={added_by['added_by']}\">@{bot.get_chat_member(target_chat_id, added_by['added_by']).user.username}</a>" if added_by else "Неизвестно"
            op_pub = "✅" if conn.execute("SELECT COUNT(*) FROM required_subs WHERE chat_id = ? AND type = 'public'", (target_chat_id,)).fetchone()[0] > 0 else "❌"
            op_priv = "✅" if conn.execute("SELECT COUNT(*) FROM required_subs WHERE chat_id = ? AND type = 'private'", (target_chat_id,)).fetchone()[0] > 0 else "❌"
            op_inv = "✅" if conn.execute("SELECT COUNT(*) FROM required_subs WHERE chat_id = ? AND type = 'invite'", (target_chat_id,)).fetchone()[0] > 0 else "❌"
            flood = "✅" if conn.execute("SELECT action FROM antiflood_settings WHERE chat_id = ?", (target_chat_id,)).fetchone() else "❌"
            auto_del = "✅" if conn.execute("SELECT timer FROM autodel_settings WHERE chat_id = ?", (target_chat_id,)).fetchone() else "❌"
            welcome = "✅" if conn.execute("SELECT welcome_text FROM group_settings WHERE chat_id = ?", (target_chat_id,)).fetchone() else "❌"
            rules = "✅" if conn.execute("SELECT rules_text FROM group_settings WHERE chat_id = ?", (target_chat_id,)).fetchone() else "❌"
            service = "✅" if conn.execute("SELECT * FROM service_msgs WHERE chat_id = ?", (target_chat_id,)).fetchone() else "❌"
        text = get_string(user_id, "group_settings_details").format(chat_title=chat.title, chat_id=target_chat_id, chat_type=chat_type, status=status, added_by=added_by, op_pub=op_pub, op_priv=op_priv, op_inv=op_inv, flood=flood, auto_del=auto_del, welcome=welcome, rules=rules, service=service)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_group_detail_keyboard(user_id, target_chat_id))
        return

    if data.startswith("op_pub:"):
        target_chat_id = data.split(":")[1]
        bot.edit_message_text(get_string(user_id, "op_public"), chat_id, msg_id, reply_markup=generate_group_detail_keyboard(user_id, target_chat_id))
        return

    if data.startswith("op_priv:"):
        target_chat_id = data.split(":")[1]
        bot.edit_message_text(get_string(user_id, "op_private"), chat_id, msg_id, reply_markup=generate_group_detail_keyboard(user_id, target_chat_id))
        return

    if data.startswith("op_inv:"):
        target_chat_id = data.split(":")[1]
        bot.edit_message_text(get_string(user_id, "op_invite"), chat_id, msg_id, reply_markup=generate_group_detail_keyboard(user_id, target_chat_id))
        return

    if data.startswith("flood:"):
        target_chat_id = data.split(":")[1]
        with get_db_connection() as conn:
            settings = conn.execute("SELECT msg_limit, time_sec, action FROM antiflood_settings WHERE chat_id = ?", (target_chat_id,)).fetchone()
            action = settings['action'] if settings else "off"
        text = get_string(user_id, "antiflood_menu").format(action=get_string(user_id, f"antiflood_action_{action}"))
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_antiflood_keyboard(user_id, target_chat_id))
        return

    if data.startswith("flood_set:"):
        limit_time, target_chat_id = data.split(":")[1].split("_"), data.split(":")[2]
        with get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO antiflood_settings (chat_id, msg_limit, time_sec) VALUES (?, ?, ?)", (target_chat_id, int(limit_time[0]), int(limit_time[1])))
            conn.commit()
        bot.answer_callback_query(call.id, get_string(user_id, "antiflood_set").format(limit=limit_time[0], time=limit_time[1], action="текущий"))
        call.data = f"flood:{target_chat_id}"
        callback_query_handler(call)
        return

    if data.startswith("flood_act:"):
        action, target_chat_id = data.split(":")[1], data.split(":")[2]
        with get_db_connection() as conn:
            conn.execute("UPDATE antiflood_settings SET action = ? WHERE chat_id = ?", (action, target_chat_id))
            conn.commit()
        bot.answer_callback_query(call.id, get_string(user_id, "antiflood_set").format(limit="текущий", time="текущий", action=get_string(user_id, f"antiflood_action_{action}")))
        call.data = f"flood:{target_chat_id}"
        callback_query_handler(call)
        return

    if data.startswith("autodel:"):
        target_chat_id = data.split(":")[1]
        with get_db_connection() as conn:
            settings = conn.execute("SELECT types, timer FROM autodel_settings WHERE chat_id = ?", (target_chat_id,)).fetchone()
            types = settings['types'] if settings else ""
            timer = settings['timer'] if settings else "10s"
        text = get_string(user_id, "autodel_menu").format(types=types, timer=timer)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_autodel_keyboard(user_id, target_chat_id))
        return

    if data.startswith("autodel_type:"):
        type_, target_chat_id = data.split(":")[1], data.split(":")[2]
        with get_db_connection() as conn:
            settings = conn.execute("SELECT types FROM autodel_settings WHERE chat_id = ?", (target_chat_id,)).fetchone()
            types = set(settings['types'].split(",") if settings else [])
            if type_ in types:
                types.remove(type_)
            else:
                types.add(type_)
            conn.execute("INSERT OR REPLACE INTO autodel_settings (chat_id, types) VALUES (?, ?)", (target_chat_id, ",".join(types)))
            conn.commit()
        bot.answer_callback_query(call.id, get_string(user_id, "autodel_set").format(types=type_, timer="текущий"))
        call.data = f"autodel:{target_chat_id}"
        callback_query_handler(call)
        return

    if data.startswith("autodel_timer:"):
        timer, target_chat_id = data.split(":")[1], data.split(":")[2]
        with get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO autodel_settings (chat_id, timer) VALUES (?, ?)", (target_chat_id, timer))
            conn.commit()
        bot.answer_callback_query(call.id, get_string(user_id, "autodel_set").format(types="текущие", timer=timer))
        call.data = f"autodel:{target_chat_id}"
        callback_query_handler(call)
        return

    if data.startswith("welcome:"):
        target_chat_id = data.split(":")[1]
        with get_db_connection() as conn:
            settings = conn.execute("SELECT welcome_text FROM group_settings WHERE chat_id = ?", (target_chat_id,)).fetchone()
            auto_del = "✅" if conn.execute("SELECT timer FROM autodel_settings WHERE chat_id = ? AND types LIKE '%welcome%'", (target_chat_id,)).fetchone() else "❌"
        text = get_string(user_id, "welcome_rules_menu").format(auto_del=auto_del)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_welcome_rules_keyboard(user_id, target_chat_id))
        return

    if data.startswith("welcome_edit:"):
        target_chat_id = data.split(":")[1]
        _local_memory[user_id] = f"waiting_welcome:{target_chat_id}"
        bot.edit_message_text("Введите текст приветствия:", chat_id, msg_id, reply_markup=generate_back_button(user_id, f"welcome:{target_chat_id}"))
        return

    if data.startswith("welcome_del:"):
        target_chat_id = data.split(":")[1]
        with get_db_connection() as conn:
            settings = conn.execute("SELECT types FROM autodel_settings WHERE chat_id = ?", (target_chat_id,)).fetchone()
            types = set(settings['types'].split(",") if settings else [])
            if "welcome" in types:
                types.remove("welcome")
            else:
                types.add("welcome")
            conn.execute("INSERT OR REPLACE INTO autodel_settings (chat_id, types) VALUES (?, ?)", (target_chat_id, ",".join(types)))
            conn.commit()
        bot.answer_callback_query(call.id, "Авто-удаление приветствий переключено.")
        call.data = f"welcome:{target_chat_id}"
        callback_query_handler(call)
        return

    if data.startswith("rules_show:"):
        target_chat_id = data.split(":")[1]
        with get_db_connection() as conn:
            rules = conn.execute("SELECT rules_text FROM group_settings WHERE chat_id = ?", (target_chat_id,)).fetchone()
        text = get_string(user_id, "rules").format(text=rules['rules_text'] if rules else "Нет правил.")
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_welcome_rules_keyboard(user_id, target_chat_id))
        return

    if data.startswith("service:"):
        target_chat_id = data.split(":")[1]
        text = get_string(user_id, "service_msgs_menu")
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_service_msgs_keyboard(user_id, target_chat_id))
        return

    if data.startswith("service_"):
        type_ = data.split("_")[1].split(":")[0]
        target_chat_id = data.split(":")[1]
        with get_db_connection() as conn:
            col = f"delete_{type_}"
            current = conn.execute(f"SELECT {col} FROM service_msgs WHERE chat_id = ?", (target_chat_id,)).fetchone()
            new_val = 0 if current and current[col] else 1
            conn.execute(f"INSERT OR REPLACE INTO service_msgs (chat_id, {col}) VALUES (?, ?)", (target_chat_id, new_val))
            conn.commit()
        bot.answer_callback_query(call.id, f"Удаление {type_} переключено.")
        call.data = f"service:{target_chat_id}"
        callback_query_handler(call)
        return

    if data == "info":
        bot.edit_message_text(get_string(user_id, "info_text"), chat_id, msg_id, reply_markup=generate_back_button(user_id, "main_menu"))
        return

    if data == "adm_main":
        bot.edit_message_text(get_string(user_id, "admin_panel_title"), chat_id, msg_id, reply_markup=generate_adm_main_keyboard(user_id))
        return

    if data == "adm_stats":
        with get_db_connection() as conn:
            users = conn.execute("SELECT COUNT(*) FROM first_start").fetchone()[0]
            chats = conn.execute("SELECT COUNT(DISTINCT chat_id) FROM user_groups").fetchone()[0]
            msgs = conn.execute("SELECT SUM(total_messages) FROM user_stats").fetchone()[0] or 0
            subs = conn.execute("SELECT COUNT(*) FROM required_subs").fetchone()[0]
            mutes = conn.execute("SELECT COUNT(*) FROM mutes").fetchone()[0]
            warns = conn.execute("SELECT COUNT(*) FROM warns").fetchone()[0]
            server_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        text = get_string(user_id, "adm_stats").format(users=users, chats=chats, msgs=msgs, subs=subs, mutes=mutes, warns=warns, time=server_time)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    if data == "adm_broadcast":
        _local_memory[user_id] = "waiting_broadcast"
        bot.edit_message_text(get_string(user_id, "adm_broadcast_prompt"), chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    if data == "adm_logs":
        with get_db_connection() as conn:
            logs = conn.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT 10").fetchall()
        logs_text = "\n".join([f"{log['action_type']}: {log['details']} ({log['created_at']})" for log in logs]) or "Нет логов."
        text = get_string(user_id, "adm_logs").format(logs=logs_text)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    if data == "adm_groups":
        bot.edit_message_text(get_string(user_id, "adm_group_manage"), chat_id, msg_id, reply_markup=generate_group_settings_keyboard(user_id))
        return

    if data == "adm_group_logs":
        with get_db_connection() as conn:
            logs = conn.execute("SELECT * FROM mod_logs ORDER BY id DESC LIMIT 10").fetchall()
        logs_text = "\n".join([get_string(user_id, "log_entry").format(admin=log['admin_id'], target=log['target_id'], action=log['action'], term=log['term'] or "", reason=log['reason'] or "", chat=log['chat_id'], date=log['date']) for log in logs]) or "Нет логов."
        text = get_string(user_id, "adm_group_logs").format(logs=logs_text)
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    if data == "adm_create_func":
        bot.edit_message_text(get_string(user_id, "adm_create_func"), chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    # ... (остальные обработчики callback без изменений)

@bot.message_handler(func=lambda m: _local_memory.get(m.from_user.id, "").startswith("waiting_welcome:"))
def process_welcome_edit(message):
    user_id = message.from_user.id
    target_chat_id = int(_local_memory[user_id].split(":")[1])
    text = message.text.strip()
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO group_settings (chat_id, welcome_text) VALUES (?, ?)", (target_chat_id, text))
        conn.commit()
    _local_memory.pop(user_id)
    bot.reply_to(message, get_string(user_id, "set_welcome_success"))
    return

# ... (остальные message_handler для support, broadcast, user_check без изменений)

@bot.message_handler(commands=['setup'])
def command_setup(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "Команда только для групп.")
        return
    if not check_admin_rights(message.chat.id, user_id):
        bot.reply_to(message, get_string(user_id, "no_admin_rights"))
        return
    args = message.text.split()[1:]
    if not args:
        bot.reply_to(message, get_string(user_id, "op_invalid_format"))
        return
    type_ = 'public'
    channel = args[0]
    invite_link = None
    sub_limit = None
    time_str = None
    expires = None
    if channel.isdigit() or channel.startswith('-100'):
        type_ = 'private'
        if len(args) > 1:
            invite_link = args[1]
            type_ = 'invite'
            if len(args) > 2 and args[2].isdigit():
                sub_limit = int(args[2])
            if len(args) > 3:
                time_str = args[3]
        else:
            if len(args) > 1:
                time_str = args[1]
    else:
        if len(args) > 1:
            time_str = args[1]
    if time_str:
        delta = parse_time_string(time_str)
        if delta:
            expires = (datetime.utcnow() + delta).isoformat()
        else:
            bot.reply_to(message, get_string(user_id, "setup_error_time"))
            return
    if type_ == 'public' and not check_bot_admin_in_channel(channel):
        bot.reply_to(message, get_string(user_id, "op_error").format(channel=channel))
        return
    with get_db_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM required_subs WHERE chat_id = ?", (message.chat.id,)).fetchone()[0]
        if count >= MAX_SUBS:
            bot.reply_to(message, get_string(user_id, "op_max"))
            return
        conn.execute("INSERT INTO required_subs (chat_id, channel, type, invite_link, sub_limit, expires, added_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (message.chat.id, channel, type_, invite_link, sub_limit, expires, user_id, get_iso_now()))
        conn.commit()
    bot.reply_to(message, get_string(user_id, "setup_success").format(channel=channel, info=expires or "навсегда"))
    return

@bot.message_handler(commands=['unsetup'])
def command_unsetup(message):
    # Аналогично, но с поддержкой ID для private/invite
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        bot.reply_to(message, "Команда только для групп.")
        return
    if not check_admin_rights(message.chat.id, user_id):
        bot.reply_to(message, get_string(user_id, "no_admin_rights"))
        return
    args = message.text.split()[1:]
    if not args:
        bot.reply_to(message, get_string(user_id, "unsetup_usage"))
        return
    channel = args[0]
    with get_db_connection() as conn:
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel))
        conn.commit()
    bot.reply_to(message, get_string(user_id, "unsetup_deleted").format(channel=channel))
    return

# Для модерации добавить reason и term в команды, логировать в mod_logs
@bot.message_handler(commands=['ban', 'kick', 'mute', 'warn'])
def mod_commands(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return
    cmd = message.text.split()[0][1:]
    args = message.text.split()[1:]
    target_id = message.reply_to_message.from_user.id if message.reply_to_message else None
    term = args[0] if args and parse_time_string(args[0]) else ""
    reason = " ".join(args[1:] if term else args) or get_string(user_id, "warn_reason")
    if not target_id:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return
    # Выполнить действие
    if cmd == 'ban':
        bot.ban_chat_member(message.chat.id, target_id)
        text = get_string(user_id, "ban_success").format(user_name=bot.get_chat_member(message.chat.id, target_id).user.first_name, reason=reason)
    elif cmd == 'kick':
        bot.ban_chat_member(message.chat.id, target_id)
        bot.unban_chat_member(message.chat.id, target_id)
        text = get_string(user_id, "kick_success").format(user_name=bot.get_chat_member(message.chat.id, target_id).user.first_name, reason=reason)
    elif cmd == 'mute':
        delta = parse_time_string(term)
        if not delta:
            bot.reply_to(message, get_string(user_id, "mute_error_time"))
            return
        until = datetime.utcnow() + delta
        bot.restrict_chat_member(message.chat.id, target_id, until_date=until.timestamp(), permissions=ChatPermissions(can_send_messages=False))
        text = get_string(user_id, "mute_success").format(duration=term, user_name=bot.get_chat_member(message.chat.id, target_id).user.first_name, date=until.strftime("%Y-%m-%d %H:%M"), reason=reason)
    elif cmd == 'warn':
        with get_db_connection() as conn:
            conn.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?, ?)", (message.chat.id, target_id, user_id, reason, get_iso_now()))
            count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target_id)).fetchone()[0]
        if count >= 3:
            bot.ban_chat_member(message.chat.id, target_id)
            text = get_string(user_id, "warn_limit_ban").format(count=count, limit=3, user_name=bot.get_chat_member(message.chat.id, target_id).user.first_name, reason=reason)
        else:
            text = get_string(user_id, "warn_added").format(count=count, limit=3, user_name=bot.get_chat_member(message.chat.id, target_id).user.first_name, reason=reason)
    bot.reply_to(message, text)
    # Логировать
    with get_db_connection() as conn:
        conn.execute("INSERT INTO mod_logs (chat_id, admin_id, target_id, action, term, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?)", (message.chat.id, user_id, target_id, cmd.upper(), term, reason, get_iso_now()))
        conn.commit()
    return

# Добавьте логику анти-флуда в group_message_processor
# Для каждого пользователя хранить последние сообщения в _local_memory или в DB (для простоты в памяти)
flood_tracker = {}  # {chat_id: {user_id: [timestamps]}}

def group_message_processor(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    if check_admin_rights(chat_id, user_id) or message.from_user.is_bot:
        return
    # Анти-флуд
    with get_db_connection() as conn:
        flood_set = conn.execute("SELECT msg_limit, time_sec, action FROM antiflood_settings WHERE chat_id = ?", (chat_id,)).fetchone()
    if flood_set and flood_set['action'] != "off":
        if chat_id not in flood_tracker:
            flood_tracker[chat_id] = {}
        if user_id not in flood_tracker[chat_id]:
            flood_tracker[chat_id][user_id] = []
        flood_tracker[chat_id][user_id].append(time.time())
        flood_tracker[chat_id][user_id] = [t for t in flood_tracker[chat_id][user_id] if time.time() - t < flood_set['time_sec']]
        if len(flood_tracker[chat_id][user_id]) > flood_set['msg_limit']:
            if flood_set['action'] == 'delete':
                bot.delete_message(chat_id, message.message_id)
            elif flood_set['action'] == 'mute':
                bot.restrict_chat_member(chat_id, user_id, until_date=(time.time() + 60), permissions=ChatPermissions(can_send_messages=False))
            elif flood_set['action'] == 'warn':
                command_warn(message)  # Вызвать warn
            return
    # ОП проверка (без изменений)
    # Авто-удаление: добавить timer для удаления сообщений бота/служебных
    # Для служебных: если message.new_chat_members or left_chat_member or pinned_message etc.
    if message.new_chat_members or message.left_chat_member or message.pinned_message or message.new_chat_photo or message.new_chat_title or message.from_user.is_bot:
        with get_db_connection() as conn:
            autodel = conn.execute("SELECT timer FROM autodel_settings WHERE chat_id = ? AND types LIKE '%service%'", (chat_id,)).fetchone()
            service = conn.execute("SELECT * FROM service_msgs WHERE chat_id = ?", (chat_id,)).fetchone()
        if autodel and service:
            # Проверить, нужно ли удалять этот тип
            if (message.left_chat_member and service['delete_left']) or (message.new_chat_members and service['delete_joined']) or ... :  # Добавить все типы
                delta = parse_time_string(autodel['timer'])
                if delta:
                    time.sleep(delta.total_seconds())
                    bot.delete_message(chat_id, message.message_id)
    # ... (остальная логика)

# ... (остальные команды и функции без изменений, добавьте аналогично для unban, unmute)

# Для авто-удаления ОП и флуда: в местах, где бот отправляет сообщения о нарушении, добавить таймер удаления

if __name__ == "__main__":
    initialize_database()
    worker_thread = threading.Thread(target=background_unmute_worker, daemon=True)
    worker_thread.start()
    setup_webhook_connection()
    app.run(host="0.0.0.0", port=PORT)
