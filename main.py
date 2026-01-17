#!/usr/bin/env python3
"""
Anony SMS Bot - Ultimate Version v5.0
Fully functional with dynamic menu system
"""

import os
import sys
import time
import json
import logging
import qrcode
import threading
from datetime import datetime
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
└ Последняя активность: {last_active}

<b>📊 Статистика активности:</b>
├ Пик активности: <b>{peak_hour}</b>
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
        
        'btn_admin_stats': "📊 Статистика",
        'btn_admin_broadcast': "📢 Рассылка",
        'btn_admin_manage_users': "👥 Управление",
        'btn_admin_find': "🔍 Найти",
        'btn_admin_logs': "📋 Логи",
        'btn_admin_tickets': "🆘 Тикеты",
        'btn_admin_settings': "⚙️ Настройки",
        'btn_admin_custom_menus': "➕ Меню",
        
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
            
            # Кастомные меню
            c.execute('''
                CREATE TABLE IF NOT EXISTS custom_menus (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    description TEXT,
                    parent_id INTEGER DEFAULT 0,
                    button_text TEXT,
                    message_text TEXT,
                    is_active INTEGER DEFAULT 1,
                    created_at INTEGER,
                    order_index INTEGER DEFAULT 0
                )
            ''')
            
            # Детальная статистика для пользователя
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_detailed_stats (
                    user_id INTEGER PRIMARY KEY,
                    messages_by_hour TEXT DEFAULT '{}',
                    messages_by_day TEXT DEFAULT '{}',
                    message_types TEXT DEFAULT '{}',
                    avg_response_time REAL DEFAULT 0,
                    most_active_day TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            ''')
            
            # Статистика ссылок
            c.execute('''
                CREATE TABLE IF NOT EXISTS link_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    clicker_id INTEGER,
                    timestamp INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
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
            return c.lastrowid
    
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
            c.execute('''
                INSERT OR REPLACE INTO blocked_users (user_id, blocked_at, blocked_by, reason)
                VALUES (?, ?, ?, ?)
            ''', (user_id, now, admin_id, reason))
    
    def unblock_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
    
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
            
            retention_30d = round((active_30d / old_users * 100), 2) if old_users > 0 else 0
            
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
                'total_messages': total_messages,
                'blocked_users': blocked_users,
                'new_users_24h': new_users_24h,
                'messages_24h': messages_24h,
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

    # ====== МЕТОДЫ ДЛЯ СТАТИСТИКИ ======
    
    def update_detailed_stats(self, user_id, message_type, timestamp):
        """Обновление детальной статистики пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Получаем текущую статистику
            c.execute('SELECT * FROM user_detailed_stats WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            
            now = datetime.fromtimestamp(timestamp)
            hour = now.hour
            day_of_week = now.strftime('%A')
            
            if not row:
                # Создаем новую запись
                messages_by_hour = json.dumps({str(hour): 1})
                messages_by_day = json.dumps({day_of_week: 1})
                message_types = json.dumps({message_type: 1})
                
                c.execute('''
                    INSERT INTO user_detailed_stats 
                    (user_id, messages_by_hour, messages_by_day, message_types, most_active_day)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, messages_by_hour, messages_by_day, message_types, day_of_week))
            else:
                # Обновляем существующую статистику
                messages_by_hour = json.loads(row['messages_by_hour'])
                messages_by_day = json.loads(row['messages_by_day'])
                message_types = json.loads(row['message_types'])
                
                # Обновляем часы
                hour_key = str(hour)
                messages_by_hour[hour_key] = messages_by_hour.get(hour_key, 0) + 1
                
                # Обновляем дни
                messages_by_day[day_of_week] = messages_by_day.get(day_of_week, 0) + 1
                
                # Обновляем типы сообщений
                message_types[message_type] = message_types.get(message_type, 0) + 1
                
                # Определяем самый активный день
                if messages_by_day:
                    most_active_day = max(messages_by_day.items(), key=lambda x: x[1])[0]
                else:
                    most_active_day = day_of_week
                
                c.execute('''
                    UPDATE user_detailed_stats 
                    SET messages_by_hour = ?, messages_by_day = ?, message_types = ?, most_active_day = ?
                    WHERE user_id = ?
                ''', (json.dumps(messages_by_hour), json.dumps(messages_by_day), 
                      json.dumps(message_types), most_active_day, user_id))
    
    def track_link_click(self, user_id, clicker_id):
        """Отслеживание кликов по ссылке"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO link_stats (user_id, clicker_id, timestamp)
                VALUES (?, ?, ?)
            ''', (user_id, clicker_id, int(time.time())))
    
    def get_user_detailed_stats(self, user_id):
        """Получение детальной статистики пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Основная статистика
            c.execute('SELECT * FROM user_detailed_stats WHERE user_id = ?', (user_id,))
            stats_row = c.fetchone()
            
            if not stats_row:
                return None
            
            stats = dict(stats_row)
            
            # Парсим JSON данные
            stats['messages_by_hour'] = json.loads(stats.get('messages_by_hour', '{}'))
            stats['messages_by_day'] = json.loads(stats.get('messages_by_day', '{}'))
            stats['message_types'] = json.loads(stats.get('message_types', '{}'))
            
            # Статистика кликов по ссылке
            c.execute('''
                SELECT COUNT(*) as total_clicks,
                       COUNT(DISTINCT clicker_id) as unique_clickers
                FROM link_stats 
                WHERE user_id = ?
            ''', (user_id,))
            link_stats_row = c.fetchone()
            
            if link_stats_row:
                stats['total_clicks'] = link_stats_row['total_clicks']
                stats['unique_clickers'] = link_stats_row['unique_clickers']
            else:
                stats['total_clicks'] = 0
                stats['unique_clickers'] = 0
            
            # Получаем среднее время ответа из сообщений
            c.execute('''
                SELECT timestamp, sender_id, receiver_id
                FROM messages 
                WHERE sender_id = ? OR receiver_id = ?
                ORDER BY timestamp
            ''', (user_id, user_id))
            all_messages = c.fetchall()
            
            response_times = []
            for i in range(len(all_messages)-1):
                if all_messages[i]['receiver_id'] == user_id and all_messages[i+1]['sender_id'] == user_id:
                    time_diff = all_messages[i+1]['timestamp'] - all_messages[i]['timestamp']
                    if 0 < time_diff < 3600:  # Исключаем отрицательные и большие перерывы
                        response_times.append(time_diff)
            
            if response_times:
                stats['avg_response_time'] = sum(response_times) / len(response_times)
            else:
                stats['avg_response_time'] = 0
            
            return stats

    # ====== МЕТОДЫ ДЛЯ КАСТОМНЫХ МЕНЮ ======
    
    def create_custom_menu(self, name, description, parent_id, button_text, message_text):
        """Создание кастомного меню"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            
            # Получаем максимальный order_index для родителя
            c.execute('SELECT MAX(order_index) FROM custom_menus WHERE parent_id = ?', (parent_id,))
            max_order = c.fetchone()[0] or 0
            
            c.execute('''
                INSERT INTO custom_menus 
                (name, description, parent_id, button_text, message_text, created_at, order_index)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (name, description, parent_id, button_text, message_text, now, max_order + 1))
            
            return c.lastrowid
    
    def get_custom_menus(self, parent_id=0):
        """Получение кастомных меню"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT * FROM custom_menus 
                WHERE parent_id = ? AND is_active = 1
                ORDER BY order_index
            ''', (parent_id,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    def get_custom_menu_by_id(self, menu_id):
        """Получение кастомного меню по ID"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM custom_menus WHERE id = ?', (menu_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    def delete_custom_menu(self, menu_id):
        """Удаление кастомного меню"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM custom_menus WHERE id = ?', (menu_id,))
            return c.rowcount > 0

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

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin=False, lang='ru'):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        types.KeyboardButton(t(lang, 'btn_my_link')),
        types.KeyboardButton(t(lang, 'btn_profile')),
        types.KeyboardButton(t(lang, 'btn_settings')),
        types.KeyboardButton(t(lang, 'btn_qr')),
        types.KeyboardButton(t(lang, 'btn_help')),
        types.KeyboardButton(t(lang, 'btn_support'))
    ]
    
    # Добавляем кастомные меню
    custom_menus = db.get_custom_menus(parent_id=0)
    for menu in custom_menus:
        buttons.append(types.KeyboardButton(menu['button_text']))
    
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
        types.KeyboardButton(t(lang, 'btn_admin_manage_users')),
        types.KeyboardButton(t(lang, 'btn_admin_find')),
        types.KeyboardButton(t(lang, 'btn_admin_logs')),
        types.KeyboardButton(t(lang, 'btn_admin_tickets')),
        types.KeyboardButton(t(lang, 'btn_admin_settings')),
        types.KeyboardButton(t(lang, 'btn_admin_custom_menus')),
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

def custom_menu_keyboard(menu_id, lang='ru'):
    """Клавиатура для кастомного меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    # Получаем подменю
    submenus = db.get_custom_menus(parent_id=menu_id)
    
    buttons = []
    for menu in submenus:
        buttons.append(types.KeyboardButton(menu['button_text']))
    
    buttons.append(types.KeyboardButton(t(lang, 'btn_back')))
    
    keyboard.add(*buttons)
    return keyboard

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start', 'lang', 'menu'])
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
    db.track_link_click(target_id, clicker_id)  # Для статистики
    
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
            db.block_user(target_id, ADMIN_ID, "Админ-панель")
            db.add_admin_log("block", user_id, target_id, "Админ-панель")
            bot.answer_callback_query(call.id, t(lang, 'block_user', user_id=target_id))
            
            try:
                user_info = t(lang, 'user_blocked')
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + f"\n\n{user_info}",
                    reply_markup=get_admin_user_keyboard(target_id, True, lang)
                )
            except:
                pass
        
        elif data.startswith("admin_unblock_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            db.unblock_user(target_id)
            db.add_admin_log("unblock", user_id, target_id, "Админ-панель")
            bot.answer_callback_query(call.id, t(lang, 'unblock_user', user_id=target_id))
            
            try:
                user_info = "✅ Разблокирован"
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + f"\n\n{user_info}",
                    reply_markup=get_admin_user_keyboard(target_id, False, lang)
                )
            except:
                pass
        
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
    
    # Обработка кастомных меню
    custom_menus = db.get_custom_menus(parent_id=0)
    for menu in custom_menus:
        if text == menu['button_text']:
            handle_custom_menu(user_id, menu, lang)
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

def handle_custom_menu(user_id, menu, lang):
    """Обработка кастомного меню"""
    # Проверяем есть ли подменю
    submenus = db.get_custom_menus(parent_id=menu['id'])
    
    if submenus:
        # Если есть подменю, показываем их
        bot.send_message(user_id, menu['description'] or "Выберите пункт меню:",
                        reply_markup=custom_menu_keyboard(menu['id'], lang))
    else:
        # Если нет подменю, показываем сообщение
        if menu['message_text']:
            bot.send_message(user_id, menu['message_text'], 
                           reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        else:
            bot.send_message(user_id, "Это кастомное меню. Сообщение не настроено.",
                           reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

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

def show_user_stats(user_id, lang):
    """Показать статистику пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌", reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    detailed_stats = db.get_user_detailed_stats(user_id)
    
    receive_status = "✅ Включён" if user['receive_messages'] else "❌ Выключен"
    username = f"@{user['username']}" if user['username'] else "❌ отсутствует"
    
    # Анализ времени ответа
    avg_response = detailed_stats.get('avg_response_time', 0) if detailed_stats else 0
    response_time = f"{int(avg_response//60)} мин {int(avg_response%60)} сек" if avg_response > 0 else "N/A"
    
    # Анализ пиковой активности
    if detailed_stats and detailed_stats.get('messages_by_hour'):
        peak_hour = max(detailed_stats['messages_by_hour'].items(), key=lambda x: x[1])[0] if detailed_stats['messages_by_hour'] else "N/A"
    else:
        peak_hour = "N/A"
    
    # Анализ дней
    if detailed_stats:
        most_active_day = detailed_stats.get('most_active_day', 'N/A')
        day_names = {
            'Monday': 'понедельник',
            'Tuesday': 'вторник',
            'Wednesday': 'среда',
            'Thursday': 'четверг',
            'Friday': 'пятница',
            'Saturday': 'суббота',
            'Sunday': 'воскресенье'
        }
        active_day = day_names.get(most_active_day, most_active_day)
    else:
        active_day = "N/A"
    
    # Любимый тип сообщений
    if detailed_stats and detailed_stats.get('message_types'):
        fav_type = max(detailed_stats['message_types'].items(), key=lambda x: x[1])[0] if detailed_stats['message_types'] else "N/A"
        type_names = {
            'text': '📝 Текст',
            'photo': '📸 Фото',
            'video': '🎬 Видео',
            'voice': '🎤 Голос'
        }
        fav_type_display = type_names.get(fav_type, fav_type)
    else:
        fav_type_display = "N/A"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=user['messages_received'],
                    sent=user['messages_sent'],
                    clicks=user['link_clicks'],
                    response_time=response_time,
                    receive_status=receive_status,
                    last_active=format_time(user['last_active'], lang),
                    peak_hour=peak_hour,
                    active_day=active_day,
                    fav_type=fav_type_display,
                    link=generate_link(user_id))
    
    bot.send_message(user_id, profile_text, 
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
        
        # Обновляем детальную статистику
        db.update_detailed_stats(sender_id, message_type, int(time.time()))
        
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

def show_profile(user_id, lang):
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌", reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    detailed_stats = db.get_user_detailed_stats(user_id)
    
    receive_status = "✅ Включён" if user['receive_messages'] else "❌ Выключен"
    username = f"@{user['username']}" if user['username'] else "❌ отсутствует"
    
    # Анализ времени ответа
    avg_response = detailed_stats.get('avg_response_time', 0) if detailed_stats else 0
    response_time = f"{int(avg_response//60)} мин {int(avg_response%60)} сек" if avg_response > 0 else "N/A"
    
    # Анализ пиковой активности
    if detailed_stats and detailed_stats.get('messages_by_hour'):
        peak_hour = max(detailed_stats['messages_by_hour'].items(), key=lambda x: x[1])[0] if detailed_stats['messages_by_hour'] else "N/A"
    else:
        peak_hour = "N/A"
    
    # Анализ дней
    if detailed_stats:
        most_active_day = detailed_stats.get('most_active_day', 'N/A')
        day_names = {
            'Monday': 'понедельник',
            'Tuesday': 'вторник',
            'Wednesday': 'среда',
            'Thursday': 'четверг',
            'Friday': 'пятница',
            'Saturday': 'суббота',
            'Sunday': 'воскресенье'
        }
        active_day = day_names.get(most_active_day, most_active_day)
    else:
        active_day = "N/A"
    
    # Любимый тип сообщений
    if detailed_stats and detailed_stats.get('message_types'):
        fav_type = max(detailed_stats['message_types'].items(), key=lambda x: x[1])[0] if detailed_stats['message_types'] else "N/A"
        type_names = {
            'text': '📝 Текст',
            'photo': '📸 Фото',
            'video': '🎬 Видео',
            'voice': '🎤 Голос'
        }
        fav_type_display = type_names.get(fav_type, fav_type)
    else:
        fav_type_display = "N/A"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=user['messages_received'],
                    sent=user['messages_sent'],
                    clicks=user['link_clicks'],
                    response_time=response_time,
                    receive_status=receive_status,
                    last_active=format_time(user['last_active'], lang),
                    peak_hour=peak_hour,
                    active_day=active_day,
                    fav_type=fav_type_display,
                    link=generate_link(user_id))
    
    bot.send_message(user_id, profile_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id, text, lang):
    
    if text == t(lang, 'btn_admin_stats'):
        show_admin_stats(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_broadcast'):
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(admin_id, t(lang, 'broadcast_start'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_manage_users'):
        bot.send_message(admin_id, t(lang, 'users_management'), 
                        reply_markup=admin_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_find'):
        admin_modes[admin_id] = 'find_user'
        bot.send_message(admin_id, t(lang, 'find_user'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_logs'):
        show_message_logs(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_tickets'):
        show_support_tickets(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_settings'):
        show_admin_settings(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_custom_menus'):
        handle_custom_menus_management(admin_id, lang)
    
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
        
        elif mode == 'create_menu':
            create_custom_menu_handler(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]

def show_admin_stats(admin_id, lang):
    stats = db.get_admin_stats()
    today_active = db.get_today_active_users()
    
    bot.send_message(admin_id, t(lang, 'admin_stats',
                               total_users=stats['total_users'],
                               today_active=today_active,
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
                     received=user['messages_received'],
                     sent=user['messages_sent'],
                     clicks=user['link_clicks'],
                     receive_status=receive_status,
                     block_status=block_status)
        
        bot.send_message(admin_id, user_info, 
                        reply_markup=get_admin_user_keyboard(user['user_id'], is_blocked, lang))
        
    except Exception as e:
        logger.error(f"Find user error: {e}")
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

def handle_custom_menus_management(admin_id, lang):
    """Управление кастомными меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("➕ Создать меню"),
        types.KeyboardButton("📋 Список меню"),
        types.KeyboardButton("🗑️ Удалить меню"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    
    bot.send_message(admin_id, "🛠️ <b>Управление кастомными меню</b>\n\n"
                    "Выберите действие:", reply_markup=keyboard)
    
    admin_modes[admin_id] = 'custom_menus'

def create_custom_menu_handler(admin_id, text, lang):
    """Обработчик создания кастомного меню"""
    if admin_id not in admin_modes:
        return
    
    mode = admin_modes[admin_id]
    
    if mode == 'create_menu_name':
        admin_modes[admin_id] = 'create_menu_desc'
        admin_modes[f'{admin_id}_menu_name'] = text
        
        bot.send_message(admin_id, "📝 Введите описание меню:")
    
    elif mode == 'create_menu_desc':
        admin_modes[admin_id] = 'create_menu_parent'
        admin_modes[f'{admin_id}_menu_desc'] = text
        
        # Список существующих меню для выбора родителя
        menus = db.get_custom_menus()
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        if menus:
            for menu in menus:
                keyboard.add(types.KeyboardButton(f"📁 {menu['name']}"))
        
        keyboard.add(types.KeyboardButton("🏠 Главное меню (0)"))
        keyboard.add(types.KeyboardButton("❌ Отмена"))
        
        bot.send_message(admin_id, "📂 Выберите родительское меню (ID):\n"
                        "0 - Главное меню\n\n"
                        "Или напишите ID существующего меню:", 
                        reply_markup=keyboard)
    
    elif mode == 'create_menu_parent':
        if text == "🏠 Главное меню (0)":
            parent_id = 0
        elif text.startswith("📁 "):
            # Найдем меню по имени
            menu_name = text[3:]
            menus = db.get_custom_menus()
            parent_id = 0
            for menu in menus:
                if menu['name'] == menu_name:
                    parent_id = menu['id']
                    break
        else:
            try:
                parent_id = int(text)
            except:
                bot.send_message(admin_id, "❌ Неверный формат ID")
                return
        
        admin_modes[admin_id] = 'create_menu_button'
        admin_modes[f'{admin_id}_menu_parent'] = parent_id
        
        bot.send_message(admin_id, "🔘 Введите текст для кнопки меню:", 
                        reply_markup=cancel_keyboard(lang))
    
    elif mode == 'create_menu_button':
        admin_modes[admin_id] = 'create_menu_message'
        admin_modes[f'{admin_id}_menu_button'] = text
        
        bot.send_message(admin_id, "💬 Введите сообщение, которое будет показываться при нажатии на меню:\n"
                        "(Используйте HTML-разметку)")
    
    elif mode == 'create_menu_message':
        # Получаем все сохраненные данные
        menu_name = admin_modes.get(f'{admin_id}_menu_name')
        menu_desc = admin_modes.get(f'{admin_id}_menu_desc')
        menu_parent = admin_modes.get(f'{admin_id}_menu_parent')
        menu_button = admin_modes.get(f'{admin_id}_menu_button')
        menu_message = text
        
        # Создаем меню
        try:
            menu_id = db.create_custom_menu(menu_name, menu_desc, menu_parent, menu_button, menu_message)
            
            # Очищаем временные данные
            for key in [f'{admin_id}_menu_name', f'{admin_id}_menu_desc', 
                       f'{admin_id}_menu_parent', f'{admin_id}_menu_button']:
                if key in admin_modes:
                    del admin_modes[key]
            
            if admin_id in admin_modes:
                del admin_modes[admin_id]
            
            bot.send_message(admin_id, f"✅ Меню '{menu_name}' успешно создано!\n"
                            f"ID: {menu_id}", 
                            reply_markup=admin_keyboard(lang))
            
        except Exception as e:
            logger.error(f"Create menu error: {e}")
            bot.send_message(admin_id, f"❌ Ошибка создания меню: {e}", 
                            reply_markup=admin_keyboard(lang))

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
            'version': '5.0',
            'users': db.get_admin_stats()['total_users']
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
    logger.info("=== Anony SMS Bot v5.0 запущен ===")
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
