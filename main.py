#!/usr/bin/env python3
"""
Anony SMS Bot - Ultimate Version v6.0
Fully functional with all features
"""

import os
import sys
import time
import json
import logging
import qrcode
import threading
from datetime import datetime, timedelta
from io import BytesIO
from contextlib import contextmanager
import sqlite3
import requests
import random
import string

from flask import Flask, request, jsonify
from telebot import TeleBot, types
from telebot.apihelper import ApiException

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
CHANNEL = os.getenv("CHANNEL", "")
WEBHOOK_HOST = "https://songaura.onrender.com"
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = "data.db"

ANTISPAM_INTERVAL = 2

# ====== ЛОГГИРОВАНИЕ ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# ====== ПЕРЕВОДЫ ======
TRANSLATIONS = {
    'ru': {
        # Основные
        'start': """🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉

Рады видеть тебя 💬✨
Здесь тайны и эмоции превращаются в сообщения 👀💌

<b>🔥 Отправляй и получай абсолютно анонимные сообщения —</b>
никаких имён, только честность, интрига и эмоции 🕶️✨

<b>Хочешь узнать, что о тебе думают друзья?</b>
Получить тайное признание или анонимный комплимент? 😏💖

<b>🔗 Твоя личная ссылка:</b>
<code>{link}</code>

<b>🚀 Поделись ею в чатах или сторис —</b>
и жди анонимные сообщения 💌🤫

<b>Каждое сообщение — маленькая загадка</b> 👀✨

👇 <b>Жми кнопки ниже и погнали!</b> 🚀""",
        
        'my_link': """🔗 <b>Твоя уникальная ссылка для анонимок:</b>

<code>{link}</code>

<i>📤 Поделись с друзьями в:
• Чатах 💬
• Соцсетях 🌐
• Сторис 📲

🎭 Каждый переход — новый анонимный отправитель!
🔥 Чем больше делишься, тем больше тайн узнаёшь 😏</i>""",
        
        'profile': """👤 <b>Твой профиль</b>

<b>📊 Идентификация:</b>
├ ID: <code>{user_id}</code>
├ Имя: <b>{first_name}</b>
└ Юзернейм: {username}

<b>📈 Статистика:</b>
├ 📨 Получено: <b>{received}</b>
├ 📤 Отправлено: <b>{sent}</b>
├ 🔗 Переходов: <b>{clicks}</b>
└ ⏱️ Сред. время ответа: <b>{response_time}</b>

<b>⚙️ Настройки:</b>
├ Приём сообщений: {receive_status}
├ Язык: {language}
└ Последняя активность: {last_active}

<b>📊 Детальная статистика:</b>
├ Пик активности: <b>{peak_hour}:00</b>
├ Самый активный день: <b>{active_day}</b>
└ Любимый тип: <b>{fav_type}</b>

<b>🔗 Твоя ссылка:</b>
<code>{link}</code>""",
        
        'anonymous_message': """📨 <b>Ты получил анонимное сообщение!</b>

<i>💭 Кто-то отправил тебе тайное послание...</i>

{text}

<i>🎭 Отправитель останется неизвестным...</i>""",
        
        'message_sent': """✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Получатель: <b>{receiver_name}</b>
🔒 Твоя личность: <b>скрыта</b>
💭 Сообщение доставлено успешно!</i>

<b>Хочешь отправить ещё?</b>
Просто продолжай писать ✍️""",
        
        'help': """ℹ️ <b>Полное руководство по Anony SMS</b>

<b>🎯 Что это такое?</b>
Anony SMS — это бот для <b>полностью анонимных</b> сообщений! 
Никто не узнает, кто отправил послание 👻

<b>📨 КАК ПОЛУЧАТЬ сообщения:</b>
1. Нажми «📩 Моя ссылка»
2. Скопируй свою уникальную ссылку
3. Поделись с друзьями
4. Жди анонимные сообщения! 💌

<b>✉️ КАК ОТПРАВЛЯТЬ сообщения:</b>
1. Перейди по чужой ссылке
2. Напиши сообщение
3. Отправь — получатель не узнает твою личность! 🎭

<b>📎 ЧТО МОЖНО ОТПРАВИТЬ:</b>
✅ Текстовые сообщения ✍️
✅ Фотографии 📸
✅ Видео 🎬
✅ Голосовые сообщения 🎤
✅ Стикеры 😜
✅ GIF 🎞️
✅ Документы 📎

<b>⚙️ НАСТРОЙКИ:</b>
• Включить/выключить приём сообщений
• Просмотр статистики
• Генерация QR-кода

<b>🔒 БЕЗОПАСНОСТЬ:</b>
• <b>Полная анонимность</b>
• Конфиденциальность гарантирована 🔐

<b>🆘 ПОДДЕРЖКА:</b>
Возникли проблемы? Нажми «🆘 Поддержка»""",
        
        'support': """🆘 <b>Служба поддержки</b>

<i>Опишите вашу проблему как можно подробнее 💭
Мы постараемся ответить в кратчайшие сроки ⏰</i>

<b>📎 Что можно отправить:</b>
• Текстовое описание проблемы ✍️
• Скриншот ошибки 📸
• Видео с багом 🎬
• Любой медиафайл 📎""",
        
        'support_sent': """✅ <b>Запрос в поддержку отправлен!</b>

<i>Ваш тикет: <b>#{ticket_id}</b>
Мы ответим вам в ближайшее время ⏰</i>""",
        
        'settings': "⚙️ <b>Настройки</b>\n\n<i>Настрой бот под себя:</i>",
        'turn_on': "✅ <b>Приём анонимных сообщений включён!</b>\n\n<i>Теперь друзья могут отправлять тебе тайные послания 🔮</i>",
        'turn_off': "✅ <b>Приём анонимных сообщений отключён!</b>\n\n<i>Ты не будешь получать новые анонимки 🔒\nМожешь включить в любой момент ⚡</i>",
        'language': "🌐 <b>Выберите язык</b>\n\n<i>Выбор языка изменит интерфейс бота.</i>",
        'blocked': "🚫 Вы заблокированы в этом боте.",
        'user_not_found': "❌ Пользователь не найден.",
        'messages_disabled': "❌ Этот пользователь отключил получение сообщений.",
        'wait': "⏳ Подождите 2 секунды перед следующим сообщением.",
        'canceled': "❌ Действие отменено",
        'spam_wait': "⏳ Подождите 2 секунды перед следующим сообщением.",
        'qr_code': """📱 <b>Твой персональный QR-код</b>

<i>Сканируй и отправляй анонимные сообщения мгновенно! ⚡</i>

<b>🔗 Ссылка:</b>
<code>{link}</code>""",
        
        # Статистика пользователя
        'user_stats': """📊 <b>Твоя детальная статистика</b>

<b>📈 ОСНОВНЫЕ МЕТРИКИ:</b>
├ 📨 Получено: <b>{received}</b> сообщений
├ 📤 Отправлено: <b>{sent}</b> сообщений
├ 🔗 Переходов: <b>{clicks}</b> раз
└ ⏱️ Сред. ответ: <b>{response_time}</b>

<b>📅 АКТИВНОСТЬ:</b>
├ 📆 Зарегистрирован: <b>{registered}</b>
├ 📅 Последняя активность: <b>{last_active}</b>
└ 🕐 Сред. время в боте: <b>{avg_time}</b> мин/день

<b>📊 ДЕТАЛЬНО:</b>
├ 📈 Активность по часам: {hours_chart}
├ 📅 Активность по дням: {days_chart}
└ 📝 Типы сообщений: {types_chart}

<b>🏆 АЧИВКИ:</b>
{achievements}""",
        
        # Админ
        'admin_panel': "👑 <b>Панель администратора</b>\n\n<i>Доступ к управлению ботом 🔧</i>",
        'admin_stats': """👑 <b>Статистика бота</b>

<b>📊 ОСНОВНЫЕ МЕТРИКИ:</b>
├ Всего пользователей: <b>{total_users}</b>
├ Активных сегодня: <b>{today_active}</b>
├ Всего сообщений: <b>{total_messages}</b>
├ Сообщений за 24ч: <b>{messages_24h}</b>
├ Новых за 24ч: <b>{new_users_24h}</b>
├ Заблокированных: <b>{blocked_users}</b>
├ Открытых тикетов: <b>{open_tickets}</b>
└ Сред. активность в час: <b>{avg_hourly}</b>

<b>📈 ДЕТАЛЬНАЯ СТАТИСТИКА:</b>
├ Пользователей за неделю: <b>{users_week}</b>
├ Сообщений за неделю: <b>{messages_week}</b>
├ Активных за неделю: <b>{active_week}</b>
├ Удерживание (30 дней): <b>{retention_30d}%</b>
└ Конверсия в сообщения: <b>{conversion_rate}%</b>

<b>📱 ПОЛЬЗОВАТЕЛИ ПО ДНЯМ:</b>
{users_by_day}

<b>📨 СООБЩЕНИЯ ПО ДНЯМ:</b>
{messages_by_day}

<b>👥 ТОП-10 АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:</b>
{top_users}""",
        
        'broadcast_start': """📢 <b>Создание рассылки</b>

<i>Отправь сообщение которое будет отправлено всем пользователям.</i>

<b>📎 Можно отправить:</b>
• Текст с HTML-разметкой ✍️
• Фото с подписью 📸
• Видео с описанием 🎬
• Документ с комментарием 📎
• Стикер 😜""",
        
        'broadcast_progress': "⏳ <b>Начинаю рассылку...</b>\n\nВсего пользователей: {total}",
        'broadcast_result': """✅ <b>Рассылка завершена!</b>

<b>📊 РЕЗУЛЬТАТЫ:</b>
├ Всего пользователей: <b>{total}</b>
├ Успешно отправлено: <b>{sent}</b>
├ Не удалось отправить: <b>{failed}</b>
└ Пропущено (заблок.): <b>{blocked}</b>""",
        
        'users_management': "👥 <b>Управление пользователями</b>\n\n<i>Поиск и управление пользователями бота 🔧</i>",
        
        'find_user': "🔍 <b>Поиск пользователя</b>\n\n<i>Введите ID пользователя или юзернейм (без @):</i>",
        'user_info': """🔍 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

<b>👤 ОСНОВНЫЕ ДАННЫЕ:</b>
├ ID: <code>{user_id}</code>
├ Имя: <b>{first_name}</b>
├ Юзернейм: {username}
├ Зарегистрирован: {registered}
└ Последняя активность: {last_active}

<b>📊 СТАТИСТИКА:</b>
├ 📨 Получено: <b>{received}</b>
├ 📤 Отправлено: <b>{sent}</b>
├ 🔗 Переходов: <b>{clicks}</b>
└ ⚙️ Приём сообщений: {receive_status}

<b>🚫 СТАТУС:</b> {block_status}""",
        
        'logs': "📋 <b>Логи сообщений</b>",
        'no_logs': "📋 <b>Логи сообщений пусты</b>\n\n<i>Пока нет отправленных сообщений.</i>",
        'tickets': "🆘 <b>Открытые тикеты</b>",
        'no_tickets': "🆘 <b>Открытых тикетов нет</b>\n\n<i>Все обращения обработаны ✅</i>",
        'admin_settings': """⚙️ <b>Настройки администратора</b>

<b>🔔 УВЕДОМЛЕНИЯ:</b>
├ Новые сообщения: {notifications}
└ В канал: {channel_status}

<b>⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:</b>
├ Антиспам: {antispam} сек.
└ База данных: ✅ Работает""",
        
        'direct_message': """✉️ <b>Отправь сообщение для пользователя</b> <code>{user_id}</code>

<i>Сообщение придёт как от бота 🤖
Можно отправить текст, фото или видео.</i>""",
        
        'message_sent_admin': """✅ <b>Сообщение отправлено</b>

👤 Пользователь: <code>{user_id}</code>
📝 Тип: {message_type}""",
        
        'block_user': "✅ Пользователь <code>{user_id}</code> заблокирован.",
        'unblock_user': "✅ Пользователь <code>{user_id}</code> разблокирован.",
        'user_blocked': "🚫 <b>Пользователь заблокирован</b>",
        'user_already_blocked': "✅ Пользователь уже заблокирован",
        'user_not_blocked': "✅ Пользователь не заблокирован",
        
        # Новые переводы
        'main_menu': "🏠 Главное меню",
        'just_now': "только что",
        'minutes_ago': "{minutes} минут назад",
        'hours_ago': "{hours} часов назад",
        'yesterday': "вчера",
        'days_ago': "{days} дней назад",
        'never': "никогда",
        'language_changed': "✅ Язык изменен",
        'send_anonymous_to': "Отправь анонимное сообщение",
        'send_anonymous_description': "Напиши сообщение, фото, видео или голосовое сообщение",
        'send_reply': "Отправь ответное сообщение",
        'reply_to_ticket': "Ответить на тикет",
        'user_blocked_bot': "❌ Пользователь заблокировал бота",
        'text': "Текст",
        
        # Кнопки
        'btn_my_link': "📩 Моя ссылка",
        'btn_profile': "👤 Профиль",
        'btn_stats': "📊 Статистика",
        'btn_settings': "⚙️ Настройки",
        'btn_qr': "📱 QR-код",
        'btn_help': "ℹ️ Помощь",
        'btn_support': "🆘 Поддержка",
        'btn_admin': "👑 Админ",
        'btn_turn_on': "🔔 Вкл. сообщения",
        'btn_turn_off': "🔕 Выкл. сообщения",
        'btn_language': "🌐 Язык",
        'btn_back': "⬅️ Назад",
        'btn_cancel': "❌ Отмена",
        'btn_history': "📜 История",
        
        'btn_admin_stats': "📊 Статистика",
        'btn_admin_broadcast': "📢 Рассылка",
        'btn_admin_manage_users': "👥 Управление",
        'btn_admin_find': "🔍 Найти",
        'btn_admin_logs': "📋 Логи",
        'btn_admin_tickets': "🆘 Тикеты",
        'btn_admin_settings': "⚙️ Настройки",
        'btn_admin_block': "🚫 Блок/Разблок",
        'btn_admin_backup': "💾 Бэкап",
        'btn_admin_export': "📤 Экспорт",
        
        'btn_reply': "💌 Ответить",
        'btn_ignore': "🚫 Игнор",
        'btn_block': "🚫 Заблокировать",
        'btn_unblock': "✅ Разблокировать",
        'btn_message': "✉️ Написать ему",
        'btn_refresh': "🔄 Обновить",
        'btn_toggle_text': "🔕 Скрыть текст",
        'btn_show_text': "🔔 Показать текст",
        'btn_reply_ticket': "📝 Ответить",
        'btn_close_ticket': "✅ Закрыть",
        
        # Языки
        'lang_ru': "🇷🇺 Русский",
        'lang_en': "🇺🇸 English",
        
        # Блокировка
        'block_instruction': "🚫 <b>Блокировка/Разблокировка пользователя</b>\n\nВведите ID пользователя или юзернейм (без @):",
        'block_success': "✅ Пользователь <code>{user_id}</code> заблокирован.",
        'unblock_success': "✅ Пользователь <code>{user_id}</code> разблокирован.",
        'block_already': "✅ Пользователь уже заблокирован.",
        'user_not_blocked_msg': "✅ Пользователь не был заблокирован.",
        
        # История
        'history': "📜 <b>История сообщений</b>\n\n<i>Последние 20 сообщений:</i>",
        'history_empty': "📜 <b>У тебя пока нет сообщений</b>\n\n<i>Начни общение, отправив первую анонимку!</i>",
        'history_item': """<b>{index}. {direction} {name}</b> <i>({time})</i>
💬 <i>{preview}</i>""",
        'history_incoming': "⬇️ От",
        'history_outgoing': "⬆️ Кому",
        
        # Экспорт
        'export_instruction': "📤 <b>Экспорт данных</b>\n\n<i>Выберите что экспортировать:</i>",
        'export_users': "👥 Экспорт пользователей",
        'export_messages': "📨 Экспорт сообщений",
        'export_stats': "📊 Экспорт статистики",
        'export_processing': "⏳ <b>Экспорт данных...</b>\n\n<i>Пожалуйста, подождите.</i>",
        'export_complete': "✅ <b>Экспорт завершен!</b>\n\n<i>Данные успешно сохранены.</i>",
    }
}

def t(lang, key, **kwargs):
    """Функция перевода"""
    if lang not in TRANSLATIONS:
        lang = 'ru'
    if key not in TRANSLATIONS[lang]:
        if 'ru' in TRANSLATIONS and key in TRANSLATIONS['ru']:
            return TRANSLATIONS['ru'][key].format(**kwargs) if kwargs else TRANSLATIONS['ru'][key]
        return key
    return TRANSLATIONS[lang][key].format(**kwargs) if kwargs else TRANSLATIONS[lang][key]

# Глобальные переменные
last_message_time = {}
user_reply_targets = {}
admin_modes = {}
admin_log_settings = {ADMIN_ID: {'show_text': True}}
user_stats_cache = {}

# ====== БАЗА ДАННЫХ ======
class Database:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB error: {e}")
            raise
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Пользователи
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    language TEXT DEFAULT 'ru',
                    created_at INTEGER,
                    last_active INTEGER,
                    messages_received INTEGER DEFAULT 0,
                    messages_sent INTEGER DEFAULT 0,
                    link_clicks INTEGER DEFAULT 0,
                    receive_messages INTEGER DEFAULT 1
                )
            ''')
            
            # Сообщения
            c.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER,
                    receiver_id INTEGER,
                    message_type TEXT,
                    text TEXT,
                    file_id TEXT,
                    file_unique_id TEXT,
                    timestamp INTEGER,
                    replied_to INTEGER DEFAULT 0,
                    is_read INTEGER DEFAULT 0
                )
            ''')
            
            # Блокировки
            c.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id INTEGER PRIMARY KEY,
                    blocked_at INTEGER,
                    blocked_by INTEGER,
                    reason TEXT,
                    UNIQUE(user_id)
                )
            ''')
            
            # Поддержка
            c.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    file_id TEXT,
                    file_unique_id TEXT,
                    message_type TEXT,
                    status TEXT DEFAULT 'open',
                    created_at INTEGER,
                    admin_id INTEGER,
                    admin_reply TEXT,
                    replied_at INTEGER
                )
            ''')
            
            # Логи для админа
            c.execute('''
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_type TEXT,
                    user_id INTEGER,
                    target_id INTEGER,
                    details TEXT,
                    timestamp INTEGER
                )
            ''')
            
            # Настройки бота
            c.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')
            
            c.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value) 
                VALUES ('notifications_enabled', '1')
            ''')
            
            # Статистика пользователя
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    messages_by_hour TEXT DEFAULT '{}',
                    messages_by_day TEXT DEFAULT '{}',
                    message_types TEXT DEFAULT '{}',
                    total_time_spent INTEGER DEFAULT 0,
                    last_session_start INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # История сообщений пользователя
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_history (
                    user_id INTEGER,
                    partner_id INTEGER,
                    message_id INTEGER,
                    direction TEXT,
                    timestamp INTEGER,
                    preview TEXT,
                    PRIMARY KEY (user_id, message_id)
                )
            ''')
            
            # Клики по ссылкам
            c.execute('''
                CREATE TABLE IF NOT EXISTS link_clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    clicker_id INTEGER,
                    timestamp INTEGER
                )
            ''')
            
            logger.info("✅ База данных инициализирована")
    
    def register_user(self, user_id, username, first_name):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            
            c.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, created_at, last_active) 
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, now, now))
            
            c.execute('''
                UPDATE users SET 
                username = ?, 
                first_name = ?,
                last_active = ?
                WHERE user_id = ?
            ''', (username, first_name, now, user_id))
    
    def get_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    def get_user_by_username(self, username):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE username = ?', (username,))
            row = c.fetchone()
            return dict(row) if row else None
    
    def update_last_active(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET last_active = ? WHERE user_id = ?', 
                     (int(time.time()), user_id))
    
    def increment_stat(self, user_id, field):
        if field not in ['messages_received', 'messages_sent', 'link_clicks']:
            return
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(f'UPDATE users SET {field} = {field} + 1 WHERE user_id = ?', 
                     (user_id,))
    
    def set_receive_messages(self, user_id, status):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET receive_messages = ? WHERE user_id = ?',
                     (1 if status else 0, user_id))
    
    def set_language(self, user_id, language):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET language = ? WHERE user_id = ?',
                     (language, user_id))
    
    def get_all_users_list(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM users')
            rows = c.fetchall()
            return [row[0] for row in rows]
    
    def get_all_users_count(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM users')
            return c.fetchone()[0]
    
    def get_today_active_users(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            today = int(time.time()) - 86400
            c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp > ?', (today,))
            return c.fetchone()[0]
    
    def save_message(self, sender_id, receiver_id, message_type, text="", file_id=None, file_unique_id=None, replied_to=0):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO messages 
                (sender_id, receiver_id, message_type, text, file_id, file_unique_id, timestamp, replied_to) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sender_id, receiver_id, message_type, text, file_id, file_unique_id, int(time.time()), replied_to))
            message_id = c.lastrowid
            
            # Добавляем в историю отправителя
            preview = text[:50] if text else f"[{message_type}]"
            c.execute('''
                INSERT OR REPLACE INTO user_history 
                (user_id, partner_id, message_id, direction, timestamp, preview) 
                VALUES (?, ?, ?, 'outgoing', ?, ?)
            ''', (sender_id, receiver_id, message_id, int(time.time()), preview))
            
            # Добавляем в историю получателя
            c.execute('''
                INSERT OR REPLACE INTO user_history 
                (user_id, partner_id, message_id, direction, timestamp, preview) 
                VALUES (?, ?, ?, 'incoming', ?, ?)
            ''', (receiver_id, sender_id, message_id, int(time.time()), preview))
            
            # Обновляем статистику
            self.update_user_stats(sender_id, message_type)
            self.update_user_stats(receiver_id, message_type)
            
            return message_id
    
    def update_user_stats(self, user_id, message_type):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now()
            hour = now.hour
            day = now.strftime('%A')
            
            # Получаем текущую статистику
            c.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            
            if not row:
                # Создаем новую запись
                messages_by_hour = {str(hour): 1}
                messages_by_day = {day: 1}
                message_types = {message_type: 1}
                
                c.execute('''
                    INSERT INTO user_stats 
                    (user_id, messages_by_hour, messages_by_day, message_types, last_session_start) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, json.dumps(messages_by_hour), json.dumps(messages_by_day), 
                      json.dumps(message_types), int(time.time())))
            else:
                # Обновляем существующую запись
                messages_by_hour = json.loads(row['messages_by_hour'])
                messages_by_day = json.loads(row['messages_by_day'])
                message_types = json.loads(row['message_types'])
                
                # Обновляем часы
                hour_key = str(hour)
                messages_by_hour[hour_key] = messages_by_hour.get(hour_key, 0) + 1
                
                # Обновляем дни
                messages_by_day[day] = messages_by_day.get(day, 0) + 1
                
                # Обновляем типы сообщений
                message_types[message_type] = message_types.get(message_type, 0) + 1
                
                # Обновляем общее время в боте
                if row['last_session_start']:
                    session_time = int(time.time()) - row['last_session_start']
                    total_time = row['total_time_spent'] + min(session_time, 3600)  # Макс 1 час за сессию
                else:
                    total_time = row['total_time_spent']
                
                c.execute('''
                    UPDATE user_stats 
                    SET messages_by_hour = ?, messages_by_day = ?, message_types = ?, 
                        total_time_spent = ?, last_session_start = ?
                    WHERE user_id = ?
                ''', (json.dumps(messages_by_hour), json.dumps(messages_by_day), 
                      json.dumps(message_types), total_time, int(time.time()), user_id))
    
    def get_user_messages_stats(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            
            c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ?', (user_id,))
            sent_count = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE receiver_id = ?', (user_id,))
            received_count = c.fetchone()[0]
            
            return {
                'messages_sent': sent_count,
                'messages_received': received_count
            }
    
    def get_user_detailed_stats(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Основная информация
            user = self.get_user(user_id)
            if not user:
                return None
            
            # Статистика из таблицы user_stats
            c.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
            stats_row = c.fetchone()
            
            stats = {
                'user': user,
                'messages_by_hour': {},
                'messages_by_day': {},
                'message_types': {},
                'total_time_spent': 0,
                'avg_response_time': 0
            }
            
            if stats_row:
                stats['messages_by_hour'] = json.loads(stats_row['messages_by_hour'])
                stats['messages_by_day'] = json.loads(stats_row['messages_by_day'])
                stats['message_types'] = json.loads(stats_row['message_types'])
                stats['total_time_spent'] = stats_row['total_time_spent']
            
            # Вычисляем среднее время ответа
            c.execute('''
                SELECT m1.timestamp as sent_time, m2.timestamp as reply_time
                FROM messages m1
                JOIN messages m2 ON m2.replied_to = m1.id
                WHERE m1.receiver_id = ? AND m2.sender_id = ?
                ORDER BY m1.timestamp
            ''', (user_id, user_id))
            
            response_times = []
            for row in c.fetchall():
                response_time = row['reply_time'] - row['sent_time']
                if 0 < response_time < 3600:  # Игнорируем слишком быстрые или медленные ответы
                    response_times.append(response_time)
            
            if response_times:
                stats['avg_response_time'] = sum(response_times) / len(response_times)
            
            return stats
    
    def get_user_history(self, user_id, limit=20):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT h.*, u.first_name as partner_name, u.username as partner_username
                FROM user_history h
                LEFT JOIN users u ON h.partner_id = u.user_id
                WHERE h.user_id = ?
                ORDER BY h.timestamp DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = c.fetchall()
            history = []
            for row in rows:
                history.append({
                    'message_id': row['message_id'],
                    'partner_id': row['partner_id'],
                    'partner_name': row['partner_name'],
                    'partner_username': row['partner_username'],
                    'direction': row['direction'],
                    'timestamp': row['timestamp'],
                    'preview': row['preview']
                })
            return history
    
    def get_recent_messages(self, limit=10, include_text=True):
        with self.get_connection() as conn:
            c = conn.cursor()
            query = '''
                SELECT m.*, u1.first_name as sender_name, u1.username as sender_username,
                       u2.first_name as receiver_name, u2.username as receiver_username
                FROM messages m
                LEFT JOIN users u1 ON m.sender_id = u1.user_id
                LEFT JOIN users u2 ON m.receiver_id = u2.user_id
                ORDER BY m.timestamp DESC LIMIT ?
            '''
            c.execute(query, (limit,))
            rows = c.fetchall()
            messages = []
            for row in rows:
                msg = dict(row)
                if not include_text:
                    msg['text'] = '[СКРЫТО]' if msg['text'] else ''
                messages.append(msg)
            return messages
    
    def is_user_blocked(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            return c.fetchone() is not None
    
    def block_user(self, user_id, admin_id, reason=""):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            try:
                c.execute('''
                    INSERT OR IGNORE INTO blocked_users (user_id, blocked_at, blocked_by, reason)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, now, admin_id, reason))
                return True
            except:
                return False
    
    def unblock_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
            return c.rowcount > 0
    
    def get_blocked_users_count(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM blocked_users')
            return c.fetchone()[0]
    
    def create_support_ticket(self, user_id, message, file_id=None, file_unique_id=None, message_type="text"):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                INSERT INTO support_tickets 
                (user_id, message, file_id, file_unique_id, message_type, created_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, message, file_id, file_unique_id, message_type, now))
            return c.lastrowid
    
    def get_open_support_tickets(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT s.*, u.first_name, u.username 
                FROM support_tickets s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.status = 'open'
                ORDER BY s.created_at DESC
            ''')
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    def update_support_ticket(self, ticket_id, admin_id, reply_text, status='answered'):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                UPDATE support_tickets 
                SET admin_id = ?, admin_reply = ?, replied_at = ?, status = ?
                WHERE id = ?
            ''', (admin_id, reply_text, now, status, ticket_id))
    
    def add_admin_log(self, log_type, user_id, target_id=None, details=""):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO admin_logs (log_type, user_id, target_id, details, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (log_type, user_id, target_id, details, int(time.time())))
    
    def get_recent_logs(self, limit=50):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT l.*, u.username, u.first_name 
                FROM admin_logs l
                LEFT JOIN users u ON l.user_id = u.user_id
                ORDER BY l.timestamp DESC LIMIT ?
            ''', (limit,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    def get_setting(self, key, default=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
            row = c.fetchone()
            return row[0] if row else default
    
    def set_setting(self, key, value):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)', 
                     (key, value))
    
    def track_link_click(self, user_id, clicker_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO link_clicks (user_id, clicker_id, timestamp)
                VALUES (?, ?, ?)
            ''', (user_id, clicker_id, int(time.time())))
    
    def get_link_clicks_stats(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM link_clicks WHERE user_id = ?', (user_id,))
            total_clicks = c.fetchone()[0]
            
            c.execute('SELECT COUNT(DISTINCT clicker_id) FROM link_clicks WHERE user_id = ?', (user_id,))
            unique_clickers = c.fetchone()[0]
            
            return {
                'total_clicks': total_clicks,
                'unique_clickers': unique_clickers
            }
    
    def get_admin_stats(self):
        """Получение расширенной статистики бота"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Основные метрики
            c.execute('SELECT COUNT(*) FROM users')
            total_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages')
            total_messages = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM blocked_users')
            blocked_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM users WHERE created_at > ?', 
                     (int(time.time()) - 86400,))
            new_users_24h = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 86400,))
            messages_24h = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM support_tickets WHERE status = "open"')
            open_tickets = c.fetchone()[0]
            
            # Активные сегодня
            today_start = int(time.time()) - 86400
            c.execute('SELECT COUNT(DISTINCT user_id) FROM users WHERE last_active > ?', (today_start,))
            today_active = c.fetchone()[0]
            
            # Пользователи за неделю
            c.execute('SELECT COUNT(*) FROM users WHERE created_at > ?', 
                     (int(time.time()) - 604800,))
            users_week = c.fetchone()[0]
            
            # Сообщения за неделю
            c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 604800,))
            messages_week = c.fetchone()[0]
            
            # Активные за неделю
            c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 604800,))
            active_week = c.fetchone()[0]
            
            # Средняя активность в час
            c.execute('SELECT COUNT(*) / 24.0 FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 86400,))
            avg_hourly_result = c.fetchone()[0]
            avg_hourly = round(avg_hourly_result, 2) if avg_hourly_result else 0
            
            # Удерживание (пользователи, активные в последние 30 дней)
            c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 2592000,))
            active_30d = c.fetchone()[0]
            
            # Пользователи старше 30 дней
            c.execute('SELECT COUNT(*) FROM users WHERE created_at < ?', 
                     (int(time.time()) - 2592000,))
            old_users = c.fetchone()[0]
            
            retention_30d = round((active_30d / old_users * 100), 2) if old_users > 0 else 100
            
            # Конверсия (пользователи, отправившие хотя бы одно сообщение)
            c.execute('SELECT COUNT(DISTINCT sender_id) FROM messages')
            users_with_messages = c.fetchone()[0]
            
            conversion_rate = round((users_with_messages / total_users * 100), 2) if total_users > 0 else 0
            
            # Пользователи по дням (последние 7 дней)
            users_by_day_data = {}
            for i in range(7):
                day_start = int(time.time()) - (i * 86400) - 86400
                day_end = int(time.time()) - (i * 86400)
                c.execute('SELECT COUNT(*) FROM users WHERE created_at BETWEEN ? AND ?', 
                         (day_start, day_end))
                count = c.fetchone()[0]
                day_name = (datetime.fromtimestamp(day_end)).strftime('%d.%m')
                users_by_day_data[day_name] = count
            
            users_by_day = "\n".join([f"├ {day}: <b>{count}</b>" for day, count in users_by_day_data.items()])
            
            # Сообщения по дням
            messages_by_day_data = {}
            for i in range(7):
                day_start = int(time.time()) - (i * 86400) - 86400
                day_end = int(time.time()) - (i * 86400)
                c.execute('SELECT COUNT(*) FROM messages WHERE timestamp BETWEEN ? AND ?', 
                         (day_start, day_end))
                count = c.fetchone()[0]
                day_name = (datetime.fromtimestamp(day_end)).strftime('%d.%m')
                messages_by_day_data[day_name] = count
            
            messages_by_day = "\n".join([f"├ {day}: <b>{count}</b>" for day, count in messages_by_day_data.items()])
            
            # Топ-10 активных пользователей
            c.execute('''
                SELECT u.user_id, u.first_name, u.username, 
                       COUNT(m.id) as message_count
                FROM users u
                LEFT JOIN messages m ON u.user_id = m.sender_id OR u.user_id = m.receiver_id
                GROUP BY u.user_id
                ORDER BY message_count DESC
                LIMIT 10
            ''')
            top_users_rows = c.fetchall()
            
            top_users_lines = []
            for i, row in enumerate(top_users_rows, 1):
                username = f"@{row['username']}" if row['username'] else "нет"
                top_users_lines.append(f"{i}. {row['first_name']} ({username}): {row['message_count']} сообщ.")
            
            top_users = "\n".join(top_users_lines) if top_users_lines else "Нет данных"
            
            return {
                'total_users': total_users,
                'today_active': today_active,
                'total_messages': total_messages,
                'messages_24h': messages_24h,
                'new_users_24h': new_users_24h,
                'blocked_users': blocked_users,
                'open_tickets': open_tickets,
                'users_week': users_week,
                'messages_week': messages_week,
                'active_week': active_week,
                'avg_hourly': avg_hourly,
                'retention_30d': retention_30d,
                'conversion_rate': conversion_rate,
                'users_by_day': users_by_day,
                'messages_by_day': messages_by_day,
                'top_users': top_users
            }

db = Database()

# ====== УТИЛИТЫ ======
def format_time(timestamp, lang='ru'):
    if not timestamp:
        return t(lang, 'never')
    
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return t(lang, 'just_now')
        elif diff.seconds < 3600:
            return t(lang, 'minutes_ago', minutes=diff.seconds // 60)
        else:
            return t(lang, 'hours_ago', hours=diff.seconds // 3600)
    elif diff.days == 1:
        return t(lang, 'yesterday')
    elif diff.days < 7:
        return t(lang, 'days_ago', days=diff.days)
    else:
        return dt.strftime("%d.%m.%Y")

def generate_link(user_id):
    bot_username = bot.get_me().username
    return f"https://t.me/{bot_username}?start={user_id}"

def check_spam(user_id):
    current_time = time.time()
    last_time = last_message_time.get(user_id, 0)
    
    if current_time - last_time < ANTISPAM_INTERVAL:
        return False
    
    last_message_time[user_id] = current_time
    return True

def get_message_reply_keyboard(target_id, lang='ru'):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply'), callback_data=f"reply_{target_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_ignore'), callback_data="ignore")
    )
    return keyboard

def get_admin_ticket_keyboard(ticket_id, user_id, lang='ru'):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply_ticket'), callback_data=f"support_reply_{ticket_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_close_ticket'), callback_data=f"support_close_{ticket_id}")
    )
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_profile'), callback_data=f"admin_user_{user_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_block'), callback_data=f"admin_block_{user_id}")
    )
    return keyboard

def get_admin_user_keyboard(user_id, is_blocked, lang='ru'):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if is_blocked:
        keyboard.add(
            types.InlineKeyboardButton(t(lang, 'btn_unblock'), callback_data=f"admin_unblock_{user_id}"),
            types.InlineKeyboardButton(t(lang, 'btn_message'), callback_data=f"admin_msg_{user_id}")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton(t(lang, 'btn_block'), callback_data=f"admin_block_{user_id}"),
            types.InlineKeyboardButton(t(lang, 'btn_message'), callback_data=f"admin_msg_{user_id}")
        )
    return keyboard

def get_admin_log_keyboard(show_text, lang='ru'):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_refresh'), callback_data="refresh_logs"),
        types.InlineKeyboardButton(t(lang, 'btn_toggle_text') if show_text else t(lang, 'btn_show_text'), 
                                 callback_data="toggle_text")
    )
    return keyboard

def create_chart(data, max_width=10):
    """Создает текстовую диаграмму"""
    if not data:
        return "Нет данных"
    
    max_value = max(data.values())
    result = []
    
    for key, value in sorted(data.items()):
        if max_value > 0:
            width = int((value / max_value) * max_width)
        else:
            width = 0
        bar = "█" * width + "░" * (max_width - width)
        result.append(f"{key}: {bar} {value}")
    
    return "\n".join(result)

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin=False, lang='ru'):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        types.KeyboardButton(t(lang, 'btn_my_link')),
        types.KeyboardButton(t(lang, 'btn_profile')),
        types.KeyboardButton(t(lang, 'btn_stats')),
        types.KeyboardButton(t(lang, 'btn_settings')),
        types.KeyboardButton(t(lang, 'btn_qr')),
        types.KeyboardButton(t(lang, 'btn_help')),
        types.KeyboardButton(t(lang, 'btn_support')),
        types.KeyboardButton(t(lang, 'btn_history'))
    ]
    
    if is_admin:
        buttons.append(types.KeyboardButton(t(lang, 'btn_admin')))
    
    keyboard.add(*buttons)
    return keyboard

def settings_keyboard(lang='ru'):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'btn_turn_on')),
        types.KeyboardButton(t(lang, 'btn_turn_off')),
        types.KeyboardButton(t(lang, 'btn_language')),
        types.KeyboardButton(t(lang, 'btn_back'))
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard(lang='ru'):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'btn_admin_stats')),
        types.KeyboardButton(t(lang, 'btn_admin_broadcast')),
        types.KeyboardButton(t(lang, 'btn_admin_find')),
        types.KeyboardButton(t(lang, 'btn_admin_block')),
        types.KeyboardButton(t(lang, 'btn_admin_logs')),
        types.KeyboardButton(t(lang, 'btn_admin_tickets')),
        types.KeyboardButton(t(lang, 'btn_admin_settings')),
        types.KeyboardButton(t(lang, 'btn_admin_backup')),
        types.KeyboardButton(t(lang, 'btn_admin_export')),
        types.KeyboardButton(t(lang, 'btn_back'))
    ]
    keyboard.add(*buttons)
    return keyboard

def cancel_keyboard(lang='ru'):
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add(t(lang, 'btn_cancel'))

def language_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    )
    return keyboard

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start', 'lang', 'menu', 'stats', 'history'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"START: user_id={user_id}")
    
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    args = message.text.split()
    
    # Обработка команды /lang
    if message.text.startswith('/lang'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'language'), reply_markup=language_keyboard())
        return
    
    # Обработка команды /menu
    if message.text.startswith('/menu'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    # Обработка команды /stats
    if message.text.startswith('/stats'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_user_stats(user_id, lang)
        return
    
    # Обработка команды /history
    if message.text.startswith('/history'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_user_history(user_id, lang)
        return
    
    # Обработка реферальной ссылки
    if len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])
        handle_link_click(user_id, target_id)
        return
    
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    link = generate_link(user_id)
    
    bot.send_message(user_id, t(lang, 'start', link=link), 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def handle_link_click(clicker_id, target_id):
    if not check_spam(clicker_id):
        bot.send_message(clicker_id, t('ru', 'spam_wait'))
        return
    
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, t('ru', 'user_not_found'))
        return
    
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, t('ru', 'messages_disabled'))
        return
    
    user_reply_targets[clicker_id] = target_id
    db.increment_stat(target_id, 'link_clicks')
    db.track_link_click(target_id, clicker_id)
    
    user = db.get_user(clicker_id)
    lang = user['language'] if user else 'ru'
    
    bot.send_message(
        clicker_id,
        f"💌 <b>{t(lang, 'send_anonymous_to')}</b> <i>{target_user['first_name']}</i>!\n\n"
        f"<i>{t(lang, 'send_anonymous_description')}</i>",
        reply_markup=cancel_keyboard(lang)
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    try:
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        
        if data == "ignore":
            bot.answer_callback_query(call.id, "✅ OK")
            return
        
        elif data == "refresh_logs":
            if user_id == ADMIN_ID:
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, "✅ Обновлено")
            return
        
        elif data == "toggle_text":
            if user_id == ADMIN_ID:
                current = admin_log_settings.get(user_id, {}).get('show_text', True)
                admin_log_settings[user_id] = {'show_text': not current}
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, "✅ Настройки изменены")
            return
        
        elif data == "refresh_tickets":
            if user_id == ADMIN_ID:
                show_support_tickets(user_id)
                bot.answer_callback_query(call.id, "✅ Обновлено")
            return
        
        elif data.startswith("lang_"):
            language = data.split("_")[1]
            db.set_language(user_id, language)
            bot.answer_callback_query(call.id, f"✅ {t(language, 'language_changed')}")
            
            link = generate_link(user_id)
            bot.send_message(user_id, t(language, 'start', link=link), 
                           reply_markup=main_keyboard(user_id == ADMIN_ID, language))
            return
        
        elif data.startswith("reply_"):
            target_id = int(data.split("_")[1])
            user_reply_targets[user_id] = target_id
            
            target_user = db.get_user(target_id)
            if target_user:
                bot.send_message(user_id, f"💌 {t(lang, 'send_reply')} {target_user['first_name']}", 
                               reply_markup=cancel_keyboard(lang))
            else:
                bot.send_message(user_id, t(lang, 'send_reply'), 
                               reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("admin_block_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            if db.block_user(target_id, ADMIN_ID, "Админ-панель"):
                db.add_admin_log("block", user_id, target_id, "Админ-панель")
                bot.answer_callback_query(call.id, t(lang, 'block_user', user_id=target_id))
                
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + f"\n\n{t(lang, 'user_blocked')}",
                        reply_markup=get_admin_user_keyboard(target_id, True, lang)
                    )
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, t(lang, 'user_already_blocked'))
        
        elif data.startswith("admin_unblock_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            if db.unblock_user(target_id):
                db.add_admin_log("unblock", user_id, target_id, "Админ-панель")
                bot.answer_callback_query(call.id, t(lang, 'unblock_user', user_id=target_id))
                
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + "\n\n✅ Разблокирован",
                        reply_markup=get_admin_user_keyboard(target_id, False, lang)
                    )
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, t(lang, 'user_not_blocked_msg'))
        
        elif data.startswith("admin_msg_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            admin_modes[user_id] = f'direct_msg_{target_id}'
            
            bot.send_message(user_id, t(lang, 'direct_message', user_id=target_id),
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_reply_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            ticket_id = int(data.split("_")[2])
            admin_modes[user_id] = f'support_reply_{ticket_id}'
            
            bot.send_message(user_id, f"📝 {t(lang, 'reply_to_ticket')} #{ticket_id}",
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_close_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            ticket_id = int(data.split("_")[2])
            db.update_support_ticket(ticket_id, user_id, "Закрыто", "closed")
            db.add_admin_log("ticket_close", user_id, None, f"Тикет #{ticket_id}")
            bot.answer_callback_query(call.id, "✅ Закрыто")
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + "\n\n✅ Тикет закрыт"
                )
            except:
                pass
        
        elif data.startswith("admin_user_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            find_user_info(admin_id=user_id, query=str(target_id))
            bot.answer_callback_query(call.id)
        
        else:
            bot.answer_callback_query(call.id, "⚠️ Неизвестная команда")
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# ====== ОСНОВНОЙ ОБРАБОТЧИК ======
@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    if message.text and message.text.startswith('/'):
        return
    
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    db.update_last_active(user_id)
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    
    if text == t(lang, 'btn_cancel'):
        clear_user_state(user_id)
        bot.send_message(user_id, t(lang, 'canceled'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    # Обработка кнопки "Админ"
    if text == t(lang, 'btn_admin') and user_id == ADMIN_ID:
        bot.send_message(user_id, t(lang, 'admin_panel'), 
                        reply_markup=admin_keyboard(lang))
        return
    
    if user_id == ADMIN_ID and user_id in admin_modes:
        mode = admin_modes[user_id]
        
        if mode.startswith('direct_msg_'):
            target_id = int(mode.split('_')[2])
            send_direct_admin_message(message, target_id, lang)
            if user_id in admin_modes:
                del admin_modes[user_id]
            return
        
        elif mode.startswith('support_reply_'):
            ticket_id = int(mode.split('_')[2])
            reply_to_support_ticket(message, ticket_id, lang)
            if user_id in admin_modes:
                del admin_modes[user_id]
            return
    
    if text == t(lang, 'btn_support'):
        handle_support_request(message, lang)
        return
    
    if user_id in user_reply_targets:
        target_id = user_reply_targets[user_id]
        send_anonymous_message(user_id, target_id, message, lang)
        return
    
    if user_id in admin_modes and admin_modes[user_id] == 'support':
        create_support_ticket(message, lang)
        if user_id in admin_modes:
            del admin_modes[user_id]
        return
    
    if message_type == 'text':
        handle_text_button(user_id, text, lang)

def clear_user_state(user_id):
    if user_id in user_reply_targets:
        del user_reply_targets[user_id]
    if user_id in admin_modes:
        del admin_modes[user_id]

def handle_text_button(user_id, text, lang):
    is_admin = user_id == ADMIN_ID
    
    if text == t(lang, 'btn_my_link'):
        link = generate_link(user_id)
        bot.send_message(user_id, t(lang, 'my_link', link=link),
                        reply_markup=main_keyboard(is_admin, lang))
    
    elif text == t(lang, 'btn_profile'):
        show_profile(user_id, lang)
    
    elif text == t(lang, 'btn_stats'):
        show_user_stats(user_id, lang)
    
    elif text == t(lang, 'btn_settings'):
        bot.send_message(user_id, t(lang, 'settings'),
                        reply_markup=settings_keyboard(lang))
    
    elif text == t(lang, 'btn_qr'):
        generate_qr_code(user_id, lang)
    
    elif text == t(lang, 'btn_help'):
        show_help(user_id, lang)
    
    elif text == t(lang, 'btn_history'):
        show_user_history(user_id, lang)
    
    elif text == t(lang, 'btn_turn_on'):
        db.set_receive_messages(user_id, True)
        bot.send_message(user_id, t(lang, 'turn_on'),
                        reply_markup=settings_keyboard(lang))
    
    elif text == t(lang, 'btn_turn_off'):
        db.set_receive_messages(user_id, False)
        bot.send_message(user_id, t(lang, 'turn_off'),
                        reply_markup=settings_keyboard(lang))
    
    elif text == t(lang, 'btn_language'):
        bot.send_message(user_id, t(lang, 'language'),
                        reply_markup=language_keyboard())
    
    elif text == t(lang, 'btn_back'):
        bot.send_message(user_id, t(lang, 'main_menu'),
                        reply_markup=main_keyboard(is_admin, lang))
    
    elif is_admin:
        handle_admin_command(user_id, text, lang)

def show_profile(user_id, lang):
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ Профиль не найден", reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    detailed_stats = db.get_user_detailed_stats(user_id)
    
    receive_status = "✅ Включён" if user['receive_messages'] else "❌ Выключен"
    username = f"@{user['username']}" if user['username'] else "❌ отсутствует"
    
    # Анализ статистики
    peak_hour = "N/A"
    active_day = "N/A"
    fav_type = "N/A"
    
    if detailed_stats:
        # Пиковая активность по часам
        if detailed_stats['messages_by_hour']:
            max_hour = max(detailed_stats['messages_by_hour'].items(), key=lambda x: x[1])
            peak_hour = max_hour[0]
        
        # Самый активный день
        if detailed_stats['messages_by_day']:
            max_day = max(detailed_stats['messages_by_day'].items(), key=lambda x: x[1])
            day_names = {
                'Monday': 'понедельник',
                'Tuesday': 'вторник',
                'Wednesday': 'среда',
                'Thursday': 'четверг',
                'Friday': 'пятница',
                'Saturday': 'суббота',
                'Sunday': 'воскресенье'
            }
            active_day = day_names.get(max_day[0], max_day[0])
        
        # Любимый тип сообщений
        if detailed_stats['message_types']:
            max_type = max(detailed_stats['message_types'].items(), key=lambda x: x[1])
            type_names = {
                'text': '📝 Текст',
                'photo': '📸 Фото',
                'video': '🎬 Видео',
                'voice': '🎤 Голос',
                'document': '📎 Документ',
                'sticker': '😜 Стикер'
            }
            fav_type = type_names.get(max_type[0], max_type[0])
    
    # Время ответа
    avg_response = detailed_stats['avg_response_time'] if detailed_stats and 'avg_response_time' in detailed_stats else 0
    response_time = f"{int(avg_response//60)} мин {int(avg_response%60)} сек" if avg_response > 0 else "N/A"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=stats['messages_received'],
                    sent=stats['messages_sent'],
                    clicks=user['link_clicks'],
                    response_time=response_time,
                    receive_status=receive_status,
                    language=user['language'].upper(),
                    last_active=format_time(user['last_active'], lang),
                    peak_hour=peak_hour,
                    active_day=active_day,
                    fav_type=fav_type,
                    link=generate_link(user_id))
    
    bot.send_message(user_id, profile_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_stats(user_id, lang):
    """Показывает детальную статистику пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ Пользователь не найден", reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    detailed_stats = db.get_user_detailed_stats(user_id)
    
    # Время ответа
    avg_response = detailed_stats['avg_response_time'] if detailed_stats and 'avg_response_time' in detailed_stats else 0
    response_time = f"{int(avg_response//60)} мин {int(avg_response%60)} сек" if avg_response > 0 else "N/A"
    
    # Среднее время в боте в день
    if detailed_stats and detailed_stats['total_time_spent'] > 0:
        days_registered = max(1, (time.time() - user['created_at']) / 86400)
        avg_time_per_day = detailed_stats['total_time_spent'] / days_registered / 60
        avg_time = f"{avg_time_per_day:.1f}"
    else:
        avg_time = "N/A"
    
    # Создаем графики
    hours_chart = create_chart(detailed_stats['messages_by_hour'] if detailed_stats else {}, 5)
    days_chart = create_chart(detailed_stats['messages_by_day'] if detailed_stats else {}, 5)
    types_chart = create_chart(detailed_stats['message_types'] if detailed_stats else {}, 5)
    
    # Определяем ачивки
    achievements = []
    if stats['messages_sent'] >= 100:
        achievements.append("🏆 Мастер анонимок (100+ отправленных)")
    elif stats['messages_sent'] >= 50:
        achievements.append("🥈 Любитель секретов (50+ отправленных)")
    elif stats['messages_sent'] >= 10:
        achievements.append("🥉 Новичок (10+ отправленных)")
    
    if stats['messages_received'] >= 100:
        achievements.append("🏆 Популярная личность (100+ полученных)")
    elif stats['messages_received'] >= 50:
        achievements.append("🥈 Интересный человек (50+ полученных)")
    elif stats['messages_received'] >= 10:
        achievements.append("🥉 Общительный (10+ полученных)")
    
    if user['link_clicks'] >= 100:
        achievements.append("🏆 Вирусная ссылка (100+ переходов)")
    elif user['link_clicks'] >= 50:
        achievements.append("🥈 Популярная ссылка (50+ переходов)")
    elif user['link_clicks'] >= 10:
        achievements.append("🥉 Активный (10+ переходов)")
    
    if not achievements:
        achievements.append("📌 Начни общение для получения ачивок!")
    
    achievements_text = "\n".join([f"├ {achievement}" for achievement in achievements])
    
    stats_text = t(lang, 'user_stats',
                  received=stats['messages_received'],
                  sent=stats['messages_sent'],
                  clicks=user['link_clicks'],
                  response_time=response_time,
                  registered=format_time(user['created_at'], lang),
                  last_active=format_time(user['last_active'], lang),
                  avg_time=avg_time,
                  hours_chart=hours_chart,
                  days_chart=days_chart,
                  types_chart=types_chart,
                  achievements=achievements_text)
    
    bot.send_message(user_id, stats_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_history(user_id, lang):
    """Показывает историю сообщений пользователя"""
    history = db.get_user_history(user_id, limit=20)
    
    if not history:
        bot.send_message(user_id, t(lang, 'history_empty'),
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    history_text = t(lang, 'history') + "\n\n"
    
    for i, item in enumerate(history, 1):
        direction = t(lang, 'history_incoming') if item['direction'] == 'incoming' else t(lang, 'history_outgoing')
        name = item['partner_name'] or f"ID: {item['partner_id']}"
        time_str = format_time(item['timestamp'], lang)
        
        history_text += t(lang, 'history_item',
                         index=i,
                         direction=direction,
                         name=name,
                         time=time_str,
                         preview=item['preview']) + "\n\n"
    
    bot.send_message(user_id, history_text,
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def send_anonymous_message(sender_id, receiver_id, message, lang):
    try:
        if not check_spam(sender_id):
            bot.send_message(sender_id, t(lang, 'spam_wait'))
            return
        
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, t(lang, 'messages_disabled'))
            return
        
        file_id = None
        file_unique_id = None
        message_type = message.content_type
        
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
            file_unique_id = message.photo[-1].file_unique_id
        elif message_type == 'video':
            file_id = message.video.file_id
            file_unique_id = message.video.file_unique_id
        elif message_type == 'audio':
            file_id = message.audio.file_id
            file_unique_id = message.audio.file_unique_id
        elif message_type == 'voice':
            file_id = message.voice.file_id
            file_unique_id = message.voice.file_unique_id
        elif message_type == 'document':
            file_id = message.document.file_id
            file_unique_id = message.document.file_unique_id
        elif message_type == 'sticker':
            file_id = message.sticker.file_id
            file_unique_id = message.sticker.file_unique_id
        
        message_id = db.save_message(sender_id, receiver_id, message_type, 
                       message.text or message.caption or "", 
                       file_id, file_unique_id)
        
        message_text = message.text or message.caption or ""
        caption = t(receiver['language'] if receiver else 'ru', 'anonymous_message', 
                   text=f"💬 <b>{t(receiver['language'] if receiver else 'ru', 'text')}:</b>\n<code>{message_text}</code>\n\n" if message_text else "")
        
        try:
            if message_type == 'text':
                msg = bot.send_message(receiver_id, caption, 
                                      reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            elif message_type == 'photo':
                msg = bot.send_photo(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            elif message_type == 'video':
                msg = bot.send_video(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            elif message_type == 'audio':
                msg = bot.send_audio(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            elif message_type == 'voice':
                msg = bot.send_voice(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            elif message_type == 'document':
                msg = bot.send_document(receiver_id, file_id, caption=caption,
                                      reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            elif message_type == 'sticker':
                if caption:
                    bot.send_message(receiver_id, caption)
                msg = bot.send_sticker(receiver_id, file_id, 
                                     reply_markup=get_message_reply_keyboard(sender_id, receiver['language'] if receiver else 'ru'))
            
        except ApiException as e:
            if e.error_code == 403:
                bot.send_message(sender_id, t(lang, 'user_blocked_bot'))
                return
            else:
                raise
        
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        bot.send_message(sender_id, t(lang, 'message_sent', receiver_name=receiver['first_name']),
                        reply_markup=cancel_keyboard(lang))
        
        if db.get_setting('notifications_enabled', '1') == '1':
            log_to_admin_channel(sender_id, receiver_id, message_type, message_text, file_id)
        
        db.add_admin_log("anonymous_message", sender_id, receiver_id, 
                        f"{message_type}: {message_text[:50] if message_text else 'no text'}")
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.send_message(sender_id, "❌ Ошибка отправки")

def log_to_admin_channel(sender_id, receiver_id, message_type, message_text, file_id):
    if not CHANNEL:
        return
    
    try:
        sender = db.get_user(sender_id)
        receiver = db.get_user(receiver_id)
        
        log_msg = f"""📨 Новое анонимное сообщение

👤 От: {sender_id} ({sender['first_name'] if sender else '?'})
🎯 Кому: {receiver_id} ({receiver['first_name'] if receiver else '?'})
📝 Тип: {message_type}"""
        
        if message_text:
            log_msg += f"\n💬 Текст: {message_text[:100]}"
        
        if file_id and message_type in ['photo', 'video']:
            if message_type == 'photo':
                bot.send_photo(CHANNEL, file_id, caption=log_msg)
            elif message_type == 'video':
                bot.send_video(CHANNEL, file_id, caption=log_msg)
        else:
            bot.send_message(CHANNEL, log_msg)
            
    except Exception as e:
        logger.error(f"Channel error: {e}")

def send_direct_admin_message(message, target_user_id, lang):
    try:
        file_id = None
        message_type = message.content_type
        
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        elif message_type == 'sticker':
            file_id = message.sticker.file_id
        
        message_text = message.text or message.caption or ""
        user_message = f"""📢 Важное уведомление

{message_text}

<i>С уважением, команда бота 🤖</i>"""
        
        try:
            if message_type == 'text':
                bot.send_message(target_user_id, user_message)
            elif message_type == 'photo':
                bot.send_photo(target_user_id, file_id, caption=user_message)
            elif message_type == 'video':
                bot.send_video(target_user_id, file_id, caption=user_message)
            elif message_type == 'document':
                bot.send_document(target_user_id, file_id, caption=user_message)
            elif message_type == 'sticker':
                bot.send_message(target_user_id, user_message)
                bot.send_sticker(target_user_id, file_id)
        except ApiException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ Пользователь {target_user_id} заблокировал бота.")
                return
            else:
                raise
        
        bot.send_message(ADMIN_ID, t(lang, 'message_sent_admin', user_id=target_user_id, message_type=message_type),
                        reply_markup=admin_keyboard(lang))
        
        db.add_admin_log("direct_message", ADMIN_ID, target_user_id, 
                        f"{message_type}: {message_text[:50] if message_text else 'no text'}")
        
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка отправки")

def handle_support_request(message, lang):
    user_id = message.from_user.id
    bot.send_message(user_id, t(lang, 'support'), reply_markup=cancel_keyboard(lang))
    admin_modes[user_id] = 'support'

def create_support_ticket(message, lang):
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    if not text and message_type == 'text':
        bot.send_message(user_id, "❌ Введите текст")
        return
    
    try:
        file_id = None
        file_unique_id = None
        
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
            file_unique_id = message.photo[-1].file_unique_id
        elif message_type == 'video':
            file_id = message.video.file_id
            file_unique_id = message.video.file_unique_id
        elif message_type == 'document':
            file_id = message.document.file_id
            file_unique_id = message.document.file_unique_id
        
        ticket_id = db.create_support_ticket(user_id, text, file_id, file_unique_id, message_type)
        
        bot.send_message(user_id, t(lang, 'support_sent', ticket_id=ticket_id),
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        
        notify_admin_about_ticket(ticket_id, user_id, message_type, text, file_id)
        db.add_admin_log("support_ticket", user_id, None, f"Тикет #{ticket_id}")
        
    except Exception as e:
        logger.error(f"Ticket error: {e}")
        bot.send_message(user_id, "❌ Ошибка создания тикета")

def notify_admin_about_ticket(ticket_id, user_id, message_type, text, file_id):
    user = db.get_user(user_id)
    
    notification = f"""🆘 Новый тикет #{ticket_id}

👤 Пользователь: {user_id}
📝 Имя: {user['first_name'] if user else '?'}
📱 Юзернейм: {f'@{user['username']}' if user and user['username'] else 'нет'}
📅 Время: {format_time(int(time.time()))}
📝 Тип: {message_type}"""
    
    if text:
        notification += f"\n💬 Сообщение: {text[:200]}"
    
    try:
        if file_id and message_type in ['photo', 'video']:
            if message_type == 'photo':
                msg = bot.send_photo(ADMIN_ID, file_id, caption=notification, 
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'ru'))
            elif message_type == 'video':
                msg = bot.send_video(ADMIN_ID, file_id, caption=notification,
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'ru'))
        else:
            msg = bot.send_message(ADMIN_ID, notification,
                                 reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'ru'))
        
        if CHANNEL and CHANNEL != str(ADMIN_ID):
            try:
                if file_id and message_type in ['photo', 'video']:
                    if message_type == 'photo':
                        bot.send_photo(CHANNEL, file_id, caption=notification)
                    elif message_type == 'video':
                        bot.send_video(CHANNEL, file_id, caption=notification)
                else:
                    bot.send_message(CHANNEL, notification)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Notify error: {e}")

def reply_to_support_ticket(message, ticket_id, lang):
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, message FROM support_tickets WHERE id = ?', (ticket_id,))
            row = c.fetchone()
            
            if not row:
                bot.send_message(ADMIN_ID, "❌ Тикет не найден.")
                return
            
            user_id, user_message = row
        
        message_type = message.content_type
        reply_text = message.text or message.caption or ""
        
        if not reply_text and message_type == 'text':
            bot.send_message(ADMIN_ID, "❌ Введите текст")
            return
        
        file_id = None
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        
        db.update_support_ticket(ticket_id, ADMIN_ID, reply_text, 'answered')
        
        user_reply = f"""🆘 Ответ от поддержки

Ваше сообщение:
{user_message[:500]}

Наш ответ:
{reply_text}"""
        
        try:
            if message_type == 'text':
                bot.send_message(user_id, user_reply)
            elif message_type == 'photo':
                bot.send_photo(user_id, file_id, caption=user_reply)
            elif message_type == 'video':
                bot.send_video(user_id, file_id, caption=user_reply)
            elif message_type == 'document':
                bot.send_document(user_id, file_id, caption=user_reply)
        except ApiException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ Пользователь {user_id} заблокировал бота.")
            else:
                raise
        
        bot.send_message(ADMIN_ID, f"✅ Ответ на тикет #{ticket_id} отправлен",
                        reply_markup=admin_keyboard(lang))
        
        db.add_admin_log("support_reply", ADMIN_ID, user_id, f"Тикет #{ticket_id}")
        
    except Exception as e:
        logger.error(f"Reply error: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка отправки ответа")

def generate_qr_code(user_id, lang):
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.send_photo(user_id, photo=bio, caption=t(lang, 'qr_code', link=link),
                      reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
    except Exception as e:
        logger.error(f"QR error: {e}")
        bot.send_message(user_id, "❌ Ошибка генерации QR-кода")

def show_help(user_id, lang):
    bot.send_message(user_id, t(lang, 'help'), reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id, text, lang):
    
    if text == t(lang, 'btn_admin_stats'):
        show_admin_stats(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_broadcast'):
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(admin_id, t(lang, 'broadcast_start'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_find'):
        admin_modes[admin_id] = 'find_user'
        bot.send_message(admin_id, t(lang, 'find_user'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_block'):
        admin_modes[admin_id] = 'block_user'
        bot.send_message(admin_id, t(lang, 'block_instruction'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_logs'):
        show_message_logs(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_tickets'):
        show_support_tickets(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_settings'):
        show_admin_settings(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_backup'):
        create_backup(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_export'):
        show_export_options(admin_id, lang)
    
    elif text == t(lang, 'btn_back'):
        bot.send_message(admin_id, t(lang, 'main_menu'), reply_markup=main_keyboard(True, lang))
    
    elif admin_id in admin_modes:
        mode = admin_modes[admin_id]
        
        if mode == 'broadcast':
            start_broadcast(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'find_user':
            find_user_info(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'block_user':
            handle_block_user(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'export_users':
            export_users_data(admin_id)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'export_messages':
            export_messages_data(admin_id)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'export_stats':
            export_stats_data(admin_id)
            if admin_id in admin_modes:
                del admin_modes[admin_id]

def show_admin_stats(admin_id, lang):
    stats = db.get_admin_stats()
    
    bot.send_message(admin_id, t(lang, 'admin_stats',
                               total_users=stats['total_users'],
                               today_active=stats['today_active'],
                               total_messages=stats['total_messages'],
                               messages_24h=stats['messages_24h'],
                               new_users_24h=stats['new_users_24h'],
                               blocked_users=stats['blocked_users'],
                               open_tickets=stats['open_tickets'],
                               avg_hourly=stats['avg_hourly'],
                               users_week=stats['users_week'],
                               messages_week=stats['messages_week'],
                               active_week=stats['active_week'],
                               retention_30d=stats['retention_30d'],
                               conversion_rate=stats['conversion_rate'],
                               users_by_day=stats['users_by_day'],
                               messages_by_day=stats['messages_by_day'],
                               top_users=stats['top_users']),
                    reply_markup=admin_keyboard(lang))

def start_broadcast(admin_id, message, lang):
    try:
        if isinstance(message, str):
            text = message
        else:
            text = message.text or message.caption or ""
            
        if not text:
            bot.send_message(admin_id, "❌ Введите текст рассылки")
            return
        
        users = db.get_all_users_list()
        total = len(users)
        sent = 0
        failed = 0
        blocked = 0
        
        progress_msg = bot.send_message(admin_id, t(lang, 'broadcast_progress', total=total))
        
        for user_id in users:
            try:
                if db.is_user_blocked(user_id):
                    blocked += 1
                    continue
                
                bot.send_message(user_id, text, parse_mode="HTML")
                sent += 1
                
                if sent % 20 == 0:
                    try:
                        bot.edit_message_text(
                            chat_id=admin_id,
                            message_id=progress_msg.message_id,
                            text=f"⏳ Отправлено: {sent}/{total}"
                        )
                    except:
                        pass
                
                time.sleep(0.05)
                
            except ApiException as e:
                if e.error_code == 403:
                    failed += 1
                else:
                    logger.error(f"Broadcast error: {e}")
                    failed += 1
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
                failed += 1
        
        bot.edit_message_text(
            chat_id=admin_id,
            message_id=progress_msg.message_id,
            text=t(lang, 'broadcast_result', total=total, sent=sent, failed=failed, blocked=blocked)
        )
        
        db.add_admin_log("broadcast", admin_id, None, f"Отправлено: {sent}/{total}")
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

def find_user_info(admin_id, query, lang):
    try:
        user = None
        
        if query.isdigit():
            user_id = int(query)
            user = db.get_user(user_id)
        else:
            username = query.lstrip('@')
            user = db.get_user_by_username(username)
        
        if not user:
            bot.send_message(admin_id, t(lang, 'user_not_found'), reply_markup=admin_keyboard(lang))
            return
        
        stats = db.get_user_messages_stats(user['user_id'])
        is_blocked = db.is_user_blocked(user['user_id'])
        
        username = f"@{user['username']}" if user['username'] else "❌ отсутствует"
        receive_status = "✅ Включён" if user['receive_messages'] else "❌ Выключен"
        block_status = "🔴 ЗАБЛОКИРОВАН" if is_blocked else "🟢 АКТИВЕН"
        
        user_info = t(lang, 'user_info',
                     user_id=user['user_id'],
                     first_name=user['first_name'],
                     username=username,
                     registered=format_time(user['created_at'], lang),
                     last_active=format_time(user['last_active'], lang),
                     received=stats['messages_received'],
                     sent=stats['messages_sent'],
                     clicks=user['link_clicks'],
                     receive_status=receive_status,
                     block_status=block_status)
        
        bot.send_message(admin_id, user_info, 
                        reply_markup=get_admin_user_keyboard(user['user_id'], is_blocked, lang))
        
    except Exception as e:
        logger.error(f"Find user error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard(lang))

def handle_block_user(admin_id, query, lang):
    try:
        user = None
        
        if query.isdigit():
            user_id = int(query)
            user = db.get_user(user_id)
        else:
            username = query.lstrip('@')
            user = db.get_user_by_username(username)
        
        if not user:
            bot.send_message(admin_id, t(lang, 'user_not_found'), reply_markup=admin_keyboard(lang))
            return
        
        is_blocked = db.is_user_blocked(user['user_id'])
        
        if is_blocked:
            if db.unblock_user(user['user_id']):
                db.add_admin_log("unblock", admin_id, user['user_id'], "Панель блокировки")
                bot.send_message(admin_id, t(lang, 'unblock_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'user_not_blocked_msg'),
                               reply_markup=admin_keyboard(lang))
        else:
            if db.block_user(user['user_id'], admin_id, "Панель блокировки"):
                db.add_admin_log("block", admin_id, user['user_id'], "Панель блокировки")
                bot.send_message(admin_id, t(lang, 'block_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'block_already'),
                               reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Block user error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard(lang))

def show_message_logs(admin_id, lang):
    show_text = admin_log_settings.get(admin_id, {}).get('show_text', True)
    messages = db.get_recent_messages(limit=10, include_text=show_text)
    
    if not messages:
        bot.send_message(admin_id, t(lang, 'no_logs'), reply_markup=get_admin_log_keyboard(show_text, lang))
        return
    
    logs_text = f"{t(lang, 'logs')}:\n\n"
    
    for i, msg in enumerate(messages, 1):
        sender_name = msg.get('sender_name', '?')
        receiver_name = msg.get('receiver_name', '?')
        sender_username = f" (@{msg['sender_username']})" if msg.get('sender_username') else ""
        receiver_username = f" (@{msg['receiver_username']})" if msg.get('receiver_username') else ""
        
        logs_text += f"{i}. {format_time(msg['timestamp'], lang)}\n"
        logs_text += f"   👤 От: {msg['sender_id']} - {sender_name}{sender_username}\n"
        logs_text += f"   🎯 Кому: {msg['receiver_id']} - {receiver_name}{receiver_username}\n"
        logs_text += f"   📝 Тип: {msg['message_type']}\n"
        
        if msg['text']:
            logs_text += f"   💬 Текст: {msg['text']}\n"
        
        logs_text += "\n"
    
    bot.send_message(admin_id, logs_text, reply_markup=get_admin_log_keyboard(show_text, lang))

def show_support_tickets(admin_id, lang):
    tickets = db.get_open_support_tickets()
    
    if not tickets:
        bot.send_message(admin_id, t(lang, 'no_tickets'), reply_markup=admin_keyboard(lang))
        return
    
    tickets_text = f"{t(lang, 'tickets')} ({len(tickets)}):\n\n"
    
    for i, ticket in enumerate(tickets, 1):
        tickets_text += f"{i}. Тикет #{ticket['id']}\n"
        tickets_text += f"   👤 Пользователь: {ticket['user_id']} - {ticket['first_name']}\n"
        tickets_text += f"   📱 Юзернейм: {f'@{ticket['username']}' if ticket['username'] else 'нет'}\n"
        tickets_text += f"   📅 Создан: {format_time(ticket['created_at'], lang)}\n"
        
        if ticket['message']:
            preview = ticket['message'][:100] + "..." if len(ticket['message']) > 100 else ticket['message']
            tickets_text += f"   💬 Сообщение: {preview}\n"
        
        tickets_text += f"   📝 Тип: {ticket['message_type']}\n\n"
    
    bot.send_message(admin_id, tickets_text, reply_markup=admin_keyboard(lang))

def show_admin_settings(admin_id, lang):
    notifications = db.get_setting('notifications_enabled', '1')
    notifications_status = "✅ Включены" if notifications == '1' else "❌ Выключены"
    channel_status = "✅ Настроен" if CHANNEL else "❌ Не настроен"
    
    settings_text = t(lang, 'admin_settings',
                     notifications=notifications_status,
                     channel_status=channel_status,
                     antispam=ANTISPAM_INTERVAL)
    
    bot.send_message(admin_id, settings_text, reply_markup=admin_keyboard(lang))

def create_backup(admin_id, lang):
    try:
        # Создаем резервную копию базы данных
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        with open(DB_PATH, 'rb') as f:
            db_content = f.read()
        
        # Отправляем файл админу
        bio = BytesIO(db_content)
        bio.name = backup_filename
        
        bot.send_document(admin_id, bio, caption=f"💾 Резервная копия базы данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        db.add_admin_log("backup", admin_id, None, "Создана резервная копия")
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка создания бэкапа: {e}")

def show_export_options(admin_id, lang):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'export_users')),
        types.KeyboardButton(t(lang, 'export_messages')),
        types.KeyboardButton(t(lang, 'export_stats')),
        types.KeyboardButton(t(lang, 'btn_cancel'))
    ]
    keyboard.add(*buttons)
    
    bot.send_message(admin_id, t(lang, 'export_instruction'), reply_markup=keyboard)
    admin_modes[admin_id] = 'export_options'

def export_users_data(admin_id):
    try:
        bot.send_message(admin_id, t('ru', 'export_processing'))
        
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users ORDER BY user_id')
            users = c.fetchall()
        
        # Создаем CSV файл
        csv_content = "ID;Username;First Name;Language;Created At;Last Active;Messages Received;Messages Sent;Link Clicks;Receive Messages\n"
        
        for user in users:
            csv_content += f"{user['user_id']};{user['username'] or ''};{user['first_name'] or ''};{user['language']};"
            csv_content += f"{format_time(user['created_at'])};{format_time(user['last_active'])};"
            csv_content += f"{user['messages_received']};{user['messages_sent']};{user['link_clicks']};{user['receive_messages']}\n"
        
        # Отправляем файл
        bio = BytesIO(csv_content.encode('utf-8'))
        bio.name = f"users_export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        bot.send_document(admin_id, bio, caption="👥 Экспорт пользователей")
        db.add_admin_log("export", admin_id, None, "Экспорт пользователей")
        
    except Exception as e:
        logger.error(f"Export users error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка экспорта: {e}")

def export_messages_data(admin_id):
    try:
        bot.send_message(admin_id, t('ru', 'export_processing'))
        
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM messages ORDER BY timestamp DESC LIMIT 1000')
            messages = c.fetchall()
        
        # Создаем CSV файл
        csv_content = "ID;Sender ID;Receiver ID;Type;Text;Timestamp\n"
        
        for msg in messages:
            text = (msg['text'] or '').replace(';', ',').replace('\n', ' ').replace('\r', '')
            csv_content += f"{msg['id']};{msg['sender_id']};{msg['receiver_id']};{msg['message_type']};{text};{format_time(msg['timestamp'])}\n"
        
        # Отправляем файл
        bio = BytesIO(csv_content.encode('utf-8'))
        bio.name = f"messages_export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        bot.send_document(admin_id, bio, caption="📨 Экспорт сообщений (последние 1000)")
        db.add_admin_log("export", admin_id, None, "Экспорт сообщений")
        
    except Exception as e:
        logger.error(f"Export messages error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка экспорта: {e}")

def export_stats_data(admin_id):
    try:
        bot.send_message(admin_id, t('ru', 'export_processing'))
        
        stats = db.get_admin_stats()
        
        # Создаем текстовый файл со статистикой
        stats_text = f"""📊 Статистика бота Anony SMS
📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Основные метрики:
├ Всего пользователей: {stats['total_users']}
├ Активных сегодня: {stats['today_active']}
├ Всего сообщений: {stats['total_messages']}
├ Сообщений за 24ч: {stats['messages_24h']}
├ Новых за 24ч: {stats['new_users_24h']}
├ Заблокированных: {stats['blocked_users']}
├ Открытых тикетов: {stats['open_tickets']}
└ Сред. активность в час: {stats['avg_hourly']}

Детальная статистика:
├ Пользователей за неделю: {stats['users_week']}
├ Сообщений за неделю: {stats['messages_week']}
├ Активных за неделю: {stats['active_week']}
├ Удерживание (30 дней): {stats['retention_30d']}%
└ Конверсия в сообщения: {stats['conversion_rate']}%
"""
        
        # Отправляем файл
        bio = BytesIO(stats_text.encode('utf-8'))
        bio.name = f"stats_export_{datetime.now().strftime('%Y%m%d')}.txt"
        
        bot.send_document(admin_id, bio, caption="📊 Экспорт статистики")
        db.add_admin_log("export", admin_id, None, "Экспорт статистики")
        
    except Exception as e:
        logger.error(f"Export stats error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка экспорта: {e}")

# ====== FLASK РОУТЫ ======
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data(as_text=True)
            update = types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        return 'Invalid content type', 400
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'ERROR', 500

@app.route('/health', methods=['GET'])
def health_check():
    try:
        db.get_admin_stats()
        return jsonify({
            'status': 'ok', 
            'time': datetime.now().isoformat(),
            'bot': 'Anony SMS',
            'version': '6.0',
            'users': db.get_admin_stats()['total_users'],
            'messages': db.get_admin_stats()['total_messages']
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'status': 'active', 'timestamp': time.time()})

@app.route('/admin', methods=['GET'])
def admin_panel():
    if not CHANNEL:
        return "Admin panel not configured"
    
    stats = db.get_admin_stats()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Anony SMS Admin</title>
        <style>
            body {{ font-family: Arial; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
            .stat-card {{ background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            .stat-value {{ font-size: 24px; font-weight: bold; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header"><h1>🤖 Anony SMS Admin</h1></div>
            <div class="stats">
                <div class="stat-card"><div>Пользователей</div><div class="stat-value">{stats['total_users']}</div></div>
                <div class="stat-card"><div>Сообщений</div><div class="stat-value">{stats['total_messages']}</div></div>
                <div class="stat-card"><div>Тикетов</div><div class="stat-value">{stats['open_tickets']}</div></div>
                <div class="stat-card"><div>Заблокированных</div><div class="stat-value">{stats['blocked_users']}</div></div>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ====== МОНИТОРИНГ ======
def monitor_bot():
    while True:
        try:
            user_count = db.get_all_users_count()
            
            hour_ago = int(time.time()) - 3600
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', (hour_ago,))
                messages_last_hour = c.fetchone()[0]
            
            if messages_last_hour < 5 and user_count > 100:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Низкая активность\nЗа час: {messages_last_hour} сообщений\nПользователей: {user_count}")
                except:
                    pass
            
            tickets = db.get_open_support_tickets()
            if len(tickets) > 5:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Много тикетов: {len(tickets)}")
                except:
                    pass
            
            time.sleep(3600)
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(300)

def keep_alive():
    while True:
        try:
            requests.get(f"{WEBHOOK_HOST}/ping", timeout=10)
            logger.info("✅ Ping")
        except Exception as e:
            logger.error(f"❌ Ping error: {e}")
        time.sleep(300)

# ====== ЗАПУСК ======
if __name__ == '__main__':
    logger.info("=== Anony SMS Bot v6.0 запущен ===")
    logger.info(f"Admin ID: {ADMIN_ID}")
    
    try:
        bot_username = bot.get_me().username
        logger.info(f"Bot username: @{bot_username}")
    except:
        logger.warning("⚠️ Не удалось получить имя бота")
    
    if WEBHOOK_HOST:
        try:
            ping_thread = threading.Thread(target=keep_alive, daemon=True)
            ping_thread.start()
            logger.info("✅ Пингер запущен")
            
            monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
            monitor_thread.start()
            logger.info("✅ Мониторинг запущен")
        except:
            pass
    
    try:
        if WEBHOOK_HOST:
            logger.info(f"Настройка вебхука для {WEBHOOK_HOST}")
            
            try:
                bot.remove_webhook()
                time.sleep(1)
            except:
                pass
            
            bot.set_webhook(
                url=f"{WEBHOOK_HOST}/webhook",
                max_connections=100,
                timeout=60
            )
            logger.info("✅ Вебхук настроен")
            
            app.run(
                host='0.0.0.0',
                port=PORT,
                debug=False,
                threaded=True
            )
        else:
            logger.info("Локальный запуск (поллинг)")
            bot.remove_webhook()
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=20,
                long_polling_timeout=20
            )
            
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
