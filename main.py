import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Update, ChatPermissions, ReplyKeyboardRemove
from dotenv import load_dotenv
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация
TOKEN = os.getenv("BOT_TOKEN") or "YOUR_TOKEN_HERE"
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "8000"))
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
LOG_CHANNEL = int(os.getenv("LOG_CHANNEL", "4902536707"))  
DB_PATH = os.getenv("DB_PATH", "data.db")
ADMIN_STATUSES = ("administrator", "creator")
MAX_LOG_ENTRIES = 10
BOT_USERNAME = "Subscribe_piarbot"
MAX_SUBS = 5

# Инициализация
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Локальная память
_local_memory = {}

# Строки локализации
STRINGS = {
    'ru': {
        "welcome_private": "👋 Добро пожаловать, {user_name}!\n\nSUB PR — бот для управления подписками, безопасностью чатов и модерацией.\n\nИспользуйте меню ниже для управления ботом:",
        "menu_add_group": "➕ Добавить в группу",
        "menu_settings": "⚙ Настройки группы",
        "menu_info": "💬 О боте",
        "menu_support": "🛟 Поддержка",
        "menu_profile": "👤 Профиль",
        "menu_languages": "🌍 Язык",
        "menu_admin": "🔒 Админ меню",
        "menu_our_chat": "Наш чат",
        "menu_our_channel": "Наш канал",
        "menu_auto_delete": "🧹 Авто-удаление",
        "menu_welcome_rules": "📝 Приветствия и правила",
        "menu_user_check": "🔍 Проверка пользователя",
        "menu_group_settings": "⚙️ Настройки групп",
        "menu_manage_subs": "🛡 Управление подписками",
        "lang_changed": "✅ Язык изменен на **{lang}**.",
        "lang_choose": "🌐 Выберите язык / Choose Language / Оберіть мову:",
        "lang_back": "🔙 Назад",
        "lang_title_ru": "🇷🇺 Русский",
        "lang_title_en": "🇺🇸 English",
        "lang_title_uk": "🇺🇦 Українська",
        "admin_panel_title": "🎛 Панель Администратора\nГлавное меню управления ботом.",
        "no_rights": "⛔ У вас нет прав доступа к этому меню. Вы не владелец бота.",
        "group_welcome": "👋 Привет! Я — {bot_name}.\n\nЯ помогаю управлять группой и подписками. Чтобы настроить меня, перейдите в ЛС.",
        "group_go_private": "🤖 Перейти в ЛС для настройки",
        "setup_info": "ℹ️ Использование:\n/setup @channel [время]\n\nПример: /setup @MyChannel 1d",
        "setup_error_time": "⚠️ Ошибка: Неверный формат времени. Используйте: 30m, 1h, 5d и т.д.",
        "setup_error_not_channel": "⚠️ Ошибка: Это не канал или супергруппа.",
        "setup_error_unknown_channel": "⚠️ Ошибка: Я не вижу этот канал. Убедитесь, что он существует и его юзернейм корректен.",
        "setup_success": "✅ Канал добавлен!\nТеперь подписка на {channel} обязательна {info}.",
        "setup_info_forever": "навсегда",
        "setup_info_until": "до {date}",
        "unsetup_usage": "ℹ️ Использование: /unsetup @channel\n\nВ этом чате нет активных требований подписки.",
        "unsetup_list": "ℹ️ Текущие обязательные подписки:\n{channels}\n\nВведите команду с юзернеймом для удаления.",
        "unsetup_deleted": "🗑 Требование подписки на {channel} удалено.",
        "unsetup_not_found": "❌ Ошибка: Подписка на {channel} не найдена в списке обязательных для этого чата.",
        "cmd_no_reply": "↩️ Ответьте на сообщение пользователя или укажите @username.",
        "cmd_no_id_reply": "ℹ️ ID или реплай или @username.",
        "no_admin_rights": "⛔ Только администраторы могут использовать эту команду.",
        "ban_success": "⛔ Забанен: {user_name}\nПричина: {reason}",
        "ban_error": "❌ Ошибка бана: {error}",
        "unban_success": "🕊 Разбанен: {user_id}",
        "unban_error": "❌ Ошибка разбана: {error}",
        "mute_error_time": "⚠️ Неверный формат времени. Используйте: 30m, 1h, 5d.",
        "mute_success": "🔇 Мут на {duration}: {user_name}\nАвтоматический размут: {date}\nПричина: {reason}",
        "mute_error": "❌ Ошибка мьюта: {error}",
        "unmute_success": "🔊 Мут снят с {user_name}.",
        "unmute_error": "❌ Ошибка размута: {error}",
        "warn_reason": "Нарушение правил чата",
        "warn_limit_ban": "⛔ Бан за варны ({count}/{limit}): {user_name}\nПричина: {reason}",
        "warn_added": "⚠️ Варн ({count}/{limit}): {user_name}\nПричина: {reason}",
        "kick_success": "👢 Кикнут: {user_name}.\nПричина: {reason}",
        "kick_error": "❌ Ошибка кика: {error}",
        "sub_access_denied": "🚫 Доступ ограничен, {user_name}!\n\nДля того чтобы писать в этот чат, необходимо подписаться на следующие каналы.",
        "sub_button_text": "👉 Подписаться на {channel}",
        "sub_button_verify": "✅ Я подписался",
        "sub_verified": "✅ Доступ разрешен! Можете писать в чат.",
        "sub_not_all": "❌ Вы подписались не на все каналы! Повторите проверку после подписки.",
        "settings_info": "⚙️ Настройки группы\n\nЗдесь вы можете настроить фильтры, приветствия и подписки. Используйте /setup в чате.",
        "support_prompt": "📞 Поддержка\n\nНапишите ваше сообщение для поддержки:",
        "support_received": "✅ Ваше сообщение отправлено в поддержку! Ожидайте ответа.",
        "support_from_user": "📩 Сообщение от пользователя {user_name} (@{username}, ID: {user_id}):\n\n{text}",
        "support_reply": "Ответить",
        "support_dismiss": "Отклонить",
        "support_response": "📨 Ответ от поддержки:\n\n{text}",
        "user_check_prompt": "🔍 Проверка пользователя\n\nВведите ID или @username:",
        "user_check_not_found": "❌ Пользователь не найден.",
        "user_check_info": "Информация о пользователе:\nID: {user_id}\nИмя: {first_name}\nФамилия: {last_name}\nUsername: @{username}\n\nЧаты:\n{chats}\n\nВарны: {warns}\nМьюты: {mutes}",
        "group_settings_title": "⚙️ Настройки групп\n\nВыберите группу:",
        "group_settings_details": "Настройки для {chat_title} (ID: {chat_id})\nТип: {chat_type}\nСтатус: {status}\nДобавил: {added_by}\n\nФункции:\n- ОП (Публичный канал): {op_pub}\n- ОП (Приватный канал): {op_priv}\n- ОП (Инвайт-ссылка): {op_inv}\n- Анти-флуд: {flood}\n- Авто-удаление сообщений: {auto_del}\n- Приветствие новых участников: {welcome}\n- Правила группы: {rules}\n- Служебные сообщения: {service}",
        "anti_flood_on": "✅ Антифлуд включен.",
        "anti_flood_off": "❌ Антифлуд выключен.",
        "set_welcome_success": "✅ Приветствие установлено.",
        "set_rules_success": "✅ Правила установлены.",
        "rules": "Правила чата:\n{text}",
        "welcome_new_member": "👋 Добро пожаловать, {user_name}!\n\n{rules}",
        "no_bot_admin": "⚠️ Бот не админ в {channel}.\n\nДобавьте в админы сначала.",
        "status_text": "📋 Активные проверки:\n\n{list}",
        "status_empty": "Нет активных проверок.",
        "profile_text": "💳 Ваш профиль\n━━━━━━━━━━━━━━━\n🆔 ID: {user_id}\n👤 Ник: @{username}\n📅 Регистрация: {reg_date}\n━━━━━━━━━━━━━━━\nВаши активные чаты:\n{chats}",
        "op_public": "✅ Функция проверки подписки на публичные каналы/чаты 🛡️\n\n"
                     "▸ Шаг 1: Добавьте меня в админы канала/чата для проверки.\n"
                     "▸ Шаг 2: В вашем чате: /setup @channel и время (60s, 60m, 24h, 1d).\n\n"
                     "⛔ Для отключения: /unsetup @channel ❌\n\n"
                     "➕ Макс. 5 проверок!\n\n"
                     "💡 /status покажет активные проверки и таймеры. ⏰\n\n"
                     "Вопросы? В поддержку 📞",
        "op_private": "📢 Проверка подписки для приватных каналов/чатов:\n\n"
                      "Шаг 1: Узнайте ID приватного канала.\n"
                      "Шаг 2: В чате: /setup 1001994526641\n\n"
                      "Отключить: /unsetup 1001994526641\n\n"
                     "💡 /status для меню просмотра и редактирования.",
        "op_invite": "🔗 Проверка подписки на пригласительные ссылки.\n\n"
                     "Шаг 1: Узнайте ID приватного канала.\n"
                     "Шаг 2: /setup 1001994526641 https://t.me/+Link\n\n"
                     "Отключить: /unsetup 1001994526641\n\n"
                     "Лимит подписок: /setup ... 100\n"
                     "Таймер: /setup ... 1d (s/m/h/d)\n\n"
                     "💡 /status для управления.",
        "op_error": "❌ Я не могу установить проверку подписки. Причина: я не администратор канала/чата {channel}.",
        "op_max": "❌ Превышено максимальное количество проверок (5). Удалите старые через /unsetup @channel.",
        "op_invalid_format": "❌ Неправильный формат команды. Используйте /setup @channel или /setup ID [ссылка] [лимит] [время].",
        "op_group_list": "Список ваших групп:\n\n{chats}",
        "antiflood_menu": "🚫 Анти-флуд\n\nВыберите лимит:\n- 3 сообщения / 5 сек\n- 5 сообщений / 10 сек\n- 10 сообщений / 30 сек\n\nДействие: {action}",
        "antiflood_action_warn": "⚠ Предупреждение",
        "antiflood_action_mute": "🔇 Мут",
        "antiflood_action_delete": "🧹 Удаление сообщений",
        "antiflood_action_off": "❌ Отключить",
        "antiflood_set": "✅ Анти-флуд установлен: {limit} сообщений / {time} сек. Действие: {action}.",
        "autodel_menu": "🧹 Авто-удаление\n\nВыберите тип сообщений для удаления:\n- ОП\n- Анти-флуд\n- Служебные (покинул, присоединился, закрепил, смена фото/названия, уведомления Telegram, сообщения бота)\n\nТаймер: {timer}",
        "autodel_timer_10s": "10s",
        "autodel_timer_30s": "30s",
        "autodel_timer_1m": "1m",
        "autodel_timer_15m": "15m",
        "autodel_timer_1h": "1h",
        "autodel_timer_1d": "1d",
        "autodel_timer_instant": "Моментально",
        "autodel_set": "✅ Авто-удаление установлено для {types} с таймером {timer}.",
        "welcome_rules_menu": "📝 Приветствия и правила\n\nРедактируйте приветствие: /set_welcome текст\nПравила: /set_rules текст\nАвто-удаление приветствий: {auto_del}",
        "info_text": "📢 SUB PR — мощный бот для защиты и управления вашими чатами\n\n🔹 Подписка на каналы и чаты (ОП) — публичные, приватные и по инвайт-ссылке  \n🔹 Анти-флуд с гибкими настройками  \n🔹 Модерация: бан, кик, мут, варн (через команды или свайп по сообщению)  \n🔹 Авто-удаление служебных сообщений, ОП и анти-флуда  \n🔹 Красивые приветствия и правила  \n🔹 Удобная панель управления прямо в Telegram  \n🔹 Поддержка 24/7  \n🔹 Многоязычный интерфейс  \n\n🔔 Официальный канал с обновлениями, новостями и полезными материалами:  \n👉 https://t.me/sub_pr  \n\n💡 По всем вопросам — пишите в [Поддержку] в главном меню",
        "adm_stats": "📊 Статистика\n\nВсего пользователей: {users}\nАктивные чаты: {chats}\nСообщений в базе: {msgs}\nАктивных подписок: {subs}\nАктивных мьютов: {mutes}\nПредупреждений: {warns}\nВремя сервера: {time}",
        "adm_broadcast_prompt": "📡 Рассылка\n\nОтправьте текст, фото, видео или анимацию для рассылки всем пользователям.",
        "adm_logs": "📋 Логи системы\n\nПоследние 10 действий:\n{logs}",
        "adm_group_manage": "🛠 Управление группами\n\nВыберите группу для настройки.",
        "adm_group_logs": "📝 Логи групп\n\n{logs}",
        "adm_create_func_prompt": "Введите имя функции и описание через пробел: имя описание",
        "adm_create_func_success": "✅ Функция {name} создана с описанием: {desc}",
        "adm_create_func_format": "Формат: имя описание",
        "service_msgs_menu": "Служебные сообщения\n\nВыберите, что удалять: покинул, присоединился, закрепил, смена фото/названия, уведомления Telegram, сообщения бота.",
        "op_invalid_id": "❌ Неправильный ID канала. Должен начинаться с -100 или быть числом.",
        "op_invite_limit": "Опционально: количество подписок: /setup ID ссылка 100",
        "log_entry": "Админ: @{admin_username} ({admin_id})\nЦель: @{target_username} ({target_id})\nДействие: {action}\nСрок: {term}\nПричина: {reason}\nЧат: {chat_title} ({chat_id})\nДата: {date}",
        "no_groups_added": "Нет добавленных групп.",
    },
    'en': {
        "welcome_private": "👋 Welcome, {user_name}!\n\nSUB PR — bot for managing subscriptions, chat security, and moderation.\n\nUse the menu below to manage the bot:",
        "menu_add_group": "➕ Add to group",
        "menu_settings": "⚙ Group settings",
        "menu_info": "💬 About the bot",
        "menu_support": "🛟 Support",
        "menu_profile": "👤 Profile",
        "menu_languages": "🌍 Language",
        "menu_admin": "🔒 Admin menu",
        "menu_our_chat": "Our chat",
        "menu_our_channel": "Our channel",
        "menu_auto_delete": "🧹 Auto-delete",
        "menu_welcome_rules": "📝 Greetings and rules",
        "menu_user_check": "🔍 User check",
        "menu_group_settings": "⚙️ Groups settings",
        "menu_manage_subs": "🛡 Manage subscriptions",
        "lang_changed": "✅ Language changed to **{lang}**.",
        "lang_choose": "🌐 Select language / Choose Language / Оберіть мову:",
        "lang_back": "🔙 Back",
        "lang_title_ru": "🇷🇺 Russian",
        "lang_title_en": "🇺🇸 English",
        "lang_title_uk": "🇺🇦 Ukrainian",
        "admin_panel_title": "🎛 Admin Panel\nMain bot management menu.",
        "no_rights": "⛔ You do not have access to this menu. You are not the bot owner.",
        "group_welcome": "👋 Hi! I am {bot_name}.\n\nI help manage the group and subscriptions. To set me up, go to PM.",
        "group_go_private": "🤖 Go to PM for setup",
        "setup_info": "ℹ️ Usage:\n/setup @channel [time]\n\nExample: /setup @MyChannel 1d",
        "setup_error_time": "⚠️ Error: Invalid time format. Use: 30m, 1h, 5d etc.",
        "setup_error_not_channel": "⚠️ Error: This is not a channel or supergroup.",
        "setup_error_unknown_channel": "⚠️ Error: I can't see this channel. Make sure it exists and the username is correct.",
        "setup_success": "✅ Channel added!\nSubscription to {channel} is now required {info}.",
        "setup_info_forever": "forever",
        "setup_info_until": "until {date}",
        "unsetup_usage": "ℹ️ Usage: /unsetup @channel\n\nThere are no active subscription requirements in this chat.",
        "unsetup_list": "ℹ️ Current required subscriptions:\n{channels}\n\nEnter the command with username to delete.",
        "unsetup_deleted": "🗑 Subscription requirement for {channel} removed.",
        "unsetup_not_found": "❌ Error: Subscription to {channel} not found in the required list for this chat.",
        "cmd_no_reply": "↩️ Reply to a user's message.",
        "cmd_no_id_reply": "ℹ️ ID or reply.",
        "no_admin_rights": "⛔ Only administrators can use this command.",
        "ban_success": "⛔ Banned: {user_name}\nReason: {reason}",
        "ban_error": "❌ Ban error: {error}",
        "unban_success": "🕊 Unbanned: {user_id}",
        "unban_error": "❌ Unban error: {error}",
        "mute_error_time": "⚠️ Invalid time format. Use: 30m, 1h, 5d.",
        "mute_success": "🔇 Mute for {duration}: {user_name}\nAuto-unmute: {date}\nReason: {reason}",
        "mute_error": "❌ Mute error: {error}",
        "unmute_success": "🔊 Mute removed from {user_name}.",
        "unmute_error": "❌ Unmute error: {error}",
        "warn_reason": "Chat rules violation",
        "warn_limit_ban": "⛔ Ban for warns ({count}/{limit}): {user_name}\nReason: {reason}",
        "warn_added": "⚠️ Warn ({count}/{limit}): {user_name}\nReason: {reason}",
        "kick_success": "👢 Kicked: {user_name}.\nReason: {reason}",
        "kick_error": "❌ Kick error: {error}",
        "sub_access_denied": "🚫 Access restricted, {user_name}!\n\nTo write in this chat, you need to subscribe to the following channels.",
        "sub_button_text": "👉 Subscribe to {channel}",
        "sub_button_verify": "✅ I subscribed",
        "sub_verified": "✅ Access granted! You can write in the chat.",
        "sub_not_all": "❌ You haven't subscribed to all channels! Repeat the check after subscribing.",
        "settings_info": "⚙️ Group settings\n\nHere you can set filters, greetings, and subscriptions. Use /setup in the chat.",
        "support_prompt": "📞 Support\n\nWrite your message for support:",
        "support_received": "✅ Your message has been sent to support! Wait for a response.",
        "support_from_user": "📩 Message from user {user_name} (@{username}, ID: {user_id}):\n\n{text}",
        "support_reply": "Reply",
        "support_dismiss": "Dismiss",
        "support_response": "📨 Response from support:\n\n{text}",
        "user_check_prompt": "🔍 User check\n\nEnter ID or @username:",
        "user_check_not_found": "❌ User not found.",
        "user_check_info": "User information:\nID: {user_id}\nFirst name: {first_name}\nLast name: {last_name}\nUsername: @{username}\n\nChats:\n{chats}\n\nWarns: {warns}\nMutes: {mutes}",
        "group_settings_title": "⚙️ Groups settings\n\nSelect a group:",
        "group_settings_details": "Settings for {chat_title} (ID: {chat_id})\nType: {chat_type}\nStatus: {status}\nAdded by: {added_by}\n\nFeatures:\n- OP (Public channel): {op_pub}\n- OP (Private channel): {op_priv}\n- OP (Invite link): {op_inv}\n- Anti-flood: {flood}\n- Auto-delete messages: {auto_del}\n- Greeting new members: {welcome}\n- Group rules: {rules}\n- Service messages: {service}",
        "anti_flood_on": "✅ Anti-flood enabled.",
        "anti_flood_off": "❌ Anti-flood disabled.",
        "set_welcome_success": "✅ Greeting set.",
        "set_rules_success": "✅ Rules set.",
        "rules": "Chat rules:\n{text}",
        "welcome_new_member": "👋 Welcome, {user_name}!\n\n{rules}",
        "no_bot_admin": "⚠️ Bot is not admin in {channel}.\n\nAdd as admin first.",
        "status_text": "📋 Active checks:\n\n{list}",
        "status_empty": "No active checks.",
        "profile_text": "💳 Your profile\n━━━━━━━━━━━━━━━\n🆔 ID: {user_id}\n👤 Nick: @{username}\n📅 Registration: {reg_date}\n━━━━━━━━━━━━━━━\nYour active chats:\n{chats}",
        "op_public": "✅ Public channels/chats subscription check feature 🛡️\n\n"
                     "▸ Step 1: Add me as admin to the channel/chat for check.\n"
                     "▸ Step 2: In your chat: /setup @channel and time (60s, 60m, 24h, 1d).\n\n"
                     "⛔ To disable: /unsetup @channel ❌\n\n"
                     "➕ Max 5 checks!\n\n"
                     "💡 /status will show active checks and timers. ⏰\n\n"
                     "Questions? Contact support 📞",
        "op_private": "📢 Subscription check for private channels/chats:\n\n"
                      "Step 1: Find the private channel ID.\n"
                      "Step 2: In chat: /setup 1001994526641\n\n"
                      "Disable: /unsetup 1001994526641\n\n"
                      "💡 /status for view and edit menu.",
        "op_invite": "🔗 Subscription check for invite links.\n\n"
                     "Step 1: Find the private channel ID.\n"
                     "Step 2: /setup 1001994526641 https://t.me/+Link\n\n"
                     "Disable: /unsetup 1001994526641\n\n"
                     "Subscriptions limit: /setup ... 100\n"
                     "Timer: /setup ... 1d (s/m/h/d)\n\n"
                     "💡 /status for management.",
        "op_error": "❌ I can't set subscription check. Reason: I am not an admin of the channel/chat {channel}.",
        "op_max": "❌ Maximum number of checks exceeded (5). Remove old ones via /unsetup.",
        "op_invalid_format": "❌ Invalid command format. Use /setup @channel or /setup ID [link] [limit] [time].",
        "op_group_list": "List of your groups:\n\n{chats}",
        "antiflood_menu": "🚫 Anti-flood\n\nSelect limit:\n- 3 messages / 5 sec\n- 5 messages / 10 sec\n- 10 messages / 30 sec\n\nAction: {action}",
        "antiflood_action_warn": "⚠ Warning",
        "antiflood_action_mute": "🔇 Mute",
        "antiflood_action_delete": "🧹 Delete messages",
        "antiflood_action_off": "❌ Disable",
        "antiflood_set": "✅ Anti-flood set: {limit} messages / {time} sec. Action: {action}.",
        "autodel_menu": "🧹 Auto-delete\n\nSelect message types to delete:\n- OP\n- Anti-flood\n- Service (left, joined, pinned, photo/title change, Telegram notifications, bot messages)\n\nTimer: {timer}",
        "autodel_timer_10s": "10s",
        "autodel_timer_30s": "30s",
        "autodel_timer_1m": "1m",
        "autodel_timer_15m": "15m",
        "autodel_timer_1h": "1h",
        "autodel_timer_1d": "1d",
        "autodel_timer_instant": "Instantly",
        "autodel_set": "✅ Auto-delete set for {types} with timer {timer}.",
        "welcome_rules_menu": "📝 Greetings and rules\n\nEdit greeting: /set_welcome text\nRules: /set_rules text\nAuto-delete greetings: {auto_del}",
        "info_text": "📢 SUB PR — powerful bot for protecting and managing your chats\n\n🔹 Subscriptions to channels and chats (OP) — public, private, and via invite link  \n🔹 Anti-flood with flexible settings  \n🔹 Moderation: ban, kick, mute, warn (via commands or swipe on message)  \n🔹 Auto-delete service messages, OP, and anti-flood  \n🔹 Beautiful greetings and rules  \n🔹 Convenient control panel right in Telegram  \n🔹 24/7 support  \n🔹 Multilingual interface  \n\n🔔 Official channel with updates, news, and useful materials:  \n👉 https://t.me/sub_pr  \n\n💡 For any questions — write to [Support] in the main menu",
        "adm_stats": "📊 Statistics\n\nTotal users: {users}\nActive chats: {chats}\nMessages in DB: {msgs}\nActive subscriptions: {subs}\nActive mutes: {mutes}\nWarnings: {warns}\nServer time: {time}",
        "adm_broadcast_prompt": "📡 Broadcast\n\nSend text, photo, video or animation for broadcasting to all users.",
        "adm_logs": "📋 System logs\n\nLast 10 actions:\n{logs}",
        "adm_group_manage": "🛠 Groups management\n\nSelect a group to set up.",
        "adm_group_logs": "📝 Groups logs\n\n{logs}",
        "adm_create_func_prompt": "Enter function name and description separated by space: name description",
        "adm_create_func_success": "✅ Function {name} created with description: {desc}",
        "adm_create_func_format": "Format: name description",
        "service_msgs_menu": "Service messages\n\nSelect what to delete: left, joined, pinned, photo/title change, Telegram notifications, bot messages.",
        "op_invalid_id": "❌ Invalid channel ID. Must start with -100 or be a number.",
        "op_invite_limit": "Optional: subscriptions count: /setup ID link 100",
        "log_entry": "Admin: @{admin_username} ({admin_id})\nTarget: @{target_username} ({target_id})\nAction: {action}\nTerm: {term}\nReason: {reason}\nChat: {chat_title} ({chat_id})\nDate: {date}",
        "no_groups_added": "No added groups.",
    },
    'uk': {
        "welcome_private": "👋 Ласкаво просимо, {user_name}!\n\nSUB PR — бот для керування підписками, безпекою чатів та модерацією.\n\nВикористовуйте меню нижче для керування ботом:",
        "menu_add_group": "➕ Додати до групи",
        "menu_settings": "⚙ Налаштування групи",
        "menu_info": "💬 Про бота",
        "menu_support": "🛟 Підтримка",
        "menu_profile": "👤 Профіль",
        "menu_languages": "🌍 Мова",
        "menu_admin": "🔒 Адмін меню",
        "menu_our_chat": "Наш чат",
        "menu_our_channel": "Наш канал",
        "menu_auto_delete": "🧹 Авто-видалення",
        "menu_welcome_rules": "📝 Привітання та правила",
        "menu_user_check": "🔍 Перевірка користувача",
        "menu_group_settings": "⚙️ Налаштування груп",
        "menu_manage_subs": "🛡 Керування підписками",
        "lang_changed": "✅ Мову змінено на **{lang}**.",
        "lang_choose": "🌐 Оберіть мову / Choose Language / Оберіть мову:",
        "lang_back": "🔙 Назад",
        "lang_title_ru": "🇷🇺 Російська",
        "lang_title_en": "🇺🇸 Англійська",
        "lang_title_uk": "🇺🇦 Українська",
        "admin_panel_title": "🎛 Панель Адміністратора\nГоловне меню керування ботом.",
        "no_rights": "⛔ У вас немає прав доступу до цього меню. Ви не власник бота.",
        "group_welcome": "👋 Привіт! Я — {bot_name}.\n\nЯ допомагаю керувати групою та підписками. Щоб налаштувати мене, перейдіть в ПП.",
        "group_go_private": "🤖 Перейти в ПП для налаштування",
        "setup_info": "ℹ️ Використання:\n/setup @channel [час]\n\nПриклад: /setup @MyChannel 1d",
        "setup_error_time": "⚠️ Помилка: Неправильний формат часу. Використовуйте: 30m, 1h, 5d тощо.",
        "setup_error_not_channel": "⚠️ Помилка: Це не канал або супергрупа.",
        "setup_error_unknown_channel": "⚠️ Помилка: Я не бачу цей канал. Переконайтеся, що він існує та його юзернейм правильний.",
        "setup_success": "✅ Канал додано!\nТепер підписка на {channel} обов'язкова {info}.",
        "setup_info_forever": "назавжди",
        "setup_info_until": "до {date}",
        "unsetup_usage": "ℹ️ Використання: /unsetup @channel\n\nУ цьому чаті немає активних вимог підписки.",
        "unsetup_list": "ℹ️ Поточні обов'язкові підписки:\n{channels}\n\nВведіть команду з юзернеймом для видалення.",
        "unsetup_deleted": "🗑 Вимогу підписки на {channel} видалено.",
        "unsetup_not_found": "❌ Помилка: Підписка на {channel} не знайдена в списку обов'язкових для цього чату.",
        "cmd_no_reply": "↩️ Відповідайте на повідомлення користувача.",
        "cmd_no_id_reply": "ℹ️ ID або реплай.",
        "no_admin_rights": "⛔ Тільки адміністратори можуть використовувати цю команду.",
        "ban_success": "⛔ Забанено: {user_name}\nПричина: {reason}",
        "ban_error": "❌ Помилка бану: {error}",
        "unban_success": "🕊 Розбанено: {user_id}",
        "unban_error": "❌ Помилка розбану: {error}",
        "mute_error_time": "⚠️ Неправильний формат часу. Використовуйте: 30m, 1h, 5d.",
        "mute_success": "🔇 Мут на {duration}: {user_name}\nАвтоматичний розмут: {date}\nПричина: {reason}",
        "mute_error": "❌ Помилка муту: {error}",
        "unmute_success": "🔊 Мут знято з {user_name}.",
        "unmute_error": "❌ Помилка розмуту: {error}",
        "warn_reason": "Порушення правил чату",
        "warn_limit_ban": "⛔ Бан за варни ({count}/{limit}): {user_name}\nПричина: {reason}",
        "warn_added": "⚠️ Варн ({count}/{limit}): {user_name}\nПричина: {reason}",
        "kick_success": "👢 Кікнуто: {user_name}.\nПричина: {reason}",
        "kick_error": "❌ Помилка кіку: {error}",
        "sub_access_denied": "🚫 Доступ обмежено, {user_name}!\n\nЩоб писати в цей чат, необхідно підписатися на наступні канали.",
        "sub_button_text": "👉 Підписатися на {channel}",
        "sub_button_verify": "✅ Я підписався",
        "sub_verified": "✅ Доступ дозволено! Можете писати в чат.",
        "sub_not_all": "❌ Ви підписалися не на всі канали! Повторіть перевірку після підписки.",
        "settings_info": "⚙️ Налаштування групи\n\nТут ви можете налаштувати фільтри, привітання та підписки. Використовуйте /setup в чаті.",
        "support_prompt": "📞 Підтримка\n\nНапишіть ваше повідомлення для підтримки:",
        "support_received": "✅ Ваше повідомлення надіслано в підтримку! Очікуйте відповіді.",
        "support_from_user": "📩 Повідомлення від користувача {user_name} (@{username}, ID: {user_id}):\n\n{text}",
        "support_reply": "Відповісти",
        "support_dismiss": "Відхилити",
        "support_response": "📨 Відповідь від підтримки:\n\n{text}",
        "user_check_prompt": "🔍 Перевірка користувача\n\nВведіть ID або @username:",
        "user_check_not_found": "❌ Користувача не знайдено.",
        "user_check_info": "Інформація про користувача:\nID: {user_id}\nІм'я: {first_name}\nПрізвище: {last_name}\nUsername: @{username}\n\nЧати:\n{chats}\n\nВарни: {warns}\nМути: {mutes}",
        "group_settings_title": "⚙️ Налаштування груп\n\nОберіть групу:",
        "group_settings_details": "Налаштування для {chat_title} (ID: {chat_id})\nТип: {chat_type}\nСтатус: {status}\nДодано: {added_by}\n\nФункції:\n- ОП (Публічний канал): {op_pub}\n- ОП (Приватний канал): {op_priv}\n- ОП (Інвайт-посилання): {op_inv}\n- Анти-флуд: {flood}\n- Авто-видалення повідомлень: {auto_del}\n- Привітання нових учасників: {welcome}\n- Правила групи: {rules}\n- Службові повідомлення: {service}",
        "anti_flood_on": "✅ Антифлуд увімкнено.",
        "anti_flood_off": "❌ Антифлуд вимкнено.",
        "set_welcome_success": "✅ Привітання встановлено.",
        "set_rules_success": "✅ Правила встановлено.",
        "rules": "Правила чату:\n{text}",
        "welcome_new_member": "👋 Ласкаво просимо, {user_name}!\n\n{rules}",
        "no_bot_admin": "⚠️ Бот не адмін в {channel}.\n\nДодайте в адміни спочатку.",
        "status_text": "📋 Активні перевірки:\n\n{list}",
        "status_empty": "Немає активних перевірок.",
        "profile_text": "💳 Ваш профіль\n━━━━━━━━━━━━━━━\n🆔 ID: {user_id}\n👤 Нік: @{username}\n📅 Реєстрація: {reg_date}\n━━━━━━━━━━━━━━━\nВаші активні чати:\n{chats}",
        "op_public": "✅ Функція перевірки підписки на публічні канали/чати 🛡️\n\n"
                     "▸ Крок 1: Додайте мене в адміни каналу/чату для перевірки.\n"
                     "▸ Крок 2: У вашому чаті: /setup @channel та час (60s, 60m, 24h, 1d).\n\n"
                     "⛔ Для вимкнення: /unsetup @channel ❌\n\n"
                     "➕ Макс. 5 перевірок!\n\n"
                     "💡 /status покаже активні перевірки та таймери. ⏰\n\n"
                     "Питання? В підтримку 📞",
        "op_private": "📢 Перевірка підписки для приватних каналів/чатів:\n\n"
                      "Крок 1: Дізнайтеся ID приватного каналу.\n"
                      "Крок 2: У чаті: /setup 1001994526641\n\n"
                      "Вимкнути: /unsetup 1001994526641\n\n"
                      "💡 /status для меню перегляду та редагування.",
        "op_invite": "🔗 Перевірка підписки на запрошувальні посилання.\n\n"
                     "Крок 1: Дізнайтеся ID приватного каналу.\n"
                     "Крок 2: /setup 1001994526641 https://t.me/+Link\n\n"
                     "Вимкнути: /unsetup 1001994526641\n\n"
                     "Ліміт підписок: /setup ... 100\n"
                     "Таймер: /setup ... 1d (s/m/h/d)\n\n"
                     "💡 /status для керування.",
        "op_error": "❌ Я не можу встановити перевірку підписки. Причина: я не адміністратор каналу/чату {channel}.",
        "op_max": "❌ Перевищено максимальну кількість перевірок (5). Видаліть старі через /unsetup.",
        "op_invalid_format": "❌ Неправильний формат команди. Використовуйте /setup @channel або /setup ID [посилання] [ліміт] [час].",
        "op_group_list": "Список ваших груп:\n\n{chats}",
        "antiflood_menu": "🚫 Анти-флуд\n\nОберіть ліміт:\n- 3 повідомлення / 5 сек\n- 5 повідомлень / 10 сек\n- 10 повідомлень / 30 сек\n\nДія: {action}",
        "antiflood_action_warn": "⚠ Попередження",
        "antiflood_action_mute": "🔇 Мут",
        "antiflood_action_delete": "🧹 Видалення повідомлень",
        "antiflood_action_off": "❌ Вимкнути",
        "antiflood_set": "✅ Анти-флуд встановлено: {limit} повідомлень / {time} сек. Дія: {action}.",
        "autodel_menu": "🧹 Авто-видалення\n\nОберіть тип повідомлень для видалення:\n- ОП\n- Анти-флуд\n- Службові (покинув, приєднався, закріпив, зміна фото/назви, сповіщення Telegram, повідомлення бота)\n\nТаймер: {timer}",
        "autodel_timer_10s": "10s",
        "autodel_timer_30s": "30s",
        "autodel_timer_1m": "1m",
        "autodel_timer_15m": "15m",
        "autodel_timer_1h": "1h",
        "autodel_timer_1d": "1d",
        "autodel_timer_instant": "Миттєво",
        "autodel_set": "✅ Авто-видалення встановлено для {types} з таймером {timer}.",
        "welcome_rules_menu": "📝 Привітання та правила\n\nРедагуйте привітання: /set_welcome текст\nПравила: /set_rules текст\nАвто-видалення привітань: {auto_del}",
        "info_text": "📢 SUB PR — потужний бот для захисту та керування вашими чатами\n\n🔹 Підписка на канали та чати (ОП) — публічні, приватні та за інвайт-посиланням  \n🔹 Анти-флуд з гнучкими налаштуваннями  \n🔹 Модерація: бан, кік, мут, варн (через команди або свайп по повідомленню)  \n🔹 Авто-видалення службових повідомлень, ОП та анти-флуду  \n🔹 Красиві привітання та правила  \n🔹 Зручна панель керування прямо в Telegram  \n🔹 Підтримка 24/7  \n🔹 Багатомовний інтерфейс  \n\n🔔 Офіційний канал з оновленнями, новинами та корисними матеріалами:  \n👉 https://t.me/sub_pr  \n\n💡 З усіх питань — пишіть в [Підтримку] в головному меню",
        "adm_stats": "📊 Статистика\n\nВсього користувачів: {users}\nАктивні чати: {chats}\nПовідомлень в базі: {msgs}\nАктивних підписок: {subs}\nАктивних мутів: {mutes}\nПопереджень: {warns}\nЧас сервера: {time}",
        "adm_broadcast_prompt": "📡 Розсилка\n\nНадішліть текст, фото, відео або анімацію для розсилки всім користувачам.",
        "adm_logs": "📋 Логи системи\n\nОстанні 10 дій:\n{logs}",
        "adm_group_manage": "🛠 Керування групами\n\nОберіть групу для налаштування.",
        "adm_group_logs": "📝 Логи груп\n\n{logs}",
        "adm_create_func_prompt": "Введіть ім'я функції та опис через пробіл: ім'я опис",
        "adm_create_func_success": "✅ Функцію {name} створено з описом: {desc}",
        "adm_create_func_format": "Формат: ім'я опис",
        "service_msgs_menu": "Службові повідомлення\n\nОберіть, що видаляти: покинув, приєднався, закріпив, зміна фото/назви, сповіщення Telegram, повідомлення бота.",
        "op_invalid_id": "❌ Неправильний ID каналу. Повинен починатися з -100 або бути числом.",
        "op_invite_limit": "Опціонально: кількість підписок: /setup ID посилання 100",
        "log_entry": "Адмін: @{admin_username} ({admin_id})\nЦіль: @{target_username} ({target_id})\nДія: {action}\nТермін: {term}\nПричина: {reason}\nЧат: {chat_title} ({chat_id})\nДата: {date}",
        "no_groups_added": "Немає доданих груп.",
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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS first_start (
            user_id INTEGER PRIMARY KEY,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS group_settings (
            chat_id INTEGER PRIMARY KEY,
            anti_flood BOOLEAN DEFAULT 0,
            welcome_text TEXT,
            rules_text TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER,
            chat_id INTEGER,
            chat_title TEXT,
            UNIQUE(user_id, chat_id)
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS broadcast_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            success_count INTEGER,
            fail_count INTEGER,
            created_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS additional_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            setting_name TEXT,
            setting_value TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            total_messages INTEGER DEFAULT 0,
            last_activity TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_stats (
            chat_id INTEGER PRIMARY KEY,
            total_members INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS subscription_limits (
            chat_id INTEGER PRIMARY KEY,
            max_subs INTEGER DEFAULT 5
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS invite_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            link TEXT,
            sub_limit INTEGER
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS private_channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER,
            added_by INTEGER
        )
        """)
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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS bot_chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            type TEXT,
            added_at TEXT
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_functions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            description TEXT,
            code TEXT
        )
        """)
        # Индексы
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_required_subs_chat ON required_subs(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_members_user_chat ON members(user_id, chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_warns_user_chat ON warns(user_id, chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_mutes_chat_user ON mutes(chat_id, user_id)"
        ]
        for index in indexes:
            conn.execute(index)
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
        return datetime.fromisoformat(iso_str.replace('Z', '+00:00'))
    except (ValueError, TypeError):
        return None

def format_readable_date(iso_str):
    dt = parse_iso_datetime(iso_str)
    lang = get_user_language(ADMIN_ID)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M")
    else:
        if lang == 'ru':
            return "Бессрочно"
        elif lang == 'en':
            return "Forever"
        elif lang == 'uk':
            return "Назавжди"
        return "Forever"

def sanitize_text(text):
    if not text: return ""
    return str(text).replace("&", "&").replace("<", "<").replace(">", ">").replace('"', """).replace("'", "'")

def get_full_user_name(user):
    name = ""
    if user.first_name:
        name += user.first_name
    if user.last_name:
        name += " " + user.last_name
    return name or "Anonymous"

def check_admin_rights(chat_id, user_id):
    if user_id == ADMIN_ID: return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ADMIN_STATUSES or member.can_change_info or member.can_delete_messages or member.can_restrict_members
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
        bot.send_message(LOG_CHANNEL, f"ЛОГ: {action} - {details}\nЧат: {chat_id}\nПользователь: {user_id}\n<Наш бот - @{BOT_USERNAME}>")
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
            conn.execute("UPDATE user_stats SET total_messages = total_messages + 1, last_activity = ? WHERE user_id = ?", (get_iso_now(), user.id))
            conn.execute("UPDATE chat_stats SET total_messages = total_messages + 1 WHERE chat_id = ?", (chat_id,))
            conn.execute("INSERT OR REPLACE INTO user_groups (user_id, chat_id, chat_title) VALUES (?, ?, ?)",
                         (user.id, chat_id, bot.get_chat(chat_id).title or f"Chat {chat_id}"))
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
                            bot.send_message(
                                mute['chat_id'], 
                                f"🔊 Мут знято з {mute['user_id']}\n<Наш бот - @{BOT_USERNAME}>"
                            )
                            log_system_action(mute['chat_id'], mute['user_id'], "UNMUTE_AUTO", f"Автоматичний розмут. Закінчився в {format_readable_date(mute['expires_at'])}")
                        except Exception as e:
                            print(f"Failed to unmute {mute['user_id']}: {e}")
                        finally:
                            conn.execute("DELETE FROM mutes WHERE id = ?", (mute['id'],))
                conn.commit()
        except Exception as e:
            print(f"Worker Error: {e}")
        time.sleep(20)

def resolve_username(username):
    if username.startswith('@'):
        username = username[1:]
    try:
        return bot.get_chat(f"@{username}").id
    except:
        return None

def generate_start_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    add_url = f"https://t.me/{BOT_USERNAME}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_chat+promote_members"
    lang_flag = LANG_FLAGS[get_user_language(user_id)]
    markup.row(InlineKeyboardButton(get_string(user_id, "menu_profile"), callback_data="profile"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_add_group"), url=add_url),
               InlineKeyboardButton(get_string(user_id, "menu_settings"), callback_data="group_settings"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_our_chat"), url="https://t.me/vzref2"),
               InlineKeyboardButton(get_string(user_id, "menu_our_channel"), url="https://t.me/sub_pr"))
    markup.add(InlineKeyboardButton(get_string(user_id, "menu_info"), callback_data="info"),
               InlineKeyboardButton(get_string(user_id, "menu_support"), callback_data="support"))
    markup.row(InlineKeyboardButton(f"{lang_flag} {get_string(user_id, 'menu_languages')}", callback_data="languages"))
    if user_id == ADMIN_ID:
        markup.row(InlineKeyboardButton(get_string(user_id, "menu_admin"), callback_data="adm_main"))
    return markup

def generate_group_settings_keyboard(user_id, for_admin=False):
    markup = InlineKeyboardMarkup(row_width=1)
    with get_db_connection() as conn:
        if for_admin:
            chats = conn.execute("SELECT chat_id, title FROM bot_chats").fetchall()
        else:
            chats = conn.execute("SELECT chat_id, chat_title FROM user_groups WHERE user_id = ?", (user_id,)).fetchall()
    for chat in chats:
        chat_id = chat['chat_id']
        title = chat['title'] or chat.get('chat_title') or f"Chat {chat_id}"
        link = f"https://t.me/c/{str(chat_id)[4:]}" if str(chat_id).startswith('-100') else f"https://t.me/{title.lstrip('@')}"
        markup.add(InlineKeyboardButton(title, callback_data=f"group_set:{chat_id}", url=link))
    if not chats:
        bot.send_message(user_id, get_string(user_id, "no_groups_added"))
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

def generate_languages_keyboard(user_id):
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton(get_string(user_id, "lang_title_ru"), callback_data="lang_ru"),
        InlineKeyboardButton(get_string(user_id, "lang_title_en"), callback_data="lang_en"),
        InlineKeyboardButton(get_string(user_id, "lang_title_uk"), callback_data="lang_uk")
    )
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="main_menu"))
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

def generate_management_keyboard(user_id):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📋 Показать все подписки", callback_data="mng_show_subs"))
    markup.add(InlineKeyboardButton("➕ Добавить подписку (через /setup в чате)", callback_data="mng_info_add"))
    markup.add(InlineKeyboardButton("➖ Удалить подписку (по ID)", callback_data="mng_del_sub_start"))
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data="adm_main_menu"))
    return markup

def generate_back_button(user_id, callback_data="adm_main_menu"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(get_string(user_id, "lang_back"), callback_data=callback_data))
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
        except:
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

def check_bot_admin_in_channel(channel):
    try:
        bot_member = bot.get_chat_member(channel, bot.get_me().id)
        return bot_member.status in ADMIN_STATUSES
    except Exception:
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

    if data == "profile":
        with get_db_connection() as conn:
            reg = conn.execute("SELECT created_at FROM first_start WHERE user_id = ?", (user_id,)).fetchone()
            reg_date = format_readable_date(reg['created_at']) if reg else "Неизвестно"
            groups = conn.execute("SELECT chat_title FROM user_groups WHERE user_id = ?", (user_id,)).fetchall()
            chats_list = "\n".join([f"• {g['chat_title']}" for g in groups]) or "Нет"
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
            chats_text = "\n".join([f"• {chat['chat_title']} [Настроить]" for chat in chats]) or "Нет активных чатов."
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
            added_by = f"@{bot.get_chat_member(target_chat_id, added_by['added_by']).user.username}" if added_by else "Неизвестно"
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
        limit_time = data.split(":")[1].split("_")
        target_chat_id = data.split(":")[2]
        with get_db_connection() as conn:
            conn.execute("INSERT OR REPLACE INTO antiflood_settings (chat_id, msg_limit, time_sec) VALUES (?, ?, ?)", (target_chat_id, int(limit_time[0]), int(limit_time[1])))
            conn.commit()
        bot.answer_callback_query(call.id, get_string(user_id, "antiflood_set").format(limit=limit_time[0], time=limit_time[1], action="текущий"))
        call.data = f"flood:{target_chat_id}"
        callback_query_handler(call)
        return

    if data.startswith("flood_act:"):
        action = data.split(":")[1]
        target_chat_id = data.split(":")[2]
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
        type_ = data.split(":")[1]
        target_chat_id = data.split(":")[2]
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
        timer = data.split(":")[1]
        target_chat_id = data.split(":")[2]
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
        bot.edit_message_text(get_string(user_id, "adm_group_manage"), chat_id, msg_id, reply_markup=generate_group_settings_keyboard(user_id, for_admin=True))
        return

    if data == "adm_group_logs":
        with get_db_connection() as conn:
            logs = conn.execute("SELECT * FROM mod_logs ORDER BY id DESC LIMIT ?", (MAX_LOG_ENTRIES,)).fetchall()
        logs_text = ""
        for log in logs:
            try:
                admin_user = bot.get_chat_member(log['admin_id'], log['admin_id']).user
                target_user = bot.get_chat_member(log['target_id'], log['target_id']).user
                chat = bot.get_chat(log['chat_id'])
                chat_title = chat.title or "Chat"
                chat_link = f"https://t.me/c/{str(log['chat_id'])[4:]}" if str(log['chat_id']).startswith('-100') else f"https://t.me/{chat.username}"
                logs_text += get_string(user_id, "log_entry").format(
                    admin_id=log['admin_id'], admin_username=admin_user.username or "unknown",
                    target_id=log['target_id'], target_username=target_user.username or "unknown",
                    action=log['action'], term=log['term'] or "", reason=log['reason'] or "",
                    chat_id=log['chat_id'], chat_link=chat_link, chat_title=chat_title, date=log['date']
                ) + "\n\n"
            except:
                continue
        text = get_string(user_id, "adm_group_logs").format(logs=logs_text or "Нет логов.")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=generate_back_button(user_id, "adm_main"), disable_web_page_preview=True)
        return

    if data == "adm_create_func":
        user_id = call.from_user.id
        if user_id != ADMIN_ID: return
        _local_memory[user_id] = "waiting_create_func"
        bot.edit_message_text(get_string(user_id, "adm_create_func_prompt"), call.message.chat.id, call.message.message_id, reply_markup=generate_back_button(user_id, "adm_main"))

    if data == "adm_manage_subs":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="🛡 Управление обязательными подписками\n\nЗдесь вы можете посмотреть и удалить активные требования подписки.",
            reply_markup=generate_management_keyboard(user_id)
        )

    if data == "mng_info_add":
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="ℹ️ Добавление подписки\n\n"
                 "Чтобы добавить обязательную подписку для группы, вам нужно использовать команду /setup в самой группе, где бот является администратором.\n\n"
                 "Формат: /setup @username_канала [время_действия]\n"
                 "Пример: /setup @MyChannel 1d (на 1 день)\n"
                 "Пример: /setup @MyChannel (навсегда)",
            reply_markup=generate_back_button(user_id, "adm_manage_subs")
        )

    if data == "mng_show_subs":
        with get_db_connection() as conn:
            subs = conn.execute("SELECT id, chat_id, channel, expires FROM required_subs ORDER BY chat_id, channel").fetchall()

        sub_list_text = "📋 Активные требования подписок:\n\n"
        if not subs:
            sub_list_text += "Нет активных требований подписки ни в одном из чатов."
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
                    
                    sub_list_text += f"\n--- 👥 {chat_name} (ID: {current_chat_id}) ---\n"
                
                expiry_str = format_readable_date(sub['expires'])
                sub_list_text += f"• [ID:{sub['id']}] {sub['channel']} (до: {expiry_str})\n"

        bot.edit_message_text(
            chat_id=chat_id, 
            message_id=msg_id, 
            text=sub_list_text, 
            reply_markup=generate_back_button(user_id, "adm_manage_subs")
        )

    if data == "mng_del_sub_start":
        with get_db_connection() as conn:
            subs = conn.execute("SELECT id, chat_id, channel, expires FROM required_subs ORDER BY id DESC LIMIT 50").fetchall()
        
        if not subs:
            bot.edit_message_text(
                chat_id=chat_id, 
                message_id=msg_id, 
                text="❌ Нет подписок для удаления.", 
                reply_markup=generate_back_button(user_id, "adm_manage_subs")
            )
            return
            
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="➖ Выберите подписку для удаления:\n\nОтображаются последние 50 записей.",
            reply_markup=generate_delete_subscription_keyboard(user_id, subs)
        )

    if data.startswith("mng_del_sub:"):
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

    if data == "support":
        bot.edit_message_text(get_string(user_id, "support_prompt"), chat_id, msg_id, reply_markup=generate_back_button(user_id, "main_menu"))
        _local_memory[user_id] = "waiting_support"
        return

    if data.startswith("support_reply:"):
        target_user_id = int(data.split(":")[1])
        _local_memory[user_id] = {"reply_to": target_user_id}
        bot.edit_message_text("Ответьте на это сообщение текстом для отправки ответа пользователю.", chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    if data == "support_dismiss":
        try:
            bot.delete_message(chat_id, msg_id)
        except:
            pass
        return

    if data == "verify_subscription":
        required_channels = get_required_channels_for_chat(call.message.chat.id)
        still_missing = [channel for channel in required_channels if not check_subscription_status(user_id, channel)]
        if not still_missing:
            try:
                bot.delete_message(call.message.chat.id, msg_id)
            except:
                pass
            bot.answer_callback_query(call.id, get_string(user_id, "sub_verified"))
        else:
            bot.answer_callback_query(call.id, get_string(user_id, "sub_not_all"), show_alert=True)
        return

    if data == "languages":
        bot.edit_message_text(get_string(user_id, "lang_choose"), chat_id, msg_id, reply_markup=generate_languages_keyboard(user_id))
        return

    if data.startswith("lang_"):
        lang_code = data.split("_")[1]
        set_user_language(user_id, lang_code)
        bot.edit_message_text(get_string(user_id, "lang_changed").format(lang=LANGUAGES[lang_code]), chat_id, msg_id, reply_markup=generate_start_keyboard(user_id))
        return

    if data == "adm_user_check":
        _local_memory[user_id] = "waiting_user_check"
        bot.edit_message_text(get_string(user_id, "user_check_prompt"), chat_id, msg_id, reply_markup=generate_back_button(user_id, "adm_main"))
        return

    if data == "auto_delete":
        user_id = call.from_user.id
        bot.edit_message_text(get_string(user_id, "autodel_menu").format(types="", timer=""), call.message.chat.id, call.message.message_id, reply_markup=generate_autodel_keyboard(user_id, 0))  # chat_id=0 placeholder if needed

    if data == "welcome_rules":
        user_id = call.from_user.id
        bot.edit_message_text(get_string(user_id, "welcome_rules_menu").format(auto_del=""), call.message.chat.id, call.message.message_id, reply_markup=generate_welcome_rules_keyboard(user_id, 0))  # placeholder

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

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_support", content_types=['text'])
def process_support(message):
    user_id = message.from_user.id
    text = message.text
    username = message.from_user.username or "нет"
    user_name = get_full_user_name(message.from_user)
    _local_memory.pop(user_id, None)

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(get_string(ADMIN_ID, "support_reply"), callback_data=f"support_reply:{user_id}"))
    markup.add(InlineKeyboardButton(get_string(ADMIN_ID, "support_dismiss"), callback_data="support_dismiss"))

    bot.send_message(ADMIN_ID, get_string(ADMIN_ID, "support_from_user").format(user_name=user_name, username=username, user_id=user_id, text=text), reply_markup=markup)
    bot.reply_to(message, get_string(user_id, "support_received"))

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id, {}).get("reply_to"), content_types=['text'])
def process_support_reply(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return
    target_user_id = _local_memory[user_id]["reply_to"]
    text = message.text
    _local_memory.pop(user_id)

    bot.send_message(target_user_id, get_string(target_user_id, "support_response").format(text=text))
    bot.reply_to(message, "✅ Ответ отправлен.")

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_broadcast", content_types=['text', 'photo', 'video', 'animation'])
def process_broadcast(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return
    _local_memory.pop(user_id, None)

    bot.send_message(user_id, "⏳ Начинаю рассылку... Это может занять время.")

    success_count = 0
    fail_count = 0

    with get_db_connection() as conn:
        users = conn.execute("SELECT user_id FROM first_start").fetchall()

    for user_row in users:
        target_id = user_row['user_id']
        if target_id == user_id: continue

        try:
            bot.copy_message(target_id, message.chat.id, message.message_id)
            success_count += 1
            time.sleep(0.04) 
        except Exception:
            fail_count += 1

    result_message = f"✅ Рассылка завершена!\n\nУспешно: {success_count}\nОшибок (заблокировали/удалили): {fail_count}"
    bot.send_message(user_id, result_message)
    log_system_action(user_id, user_id, "BROADCAST_END", f"Рассылка завершена. Успешно: {success_count}, Ошибок: {fail_count}")

@bot.message_handler(func=lambda m: m.chat.type == 'private' and _local_memory.get(m.from_user.id) == "waiting_user_check", content_types=['text'])
def process_user_check(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return
    input_str = message.text.strip()
    _local_memory.pop(user_id, None)

    target_id = None
    if input_str.startswith("@"):
        try:
            user_info = bot.get_chat(input_str)
            target_id = user_info.id
        except:
            bot.reply_to(message, get_string(user_id, "user_check_not_found"))
            return
    else:
        try:
            target_id = int(input_str)
        except:
            bot.reply_to(message, get_string(user_id, "user_check_not_found"))
            return

    with get_db_connection() as conn:
        member_info = conn.execute("SELECT * FROM members WHERE user_id = ?", (target_id,)).fetchall()
        warns = conn.execute("SELECT COUNT(*) FROM warns WHERE user_id = ?", (target_id,)).fetchone()[0]
        mutes = conn.execute("SELECT COUNT(*) FROM mutes WHERE user_id = ?", (target_id,)).fetchone()[0]

    if not member_info:
        bot.reply_to(message, get_string(user_id, "user_check_not_found"))
        return

    user = bot.get_chat_member(target_id, target_id).user
    first_name = user.first_name or "Нет"
    last_name = user.last_name or "Нет"
    username = user.username or "нет"

    chats_list = "\n".join([f"- Chat {m['chat_id']}: сообщений {m['messages_count']}, последний раз {format_readable_date(m['last_seen'])}" for m in member_info]) or "Нет"

    info_text = get_string(user_id, "user_check_info").format(
        user_id=target_id,
        first_name=first_name,
        last_name=last_name,
        username=username,
        chats=chats_list,
        warns=warns,
        mutes=mutes
    )
    bot.reply_to(message, info_text)

@bot.message_handler(commands=['start'])
def command_start_handler(message):
    user_id = message.from_user.id
    user_lang = get_user_language(user_id)

    with get_db_connection() as conn:
        conn.execute("INSERT OR IGNORE INTO first_start (user_id, created_at) VALUES (?, ?)", (user_id, get_iso_now()))
        conn.commit()

    if message.chat.type in ['group', 'supergroup', 'channel']:
        bot_info = bot.get_me()
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(get_string(user_id, "group_go_private"), url=f"https://t.me/{BOT_USERNAME}?start=settings"))
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
        exists = conn.execute("SELECT 1 FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel)).fetchone()
        if not exists:
            bot.reply_to(message, get_string(user_id, "unsetup_not_found").format(channel=channel))
            return
        conn.execute("DELETE FROM required_subs WHERE chat_id = ? AND channel = ?", (message.chat.id, channel))
        conn.commit()
    bot.reply_to(message, get_string(user_id, "unsetup_deleted").format(channel=channel))

@bot.message_handler(commands=['status'])
def command_status(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return

    with get_db_connection() as conn:
        subs = conn.execute("SELECT channel, expires FROM required_subs WHERE chat_id = ?", (message.chat.id,)).fetchall()
    list_text = ""
    for i, sub in enumerate(subs, 1):
        until = format_readable_date(sub['expires'])
        channel = sub['channel'] if sub['channel'].startswith('@') else f"@{sub['channel']}"
        list_text += f"{i}. {channel} — до {until}\n/unsetup {channel} — Убрать\n———————————————\n"
    text = get_string(user_id, "status_text").format(list=list_text or get_string(user_id, "status_empty"))
    bot.reply_to(message, text)

@bot.message_handler(commands=['ban', 'kick', 'mute', 'warn'])
def mod_commands(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return
    cmd = message.text.split()[0][1:]
    args = message.text.split()[1:]
    target_id = None
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
    elif args and (args[0].isdigit() or args[0].startswith('@')):
        if args[0].isdigit():
            target_id = int(args[0])
        else:
            target_id = resolve_username(args[0])
        args = args[1:]
    if not target_id:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return
    term = args[0] if args and parse_time_string(args[0]) and cmd in ['mute'] else ""
    reason = " ".join(args[1:] if term else args) or get_string(user_id, "warn_reason")
    # Выполнить действие
    if cmd == 'ban':
        try:
            bot.ban_chat_member(message.chat.id, target_id)
            text = get_string(user_id, "ban_success").format(user_name=get_full_user_name(bot.get_chat_member(message.chat.id, target_id).user), reason=reason)
        except Exception as e:
            text = get_string(user_id, "ban_error").format(error=e)
    elif cmd == 'kick':
        try:
            bot.ban_chat_member(message.chat.id, target_id)
            bot.unban_chat_member(message.chat.id, target_id)
            text = get_string(user_id, "kick_success").format(user_name=get_full_user_name(bot.get_chat_member(message.chat.id, target_id).user), reason=reason)
        except Exception as e:
            text = get_string(user_id, "kick_error").format(error=e)
    elif cmd == 'mute':
        delta = parse_time_string(term)
        if not delta:
            bot.reply_to(message, get_string(user_id, "mute_error_time"))
            return
        until = datetime.utcnow() + delta
        try:
            bot.restrict_chat_member(message.chat.id, target_id, until_date=until.timestamp(), permissions=ChatPermissions(can_send_messages=False))
            with get_db_connection() as conn:
                conn.execute("INSERT OR REPLACE INTO mutes (chat_id, user_id, expires_at) VALUES (?, ?, ?)", (message.chat.id, target_id, until.isoformat()))
                conn.commit()
            text = get_string(user_id, "mute_success").format(duration=term, user_name=get_full_user_name(bot.get_chat_member(message.chat.id, target_id).user), date=until.strftime("%Y-%m-%d %H:%M"), reason=reason)
        except Exception as e:
            text = get_string(user_id, "mute_error").format(error=e)
    elif cmd == 'warn':
        with get_db_connection() as conn:
            conn.execute("INSERT INTO warns (chat_id, user_id, admin_id, reason, created_at) VALUES (?, ?, ?, ?, ?)", (message.chat.id, target_id, user_id, reason, get_iso_now()))
            count = conn.execute("SELECT COUNT(*) FROM warns WHERE chat_id = ? AND user_id = ?", (message.chat.id, target_id)).fetchone()[0]
            conn.commit()
        if count >= 3:
            bot.ban_chat_member(message.chat.id, target_id)
            text = get_string(user_id, "warn_limit_ban").format(count=count, limit=3, user_name=get_full_user_name(bot.get_chat_member(message.chat.id, target_id).user), reason=reason)
        else:
            text = get_string(user_id, "warn_added").format(count=count, limit=3, user_name=get_full_user_name(bot.get_chat_member(message.chat.id, target_id).user), reason=reason)
    bot.reply_to(message, text)
    # Логировать
    with get_db_connection() as conn:
        conn.execute("INSERT INTO mod_logs (chat_id, admin_id, target_id, action, term, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?)", (message.chat.id, user_id, target_id, cmd.upper(), term, reason, get_iso_now()))
        conn.commit()
    return

@bot.message_handler(commands=['unban'])
def command_unban(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return

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

@bot.message_handler(commands=['unmute'])
def command_unmute(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return
    if not message.reply_to_message:
        bot.reply_to(message, get_string(user_id, "cmd_no_reply"))
        return

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

@bot.message_handler(commands=['rules'])
def command_rules(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return

    with get_db_connection() as conn:
        rules = conn.execute("SELECT rules_text FROM group_settings WHERE chat_id = ?", (message.chat.id,)).fetchone()

    text = rules['rules_text'] if rules and rules['rules_text'] else "Правила не установлены."
    bot.reply_to(message, get_string(user_id, "rules").format(text=text))

@bot.message_handler(content_types=['new_chat_members'])
def handle_new_member(message):
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            with get_db_connection() as conn:
                conn.execute("INSERT OR IGNORE INTO bot_chats (chat_id, title, type, added_at) VALUES (?, ?, ?, ?)",
                             (message.chat.id, message.chat.title, message.chat.type, get_iso_now()))
                conn.commit()
    # Для приветствия
    user_id = message.new_chat_members[0].id
    user_lang = get_user_language(user_id)
    user_name = get_full_user_name(message.new_chat_members[0])

    with get_db_connection() as conn:
        settings = conn.execute("SELECT welcome_text, rules_text FROM group_settings WHERE chat_id = ?", (message.chat.id,)).fetchone()

    welcome = settings['welcome_text'] if settings and settings['welcome_text'] else ""
    rules = settings['rules_text'] if settings and settings['rules_text'] else ""

    bot.send_message(message.chat.id, get_string(user_id, "welcome_new_member").format(user_name=user_name, rules=rules + "\n" + welcome))

@bot.message_handler(commands=['anti_flood'])
def command_anti_flood(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return

    args = message.text.split()
    if len(args) < 2 or args[1] not in ['on', 'off']:
        bot.reply_to(message, "Использование: /anti_flood on/off")
        return

    status = 1 if args[1] == 'on' else 0
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO group_settings (chat_id, anti_flood) VALUES (?, ?)", (message.chat.id, status))
        conn.commit()

    bot.reply_to(message, get_string(user_id, "anti_flood_on") if status else get_string(user_id, "anti_flood_off"))

@bot.message_handler(commands=['set_welcome'])
def command_set_welcome(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return

    text = " ".join(message.text.split()[1:])
    if not text:
        bot.reply_to(message, "Использование: /set_welcome текст")
        return

    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO group_settings (chat_id, welcome_text) VALUES (?, ?)", (message.chat.id, text))
        conn.commit()

    bot.reply_to(message, get_string(user_id, "set_welcome_success"))

@bot.message_handler(commands=['set_rules'])
def command_set_rules(message):
    user_id = message.from_user.id
    if message.chat.type not in ['group', 'supergroup']:
        return
    if not check_admin_rights(message.chat.id, user_id):
        return

    text = " ".join(message.text.split()[1:])
    if not text:
        bot.reply_to(message, "Использование: /set_rules текст")
        return

    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO group_settings (chat_id, rules_text) VALUES (?, ?)", (message.chat.id, text))
        conn.commit()

    bot.reply_to(message, get_string(user_id, "set_rules_success"))

# Для анти-флуда
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
                mod_commands(message)  # Вызвать warn с cmd='warn'
            return
    # ОП проверка
    required_channels = get_required_channels_for_chat(chat_id)
    if not required_channels:
        return

    missing_channels = [channel for channel in required_channels if not check_subscription_status(user_id, channel)]

    if missing_channels:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass 
        
        warning_text = get_string(user_id, "sub_access_denied").format(user_name=sanitize_text(get_full_user_name(message.from_user)))
        
        try:
            bot.send_message(
                message.chat.id,
                warning_text + f"\n\n<Наш бот - @{BOT_USERNAME}>",
                reply_markup=generate_subscription_keyboard(user_id, missing_channels),
                disable_notification=True,
            )
        except:
            pass
    # Авто-удаление: добавить timer для удаления сообщений бота/служебных
    if message.new_chat_members or message.left_chat_member or message.pinned_message or message.new_chat_photo or message.new_chat_title or message.from_user.is_bot:
        with get_db_connection() as conn:
            autodel = conn.execute("SELECT timer FROM autodel_settings WHERE chat_id = ? AND types LIKE '%service%'", (chat_id,)).fetchone()
            service = conn.execute("SELECT * FROM service_msgs WHERE chat_id = ?", (chat_id,)).fetchone()
        if autodel and service:
            # Проверить, нужно ли удалять этот тип
            if (message.left_chat_member and service['delete_left']) or (message.new_chat_members and service['delete_joined']) :  # Добавить все типы
                delta = parse_time_string(autodel['timer'])
                if delta:
                    time.sleep(delta.total_seconds())
                    bot.delete_message(chat_id, message.message_id)

@bot.message_handler(func=lambda m: _local_memory.get(m.from_user.id) == "waiting_create_func")
def process_create_func(message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID: return
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        bot.reply_to(message, get_string(user_id, "adm_create_func_format"))
        return
    name, desc = args
    with get_db_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO custom_functions (name, description) VALUES (?, ?)", (name, desc))
        conn.commit()
    bot.reply_to(message, get_string(user_id, "adm_create_func_success").format(name=name, desc=desc))
    _local_memory.pop(user_id)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.chat.type in ['group', 'supergroup']:
        group_message_processor(message)
        update_user_activity(message.from_user, message.chat.id)

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
