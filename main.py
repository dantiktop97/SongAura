#!/usr/bin/env python3
"""
Anony SMS Bot - Ultimate Professional Version v9.0
Merged from v7.0 and v8.0 with all features
"""

import os
import sys
import time
import json
import logging
import qrcode
import threading
import hashlib
import re
import random
import string
from datetime import datetime, timedelta
from io import BytesIO
from contextlib import contextmanager
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import requests
import base64
from typing import Dict, List, Optional, Any, Tuple

from flask import Flask, request, jsonify, Response
from telebot import TeleBot, types
from telebot.apihelper import ApiException, ApiTelegramException
from PIL import Image, ImageDraw, ImageFont
import html

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
CHANNEL = os.getenv("CHANNEL", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data.db")

# Конфигурация безопасности
ANTISPAM_INTERVAL = 2
MAX_REQUESTS_PER_MINUTE = 30
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_MESSAGE_LENGTH = 4000
SESSION_TIMEOUT = 300

# Капча конфиг
CAPTCHA_ENABLED = True
CAPTCHA_AFTER_ATTEMPTS = 5

# Модерация
BLACKLIST_WORDS = [
    'спам', 'реклама', 'скам', 'мошенничество', 'обман',
    'взлом', 'хак', 'пароль', 'карта', 'банк', 'кредит',
    'порно', 'порнография', 'нарко', 'drug', 'sex',
    'оскорбление', 'угроза', 'шантаж'
]

# ====== ЛОГГИРОВАНИЕ ======
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ ======
bot = TeleBot(TOKEN, parse_mode="HTML", num_threads=4)
app = Flask(__name__)

# ====== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ======
user_sessions = {}
admin_modes = {}
message_cooldown = {}
request_counts = {}
captcha_data = {}
user_attempts = {}
rate_limit_cache = {}
achievements_cache = {}
file_cache = {}
session_timestamps = {}

# ====== ПЕРЕВОДЫ (ОБЪЕДИНЕННЫЕ) ======
TRANSLATIONS = {
    'ru': {
        # Основные
        'start': """🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉

<code>{link}</code>

<b>📨 Получай анонимные сообщения:</b>
1. Поделись ссылкой выше
2. Жди сообщения от анонимов
3. Читай и отвечай анонимно

<b>✉️ Отправь анонимное сообщение:</b>
1. Перейди по чужой ссылке
2. Напиши сообщение
3. Отправь — получатель не узнает кто ты

<b>🔐 Полная анонимность гарантирована!</b>""",
        
        'start_ref': """🎯 <b>Вы перешли по ссылке пользователя!</b>

Теперь вы можете отправить этому пользователю <b>полностью анонимное сообщение</b>.

💌 <i>Напишите ваше сообщение ниже:</i>

<i>Вы можете отправить:</i>
• Текст ✍️
• Фото 📸
• Видео 🎬
• Голосовое 🎤
• Документ 📎
• Стикер 😜""",
        
        'my_link': """🔗 <b>Ваша уникальная ссылка:</b>

<code>{link}</code>

<i>Поделитесь этой ссылкой чтобы получать анонимные сообщения!</i>""",
        
        'profile': """👤 <b>Ваш профиль</b>

<b>📊 Статистика:</b>
├ Получено сообщений: <b>{received}</b>
├ Отправлено сообщений: <b>{sent}</b>
├ Переходов по ссылке: <b>{clicks}</b>
├ Регистрация: <b>{registered}</b>
└ Последняя активность: <b>{last_active}</b>

<b>⚙️ Настройки:</b>
├ Получение сообщений: {receive_status}
└ Язык: 🇷🇺 Русский""",
        
        'anonymous_message': """📨 <b>У вас новое анонимное сообщение!</b>

💌 <i>Кто-то отправил вам тайное послание...</i>

{message_content}

<i>🔒 Отправитель останется неизвестным...</i>""",
        
        'message_sent': """✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Ваше сообщение доставлено
🔒 Ваша личность скрыта
💌 Получатель не узнает кто вы</i>

<b>Хотите отправить ещё?</b>
Напишите новое сообщение""",
        
        'help': """ℹ️ <b>Помощь по Anony SMS</b>

<b>Как получать сообщения?</b>
1. Нажмите "📩 Моя ссылка"
2. Поделитесь своей ссылкой с друзьями
3. Ждите анонимные сообщения

<b>Как отправлять сообщения?</b>
1. Перейдите по чужой ссылке
2. Напишите сообщение
3. Отправьте — получатель не узнает кто вы

<b>Что можно отправлять?</b>
✅ Текст
✅ Фото
✅ Видео
✅ Голосовые
✅ Документы
✅ Стикеры""",
        
        'support': """🆘 <b>Поддержка</b>

<i>Опишите вашу проблему:</i>""",
        
        'support_sent': "✅ <b>Запрос отправлен в поддержку</b>",
        'settings': "⚙️ <b>Настройки</b>",
        'turn_on': "✅ <b>Получение сообщений включено</b>",
        'turn_off': "❌ <b>Получение сообщений отключено</b>",
        'language': "🌐 <b>Выберите язык</b>",
        'blocked': "🚫 <b>Вы заблокированы</b>",
        'user_not_found': "❌ Пользователь не найден",
        'messages_disabled': "❌ Пользователь отключил получение сообщений",
        'wait': "⏳ Подождите 2 секунды",
        'canceled': "❌ Отменено",
        'spam_wait': "⏳ Слишком быстро, подождите",
        'qr_code': "📱 <b>QR-код вашей ссылки</b>",
        
        # Админ
        'admin_panel': "👑 <b>Панель администратора</b>",
        'admin_stats': "📊 <b>Статистика бота</b>",
        'broadcast_start': "📢 <b>Создание рассылки</b>",
        'users_management': "👥 <b>Управление пользователями</b>",
        'find_user': "🔍 <b>Поиск пользователя</b>",
        'user_info': "👤 <b>Информация о пользователе</b>",
        'logs': "📋 <b>Логи</b>",
        'no_logs': "📋 <b>Логи пусты</b>",
        'tickets': "🆘 <b>Тикеты поддержки</b>",
        'no_tickets': "🆘 <b>Нет открытых тикетов</b>",
        'admin_settings': "⚙️ <b>Настройки админа</b>",
        'direct_message': "✉️ <b>Отправка сообщения</b>",
        'message_sent_admin': "✅ <b>Сообщение отправлено</b>",
        'block_user': "🚫 <b>Пользователь заблокирован</b>",
        'unblock_user': "✅ <b>Пользователь разблокирован</b>",
        
        # Кнопки
        'btn_my_link': "📩 Моя ссылка",
        'btn_profile': "👤 Профиль",
        'btn_stats': "📊 Статистика",
        'btn_settings': "⚙️ Настройки",
        'btn_qr': "📱 QR-код",
        'btn_help': "ℹ️ Помощь",
        'btn_support': "🆘 Поддержка",
        'btn_admin': "👑 Админ",
        'btn_turn_on': "✅ Включить получение",
        'btn_turn_off': "❌ Выключить получение",
        'btn_language': "🌐 Язык",
        'btn_back': "⬅️ Назад",
        'btn_cancel': "❌ Отмена",
        'btn_history': "📜 История",
        
        'btn_reply': "💌 Ответить",
        'btn_ignore': "🚫 Игнорировать",
        'btn_block': "🚫 Заблокировать",
        'btn_unblock': "✅ Разблокировать",
        'btn_message': "✉️ Написать",
        'btn_refresh': "🔄 Обновить",
        'btn_show_text': "🔍 Показать текст",
        'btn_hide_text': "👁️ Скрыть текст",
        'btn_reply_ticket': "📝 Ответить",
        'btn_close_ticket': "✅ Закрыть",
        
        # Админ кнопки
        'btn_admin_stats': "📊 Статистика",
        'btn_admin_broadcast': "📢 Рассылка",
        'btn_admin_manage_users': "👥 Пользователи",
        'btn_admin_find': "🔍 Найти",
        'btn_admin_logs': "📋 Логи",
        'btn_admin_tickets': "🆘 Тикеты",
        'btn_admin_settings': "⚙️ Настройки",
        'btn_admin_block': "🚫 Блокировка",
        'btn_admin_backup': "💾 Бэкап",
        'btn_admin_export': "📤 Экспорт",
        
        # Дополнительные из v7.0
        'reply_to_ticket': "📝 <b>Ответ на тикет</b>",
        'user_blocked_bot': "❌ Пользователь заблокировал бота",
        'text': "Текст",
        'main_menu': "🏠 Главное меню",
        
        # Экспорт
        'export_instruction': "📤 <b>Экспорт данных</b>",
        'export_users': "👥 Экспорт пользователей",
        'export_messages': "📨 Экспорт сообщений",
        'export_stats': "📊 Экспорт статистики",
        
        # Капча
        'captcha_required': "🔒 <b>Требуется проверка безопасности</b>",
        'captcha_correct': "✅ Капча пройдена!",
        'captcha_incorrect': "❌ Неверная капча",
        'captcha_failed': "❌ Превышено количество попыток",
        'captcha_timeout': "⏰ Время истекло",
        
        # Ошибки
        'file_too_large': "❌ Файл слишком большой",
        'message_too_long': "❌ Сообщение слишком длинное",
        'rate_limit_exceeded': "⏳ Слишком много запросов",
        'content_blocked': "❌ Сообщение содержит запрещённые слова",
        'session_expired': "⏰ Сессия истекла",
        'system_error': "❌ Системная ошибка",
        
        # Блокировка
        'block_instruction': "🚫 <b>Блокировка/Разблокировка</b>",
        'block_success': "✅ Пользователь заблокирован",
        'unblock_success': "✅ Пользователь разблокирован",
        'user_already_blocked': "✅ Пользователь уже заблокирован",
        'user_not_blocked_msg': "✅ Пользователь не был заблокирован",
    }
}

# ====== УТИЛИТЫ ======
def t(lang: str, key: str, **kwargs) -> str:
    """Функция перевода"""
    if lang not in TRANSLATIONS:
        lang = 'ru'
    if key not in TRANSLATIONS[lang]:
        return key
    return TRANSLATIONS[lang][key].format(**kwargs) if kwargs else TRANSLATIONS[lang][key]

def format_time(timestamp: int, lang: str = 'ru') -> str:
    """Форматирование времени"""
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return "только что"
        elif diff.seconds < 3600:
            return f"{diff.seconds // 60} мин назад"
        else:
            return f"{diff.seconds // 3600} ч назад"
    elif diff.days == 1:
        return "вчера"
    else:
        return dt.strftime("%d.%m.%Y")

def generate_link(user_id: int) -> str:
    """Генерация ссылки"""
    try:
        bot_username = bot.get_me().username
        return f"https://t.me/{bot_username}?start={user_id}"
    except:
        return f"https://t.me/{bot.get_me().username}?start={user_id}"

def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """Проверка ограничения скорости"""
    now = time.time()
    minute = int(now // 60)
    
    if user_id not in rate_limit_cache:
        rate_limit_cache[user_id] = {'minute': minute, 'count': 1}
        return True, 0
    
    if rate_limit_cache[user_id]['minute'] != minute:
        rate_limit_cache[user_id] = {'minute': minute, 'count': 1}
        return True, 0
    
    rate_limit_cache[user_id]['count'] += 1
    if rate_limit_cache[user_id]['count'] > MAX_REQUESTS_PER_MINUTE:
        wait_time = 60 - (now % 60)
        return False, int(wait_time)
    
    return True, 0

def check_spam(user_id: int) -> bool:
    """Проверка антиспама"""
    current_time = time.time()
    last_time = message_cooldown.get(user_id, 0)
    
    if current_time - last_time < ANTISPAM_INTERVAL:
        return False
    
    message_cooldown[user_id] = current_time
    return True

def check_session_timeout(user_id: int) -> bool:
    """Проверка времени сессии"""
    if user_id not in session_timestamps:
        session_timestamps[user_id] = time.time()
        return True
    
    if time.time() - session_timestamps[user_id] > SESSION_TIMEOUT:
        if user_id in user_sessions:
            del user_sessions[user_id]
        if user_id in admin_modes:
            del admin_modes[user_id]
        session_timestamps[user_id] = time.time()
        return False
    
    session_timestamps[user_id] = time.time()
    return True

def check_content_moderation(text: str) -> bool:
    """Проверка сообщения на запрещённые слова"""
    if not text:
        return True
    
    text_lower = text.lower()
    for word in BLACKLIST_WORDS:
        if word in text_lower:
            return False
    return True

def create_chart(data: Dict, max_width: int = 10) -> str:
    """Создание текстовой диаграммы"""
    if not data:
        return "📊 No data"
    
    max_value = max(data.values()) if data.values() else 1
    result = []
    
    for key, value in sorted(data.items()):
        if max_value > 0:
            width = int((value / max_value) * max_width)
        else:
            width = 0
        bar = "█" * width + "░" * (max_width - width)
        result.append(f"{key}: {bar} {value}")
    
    return "\n".join(result)

def generate_captcha() -> Tuple[Image.Image, str]:
    """Генерация капчи"""
    captcha_text = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6))
    
    image = Image.new('RGB', (200, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
    
    # Шум
    for _ in range(100):
        x = random.randint(0, 200)
        y = random.randint(0, 80)
        draw.point((x, y), fill=(
            random.randint(150, 255),
            random.randint(150, 255),
            random.randint(150, 255)
        ))
    
    # Текст
    for i, char in enumerate(captcha_text):
        x = 20 + i * 30 + random.randint(-5, 5)
        y = 20 + random.randint(-5, 5)
        draw.text((x, y), char, font=font, fill=(
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100)
        ))
    
    # Линии
    for _ in range(5):
        x1 = random.randint(0, 200)
        y1 = random.randint(0, 80)
        x2 = random.randint(0, 200)
        y2 = random.randint(0, 80)
        draw.line((x1, y1, x2, y2), fill=(
            random.randint(100, 200),
            random.randint(100, 200),
            random.randint(100, 200)
        ), width=1)
    
    return image, captcha_text

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin: bool = False, lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Основная клавиатура"""
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

def settings_keyboard(lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Клавиатура настроек"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'btn_turn_on')),
        types.KeyboardButton(t(lang, 'btn_turn_off')),
        types.KeyboardButton(t(lang, 'btn_language')),
        types.KeyboardButton(t(lang, 'btn_back'))
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard(lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Админская клавиатура"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'btn_admin_stats')),
        types.KeyboardButton(t(lang, 'btn_admin_broadcast')),
        types.KeyboardButton(t(lang, 'btn_admin_manage_users')),
        types.KeyboardButton(t(lang, 'btn_admin_find')),
        types.KeyboardButton(t(lang, 'btn_admin_logs')),
        types.KeyboardButton(t(lang, 'btn_admin_tickets')),
        types.KeyboardButton(t(lang, 'btn_admin_settings')),
        types.KeyboardButton(t(lang, 'btn_admin_backup')),
        types.KeyboardButton(t(lang, 'btn_admin_export')),
        types.KeyboardButton(t(lang, 'btn_back'))
    ]
    keyboard.add(*buttons)
    return keyboard

def cancel_keyboard(lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Клавиатура отмены"""
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add(t(lang, 'btn_cancel'))

def language_keyboard() -> types.InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    )
    return keyboard

def get_message_reply_keyboard(message_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для ответа на сообщение"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply'), callback_data=f"reply_{message_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_ignore'), callback_data="ignore")
    )
    return keyboard

def get_admin_ticket_keyboard(ticket_id: int, user_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для тикета"""
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

def get_admin_user_keyboard(user_id: int, is_blocked: bool, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура управления пользователем"""
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

def get_admin_log_keyboard(show_text: bool, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для логов"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_refresh'), callback_data="refresh_logs"),
        types.InlineKeyboardButton(t(lang, 'btn_hide_text') if show_text else t(lang, 'btn_show_text'), 
                                 callback_data="toggle_text")
    )
    return keyboard

# ====== БАЗА ДАННЫХ ======
class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._stats_cache = {}
        self._stats_cache_time = {}
        self._user_cache = {}
        self._user_cache_time = {}
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для подключения к БД"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
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
        """Инициализация базы данных"""
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
                    receive_messages INTEGER DEFAULT 1,
                    is_premium INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0
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
                    file_size INTEGER,
                    timestamp INTEGER,
                    replied_to INTEGER DEFAULT 0,
                    is_read INTEGER DEFAULT 0,
                    moderated INTEGER DEFAULT 1
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
                    replied_at INTEGER,
                    priority INTEGER DEFAULT 1
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
            
            # Статистика пользователя (из v7.0)
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    messages_by_hour TEXT DEFAULT '{}',
                    messages_by_day TEXT DEFAULT '{}',
                    message_types TEXT DEFAULT '{}',
                    total_time_spent INTEGER DEFAULT 0,
                    last_session_start INTEGER,
                    achievements TEXT DEFAULT '[]',
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
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
                    timestamp INTEGER,
                    ip_address TEXT
                )
            ''')
            
            # Настройки бота
            c.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at INTEGER
                )
            ''')
            
            c.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value, updated_at) 
                VALUES ('notifications_enabled', '1', ?)
            ''', (int(time.time()),))
            
            # Капчи
            c.execute('''
                CREATE TABLE IF NOT EXISTS captcha_attempts (
                    user_id INTEGER PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    last_attempt INTEGER,
                    captcha_text TEXT
                )
            ''')
            
            # Модерация
            c.execute('''
                CREATE TABLE IF NOT EXISTS moderation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    reason TEXT,
                    action TEXT,
                    timestamp INTEGER
                )
            ''')
            
            # Индексы
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)')
            
            logger.info("✅ Database initialized with all tables")
    
    def _get_cached_user(self, user_id: int):
        """Получение пользователя с кэшированием"""
        now = time.time()
        if user_id in self._user_cache:
            if now - self._user_cache_time.get(user_id, 0) < 60:
                return self._user_cache[user_id]
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            user = dict(row) if row else None
            
            if user:
                self._user_cache[user_id] = user
                self._user_cache_time[user_id] = now
            
            return user
    
    def _get_cached_user_by_username(self, username: str):
        """Получение пользователя по username с кэшированием"""
        now = time.time()
        cache_key = f"username:{username}"
        
        if cache_key in self._user_cache:
            if now - self._user_cache_time.get(cache_key, 0) < 60:
                return self._user_cache[cache_key]
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE username = ?', (username,))
            row = c.fetchone()
            user = dict(row) if row else None
            
            if user:
                self._user_cache[cache_key] = user
                self._user_cache_time[cache_key] = now
            
            return user
    
    def get_user(self, user_id: int):
        """Получение пользователя"""
        return self._get_cached_user(user_id)
    
    def get_user_by_username(self, username: str):
        """Получение пользователя по username"""
        return self._get_cached_user_by_username(username)
    
    def _clear_user_cache(self, user_id: int = None, username: str = None):
        """Очистка кэша пользователя"""
        if user_id:
            if user_id in self._user_cache:
                del self._user_cache[user_id]
            if user_id in self._user_cache_time:
                del self._user_cache_time[user_id]
        
        if username:
            cache_key = f"username:{username}"
            if cache_key in self._user_cache:
                del self._user_cache[cache_key]
            if cache_key in self._user_cache_time:
                del self._user_cache_time[cache_key]
    
    def get_admin_stats(self):
        """Получение статистики админа"""
        now = time.time()
        if 'admin_stats' in self._stats_cache:
            if now - self._stats_cache_time.get('admin_stats', 0) < 60:
                return self._stats_cache['admin_stats']
        
        stats = self._get_admin_stats_impl()
        self._stats_cache['admin_stats'] = stats
        self._stats_cache_time['admin_stats'] = now
        return stats
    
    def _get_admin_stats_impl(self):
        """Реализация получения статистики админа"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            c.execute('SELECT COUNT(*) FROM users')
            total_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages')
            total_messages = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM blocked_users')
            blocked_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM support_tickets WHERE status = "open"')
            open_tickets = c.fetchone()[0]
            
            today_start = int(time.time()) - 86400
            c.execute('SELECT COUNT(DISTINCT user_id) FROM users WHERE last_active > ?', (today_start,))
            today_active = c.fetchone()[0]
            
            return {
                'total_users': total_users,
                'total_messages': total_messages,
                'blocked_users': blocked_users,
                'open_tickets': open_tickets,
                'today_active': today_active
            }
    
    def register_user(self, user_id: int, username: str, first_name: str):
        """Регистрация пользователя"""
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
            
            self._clear_user_cache(user_id, username)
    
    def update_last_active(self, user_id: int):
        """Обновление времени последней активности"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET last_active = ? WHERE user_id = ?', 
                     (int(time.time()), user_id))
            self._clear_user_cache(user_id)
    
    def increment_stat(self, user_id: int, field: str):
        """Инкремент статистики пользователя"""
        valid_fields = {'messages_received', 'messages_sent', 'link_clicks'}
        if field not in valid_fields:
            return
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(f'UPDATE users SET {field} = {field} + 1 WHERE user_id = ?', 
                     (user_id,))
            self._clear_user_cache(user_id)
    
    def set_receive_messages(self, user_id: int, status: bool):
        """Установка статуса приёма сообщений"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET receive_messages = ? WHERE user_id = ?',
                     (1 if status else 0, user_id))
            self._clear_user_cache(user_id)
    
    def set_language(self, user_id: int, language: str):
        """Установка языка"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET language = ? WHERE user_id = ?',
                     (language, user_id))
            self._clear_user_cache(user_id)
    
    def get_all_users_list(self) -> List[int]:
        """Получение списка всех пользователей"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE is_blocked = 0')
            rows = c.fetchall()
            return [row[0] for row in rows]
    
    def save_message(self, sender_id: int, receiver_id: int, message_type: str, 
                    text: str = "", file_id: Optional[str] = None, 
                    file_unique_id: Optional[str] = None, file_size: int = 0,
                    replied_to: int = 0, moderated: bool = True) -> int:
        """Сохранение сообщения"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO messages 
                (sender_id, receiver_id, message_type, text, file_id, file_unique_id, 
                 file_size, timestamp, replied_to, moderated) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sender_id, receiver_id, message_type, text, file_id, file_unique_id,
                  file_size, int(time.time()), replied_to, 1 if moderated else 0))
            message_id = c.lastrowid
            
            # Добавляем в историю
            preview = text[:50] if text else f"[{message_type}]"
            
            # История для отправителя
            c.execute('''
                INSERT OR REPLACE INTO user_history 
                (user_id, partner_id, message_id, direction, timestamp, preview) 
                VALUES (?, ?, ?, 'outgoing', ?, ?)
            ''', (sender_id, receiver_id, message_id, int(time.time()), preview))
            
            # История для получателя
            c.execute('''
                INSERT OR REPLACE INTO user_history 
                (user_id, partner_id, message_id, direction, timestamp, preview) 
                VALUES (?, ?, ?, 'incoming', ?, ?)
            ''', (receiver_id, sender_id, message_id, int(time.time()), preview))
            
            return message_id
    
    def get_user_messages_stats(self, user_id: int) -> Dict[str, int]:
        """Статистика сообщений пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT messages_received, messages_sent, link_clicks FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            
            if row:
                return {
                    'messages_received': row['messages_received'],
                    'messages_sent': row['messages_sent'],
                    'link_clicks': row['link_clicks']
                }
            return {'messages_received': 0, 'messages_sent': 0, 'link_clicks': 0}
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Проверка блокировки пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return row['is_blocked'] == 1 if row else False
    
    def block_user(self, user_id: int, admin_id: int, reason: str = "") -> bool:
        """Блокировка пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            try:
                # Обновляем обе таблицы
                c.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (user_id,))
                c.execute('''
                    INSERT OR REPLACE INTO blocked_users (user_id, blocked_at, blocked_by, reason)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, now, admin_id, reason))
                self._clear_user_cache(user_id)
                return True
            except:
                return False
    
    def unblock_user(self, user_id: int) -> bool:
        """Разблокировка пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (user_id,))
            c.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
            success = c.rowcount > 0
            if success:
                self._clear_user_cache(user_id)
            return success
    
    def create_support_ticket(self, user_id: int, message: str, file_id: Optional[str] = None,
                            file_unique_id: Optional[str] = None, message_type: str = "text") -> int:
        """Создание тикета поддержки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                INSERT INTO support_tickets 
                (user_id, message, file_id, file_unique_id, message_type, created_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, message, file_id, file_unique_id, message_type, now))
            return c.lastrowid
    
    def get_open_support_tickets(self) -> List[Dict]:
        """Получение открытых тикетов"""
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
    
    def update_support_ticket(self, ticket_id: int, admin_id: int, 
                            reply_text: str, status: str = 'answered'):
        """Обновление тикета поддержки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                UPDATE support_tickets 
                SET admin_id = ?, admin_reply = ?, replied_at = ?, status = ?
                WHERE id = ?
            ''', (admin_id, reply_text, now, status, ticket_id))
    
    def get_recent_messages(self, limit: int = 10, include_text: bool = True) -> List[Dict]:
        """Последние сообщения"""
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
                    msg['text'] = '[HIDDEN]' if msg['text'] else ''
                messages.append(msg)
            return messages

    def add_admin_log(self, log_type: str, user_id: int, target_id: Optional[int] = None,
                     details: str = "", ip_address: str = ""):
        """Добавление лога админа"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO admin_logs (log_type, user_id, target_id, details, timestamp, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (log_type, user_id, target_id, details, int(time.time()), ip_address))

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Получение настройки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
            row = c.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str):
        """Установка настройки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO bot_settings (key, value, updated_at) VALUES (?, ?, ?)', 
                     (key, value, int(time.time())))

    def add_captcha_attempt(self, user_id: int, captcha_text: str = ""):
        """Добавление попытки капчи"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                INSERT OR REPLACE INTO captcha_attempts 
                (user_id, attempts, last_attempt, captcha_text)
                VALUES (?, COALESCE((SELECT attempts FROM captcha_attempts WHERE user_id = ?), 0) + 1, ?, ?)
            ''', (user_id, user_id, now, captcha_text))

    def get_captcha_attempts(self, user_id: int) -> Tuple[int, Optional[str]]:
        """Получение попыток капчи"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT attempts, captcha_text FROM captcha_attempts WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if row:
                return row['attempts'], row['captcha_text']
            return 0, None

    def reset_captcha_attempts(self, user_id: int):
        """Сброс попыток капчи"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM captcha_attempts WHERE user_id = ?', (user_id,))

    def add_moderation_log(self, user_id: int, message: str, reason: str, action: str):
        """Добавление лога модерации"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO moderation_logs (user_id, message, reason, action, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, message, reason, action, int(time.time())))

db = Database()

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"Start from user_id={user_id}")
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    # Регистрация пользователя
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    # Обновление сессии
    session_timestamps[user_id] = time.time()
    
    args = message.text.split()
    
    # Обработка реферальной ссылки
    if len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])
        handle_link_click(user_id, target_id)
        return
    
    # Стандартное приветствие
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    link = generate_link(user_id)
    
    bot.send_message(user_id, t(lang, 'start', link=link), 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def handle_link_click(clicker_id: int, target_id: int):
    """Обработка клика по ссылке"""
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, t('ru', 'user_not_found'))
        return
    
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, t('ru', 'messages_disabled'))
        return
    
    user_sessions[clicker_id] = {
        'target_id': target_id,
        'mode': 'anonymous'
    }
    db.increment_stat(target_id, 'link_clicks')
    
    user = db.get_user(clicker_id)
    lang = user['language'] if user else 'ru'
    
    bot.send_message(
        clicker_id,
        t(lang, 'start_ref'),
        reply_markup=cancel_keyboard(lang)
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработчик callback запросов"""
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
                bot.answer_callback_query(call.id, "✅ Refreshed")
            return
        
        elif data == "toggle_text":
            if user_id == ADMIN_ID:
                current = admin_modes.get(user_id, {}).get('show_text', True)
                admin_modes[user_id] = {'show_text': not current}
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, "✅ Settings changed")
            return
        
        elif data.startswith("lang_"):
            language = data.split("_")[1]
            db.set_language(user_id, language)
            bot.answer_callback_query(call.id, f"✅ Language changed to {language}")
            
            link = generate_link(user_id)
            bot.send_message(user_id, t(language, 'start', link=link), 
                           reply_markup=main_keyboard(user_id == ADMIN_ID, language))
            return
        
        elif data.startswith("reply_"):
            message_id = int(data.split("_")[1])
            
            # Получаем информацию о сообщении
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT sender_id, receiver_id FROM messages WHERE id = ?', (message_id,))
                msg = c.fetchone()
                
                if msg and msg['receiver_id'] == user_id:
                    user_sessions[user_id] = {
                        'target_id': msg['sender_id'],
                        'mode': 'anonymous',
                        'reply_to': message_id
                    }
                    
                    bot.send_message(user_id, "💌 Введите ваш ответ:",
                                    reply_markup=cancel_keyboard(lang))
                    bot.answer_callback_query(call.id)
                else:
                    bot.answer_callback_query(call.id, "❌ Ошибка")
        
        elif data.startswith("admin_block_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            if db.block_user(target_id, ADMIN_ID, "Admin panel"):
                db.add_admin_log("block", user_id, target_id, "Admin panel")
                bot.answer_callback_query(call.id, t(lang, 'block_user'))
                
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
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            if db.unblock_user(target_id):
                db.add_admin_log("unblock", user_id, target_id, "Admin panel")
                bot.answer_callback_query(call.id, t(lang, 'unblock_user'))
                
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + "\n\n✅ Unblocked",
                        reply_markup=get_admin_user_keyboard(target_id, False, lang)
                    )
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, t(lang, 'user_not_blocked_msg'))
        
        elif data.startswith("admin_msg_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            admin_modes[user_id] = f'direct_msg_{target_id}'
            
            bot.send_message(user_id, t(lang, 'direct_message', user_id=target_id),
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_reply_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            ticket_id = int(data.split("_")[2])
            admin_modes[user_id] = f'support_reply_{ticket_id}'
            
            bot.send_message(user_id, f"📝 {t(lang, 'reply_to_ticket')} #{ticket_id}",
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_close_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            ticket_id = int(data.split("_")[2])
            db.update_support_ticket(ticket_id, user_id, "Closed", "closed")
            db.add_admin_log("ticket_close", user_id, None, f"Ticket #{ticket_id}")
            bot.answer_callback_query(call.id, "✅ Closed")
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + "\n\n✅ Ticket closed"
                )
            except:
                pass
        
        elif data.startswith("admin_user_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            find_user_info(admin_id=user_id, query=str(target_id))
            bot.answer_callback_query(call.id)
        
        else:
            bot.answer_callback_query(call.id, "⚠️ Unknown command")
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error")

# ====== ОСНОВНОЙ ОБРАБОТЧИК ======
@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    """Основной обработчик сообщений"""
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    # Игнорирование команд
    if message.text and message.text.startswith('/'):
        return
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    # Проверка ограничения скорости
    allowed, wait_time = check_rate_limit(user_id)
    if not allowed:
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'rate_limit_exceeded', seconds=wait_time))
        return
    
    # Проверка сессии
    if not check_session_timeout(user_id):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'session_expired'))
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    db.update_last_active(user_id)
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    
    # Обработка капчи
    if user_id in captcha_data:
        handle_captcha_response(message, user_id, lang)
        return
    
    # Обработка кнопки "Отмена"
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
    
    # Обработка админских режимов
    if user_id == ADMIN_ID and user_id in admin_modes:
        mode = admin_modes[user_id]
        
        if isinstance(mode, str):
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
    
    # Обработка кнопки "Поддержка"
    if text == t(lang, 'btn_support'):
        handle_support_request(message, lang)
        return
    
    # Обработка анонимных сообщений
    if user_id in user_sessions and user_sessions[user_id]['mode'] == 'anonymous':
        target_id = user_sessions[user_id]['target_id']
        send_anonymous_message(user_id, target_id, message, lang)
        return
    
    # Обработка тикетов поддержки
    if user_id in admin_modes and admin_modes[user_id] == 'support':
        create_support_ticket(message, lang)
        if user_id in admin_modes:
            del admin_modes[user_id]
        return
    
    # Обработка текстовых кнопок
    if message_type == 'text':
        handle_text_button(user_id, text, lang)

def handle_captcha_response(message, user_id: int, lang: str):
    """Обработка ответа на капчу"""
    if user_id not in captcha_data:
        return
    
    captcha_info = captcha_data[user_id]
    user_response = message.text.strip().upper()
    
    # Проверка времени
    if time.time() - captcha_info['timestamp'] > 300:  # 5 минут
        del captcha_data[user_id]
        db.reset_captcha_attempts(user_id)
        bot.send_message(user_id, t(lang, 'captcha_timeout'))
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    # Увеличиваем количество попыток
    captcha_info['attempts'] += 1
    db.add_captcha_attempt(user_id)
    
    # Проверка капчи
    if user_response == captcha_info['text']:
        # Капча пройдена
        del captcha_data[user_id]
        db.reset_captcha_attempts(user_id)
        bot.send_message(user_id, t(lang, 'captcha_correct'))
        
        # Возвращаем к предыдущему действию
        user = db.get_user(user_id)
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
    else:
        # Неверная капча
        if captcha_info['attempts'] >= 3:
            # Превышено количество попыток
            del captcha_data[user_id]
            bot.send_message(user_id, t(lang, 'captcha_failed'))
            bot.send_message(user_id, t(lang, 'main_menu'), 
                            reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        else:
            # Пробуем снова
            bot.send_message(user_id, t(lang, 'captcha_incorrect'))
            
            # Генерация новой капчи
            captcha_image, captcha_text = generate_captcha()
            captcha_data[user_id] = {
                'text': captcha_text,
                'timestamp': time.time(),
                'attempts': captcha_info['attempts']
            }
            
            bio = BytesIO()
            captcha_image.save(bio, 'PNG')
            bio.seek(0)
            
            bot.send_photo(user_id, photo=bio, 
                          caption=t(lang, 'captcha_required'))

def clear_user_state(user_id: int):
    """Очистка состояния пользователя"""
    if user_id in user_sessions:
        del user_sessions[user_id]
    if user_id in admin_modes:
        del admin_modes[user_id]
    if user_id in captcha_data:
        del captcha_data[user_id]

def handle_text_button(user_id: int, text: str, lang: str):
    """Обработка текстовых кнопок"""
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

def show_profile(user_id: int, lang: str):
    """Показ профиля пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ Profile not found", 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    
    receive_status = "✅ Enabled" if user['receive_messages'] else "❌ Disabled"
    username = f"@{user['username']}" if user['username'] else "❌ none"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=stats['messages_received'],
                    sent=stats['messages_sent'],
                    clicks=stats['link_clicks'],
                    receive_status=receive_status,
                    language=user['language'].upper(),
                    last_active=format_time(user['last_active'], lang),
                    registered=format_time(user['created_at'], lang),
                    link=generate_link(user_id))
    
    bot.send_message(user_id, profile_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_stats(user_id: int, lang: str):
    """Показ статистики пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ User not found", 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    
    stats_text = f"""📊 <b>Ваша статистика</b>

<b>📈 Основные метрики:</b>
├ 📨 Получено: <b>{stats['messages_received']}</b> сообщений
├ 📤 Отправлено: <b>{stats['messages_sent']}</b> сообщений
└ 🔗 Переходов: <b>{stats['link_clicks']}</b> раз

<b>📅 Активность:</b>
├ 📆 Зарегистрирован: <b>{format_time(user['created_at'], lang)}</b>
└ 📅 Последняя активность: <b>{format_time(user['last_active'], lang)}</b>

<b>⚙️ Настройки:</b>
├ Приём сообщений: {'✅ Включен' if user['receive_messages'] else '❌ Выключен'}
└ Язык: 🇷🇺 Русский"""
    
    bot.send_message(user_id, stats_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_history(user_id: int, lang: str):
    """Показ истории сообщений"""
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT h.*, u.first_name as partner_name
            FROM user_history h
            LEFT JOIN users u ON h.partner_id = u.user_id
            WHERE h.user_id = ?
            ORDER BY h.timestamp DESC
            LIMIT 20
        ''', (user_id,))
        
        rows = c.fetchall()
        
        if not rows:
            bot.send_message(user_id, "📜 У тебя пока нет сообщений\n\nНачни общение, отправив первую анонимку!",
                            reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
            return
        
        history_text = "📜 <b>История сообщений</b>\n\n<i>Последние 20 сообщений:</i>\n\n"
        
        for i, row in enumerate(rows, 1):
            direction = "⬇️ От" if row['direction'] == 'incoming' else "⬆️ Кому"
            name = row['partner_name'] or f"ID: {row['partner_id']}"
            time_str = format_time(row['timestamp'], lang)
            
            history_text += f"<b>{i}. {direction} {name}</b> <i>({time_str})</i>\n"
            history_text += f"💬 <i>{row['preview']}</i>\n\n"
        
        bot.send_message(user_id, history_text,
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def send_anonymous_message(sender_id: int, receiver_id: int, message, lang: str):
    """Отправка анонимного сообщения"""
    try:
        # Проверка получателя
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, t(lang, 'messages_disabled'))
            return
        
        message_type = message.content_type
        text = message.text or message.caption or ""
        
        # Проверка длины сообщения
        if len(text) > MAX_MESSAGE_LENGTH:
            bot.send_message(sender_id, t(lang, 'message_too_long', max_length=MAX_MESSAGE_LENGTH))
            return
        
        # Проверка модерации
        if not check_content_moderation(text):
            bot.send_message(sender_id, t(lang, 'content_blocked'))
            db.add_moderation_log(sender_id, text[:100], "Blacklisted word", "blocked")
            
            # Уведомление админа
            if CHANNEL and CHANNEL != "":
                try:
                    bot.send_message(CHANNEL, f"🚨 Обнаружено подозрительное сообщение от пользователя {sender_id}")
                except:
                    pass
            return
        
        file_id = None
        file_unique_id = None
        file_size = 0
        
        # Обработка файлов
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
            file_unique_id = message.photo[-1].file_unique_id
            file_size = message.photo[-1].file_size or 0
        elif message_type == 'video':
            file_id = message.video.file_id
            file_unique_id = message.video.file_unique_id
            file_size = message.video.file_size or 0
        elif message_type == 'audio':
            file_id = message.audio.file_id
            file_unique_id = message.audio.file_unique_id
            file_size = message.audio.file_size or 0
        elif message_type == 'voice':
            file_id = message.voice.file_id
            file_unique_id = message.voice.file_unique_id
            file_size = message.voice.file_size or 0
        elif message_type == 'document':
            file_id = message.document.file_id
            file_unique_id = message.document.file_unique_id
            file_size = message.document.file_size or 0
        elif message_type == 'sticker':
            file_id = message.sticker.file_id
            file_unique_id = message.sticker.file_unique_id
        
        # Проверка размера файла
        if file_size > MAX_FILE_SIZE:
            max_size_mb = MAX_FILE_SIZE // (1024 * 1024)
            bot.send_message(sender_id, t(lang, 'file_too_large', max_size=max_size_mb))
            return
        
        # Сохранение сообщения
        replied_to = 0
        if sender_id in user_sessions and 'reply_to' in user_sessions[sender_id]:
            replied_to = user_sessions[sender_id]['reply_to']
        
        message_id = db.save_message(sender_id, receiver_id, message_type, 
                       text, file_id, file_unique_id, file_size, replied_to)
        
        # Обновление статистики
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Формирование сообщения для получателя
        receiver_lang = receiver['language'] if receiver else 'ru'
        
        if text:
            message_content = f"💬 {text}"
        else:
            message_content = "📎 Файл"
        
        # Отправка получателю
        try:
            if message_type == 'text':
                msg = bot.send_message(receiver_id, 
                    t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'photo':
                msg = bot.send_photo(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'video':
                msg = bot.send_video(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'audio':
                msg = bot.send_audio(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'voice':
                msg = bot.send_voice(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'document':
                msg = bot.send_document(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'sticker':
                bot.send_message(receiver_id,
                    t(receiver_lang, 'anonymous_message', message_content="😜 Стикер"),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
                msg = bot.send_sticker(receiver_id, file_id)
        
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(sender_id, t(lang, 'user_blocked_bot'))
                return
            elif e.error_code == 400:
                bot.send_message(sender_id, "❌ Error: invalid message format")
            else:
                logger.error(f"Send error: {e}")
                bot.send_message(sender_id, t(lang, 'system_error'))
            return
        
        # Уведомление отправителю
        bot.send_message(sender_id, t(lang, 'message_sent'),
                        reply_markup=cancel_keyboard(lang))
        
        # Логирование в канал
        if CHANNEL and CHANNEL != "":
            try:
                sender = db.get_user(sender_id)
                log_msg = f"""📨 Новое анонимное сообщение

👤 Отправитель: {sender_id}
🎯 Получатель: {receiver_id}
📝 Тип: {message_type}"""
                
                if text:
                    log_msg += f"\n💬 Текст: {text[:100]}"
                
                if file_id and message_type in ['photo', 'video']:
                    if message_type == 'photo':
                        bot.send_photo(CHANNEL, file_id, caption=log_msg)
                    elif message_type == 'video':
                        bot.send_video(CHANNEL, file_id, caption=log_msg)
                else:
                    bot.send_message(CHANNEL, log_msg)
            except Exception as e:
                logger.error(f"Channel error: {e}")
        
        # Логирование для админа
        db.add_admin_log("anonymous_message", sender_id, receiver_id, 
                        f"{message_type}: {text[:50] if text else 'no text'}")
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.send_message(sender_id, t(lang, 'system_error'))

def handle_support_request(message, lang: str):
    """Обработка запроса в поддержку"""
    user_id = message.from_user.id
    bot.send_message(user_id, t(lang, 'support'), reply_markup=cancel_keyboard(lang))
    admin_modes[user_id] = 'support'

def create_support_ticket(message, lang: str):
    """Создание тикета поддержки"""
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
        
        bot.send_message(user_id, t(lang, 'support_sent'),
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        
        notify_admin_about_ticket(ticket_id, user_id, message_type, text, file_id)
        
    except Exception as e:
        logger.error(f"Ticket error: {e}")
        bot.send_message(user_id, "❌ Ошибка создания тикета")

def notify_admin_about_ticket(ticket_id: int, user_id: int, message_type: str, 
                            text: str, file_id: Optional[str]):
    """Уведомление админа о новом тикете"""
    user = db.get_user(user_id)
    
    notification = f"""🆘 Новый тикет #{ticket_id}

👤 Пользователь: {user['first_name'] if user else '?'}
📱 Username: {f'@{user['username']}' if user and user['username'] else 'нет'}
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
        
        if CHANNEL and CHANNEL != str(ADMIN_ID) and CHANNEL != "":
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

def reply_to_support_ticket(message, ticket_id: int, lang: str):
    """Ответ на тикет поддержки"""
    try:
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

{reply_text}

<i>С уважением, команда бота 🤖</i>"""
        
        # Отправляем ответ пользователю
        try:
            if message_type == 'text':
                bot.send_message(ticket_id, user_reply)
            elif message_type == 'photo':
                bot.send_photo(ticket_id, file_id, caption=user_reply)
            elif message_type == 'video':
                bot.send_video(ticket_id, file_id, caption=user_reply)
            elif message_type == 'document':
                bot.send_document(ticket_id, file_id, caption=user_reply)
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ Пользователь заблокировал бота.")
            else:
                raise
        
        bot.send_message(ADMIN_ID, f"✅ Ответ на тикет #{ticket_id} отправлен",
                        reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Reply error: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка отправки ответа")

def send_direct_admin_message(message, target_user_id: int, lang: str):
    """Отправка прямого сообщения от админа"""
    try:
        message_type = message.content_type
        text = message.text or message.caption or ""
        
        if not text and message_type == 'text':
            bot.send_message(ADMIN_ID, "❌ Введите текст")
            return
        
        file_id = None
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        elif message_type == 'sticker':
            file_id = message.sticker.file_id
        
        # Формирование сообщения
        user_message = f"""📢 Важное уведомление

{text}

<i>С уважением, команда бота 🤖</i>"""
        
        try:
            # Отправка пользователю
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
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ Пользователь {target_user_id} заблокировал бота.")
                return
            else:
                raise
        
        # Уведомление админа
        bot.send_message(ADMIN_ID, t(lang, 'message_sent_admin', user_id=target_user_id, message_type=message_type),
                        reply_markup=admin_keyboard(lang))
        
        # Логирование
        db.add_admin_log("direct_message", ADMIN_ID, target_user_id, 
                        f"{message_type}: {text[:50] if text else 'no text'}")
        
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка отправки")

def generate_qr_code(user_id: int, lang: str):
    """Генерация QR-кода"""
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(
            version=1,
            box_size=6,
            border=2,
            error_correction=qrcode.constants.ERROR_CORRECT_L
        )
        qr.add_data(link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG', optimize=True, quality=85)
        bio.seek(0)
        
        bot.send_photo(user_id, photo=bio, caption=t(lang, 'qr_code', link=link),
                      reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
    except Exception as e:
        logger.error(f"QR error: {e}")
        bot.send_message(user_id, "❌ Ошибка генерации QR-кода")

def show_help(user_id: int, lang: str):
    """Показ помощи"""
    bot.send_message(user_id, t(lang, 'help'), 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id: int, text: str, lang: str):
    """Обработка админских команд"""
    
    if text == t(lang, 'btn_admin_stats'):
        show_admin_stats(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_broadcast'):
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(admin_id, t(lang, 'broadcast_start'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_find'):
        admin_modes[admin_id] = 'find_user'
        bot.send_message(admin_id, t(lang, 'find_user'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_logs'):
        show_message_logs(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_tickets'):
        show_support_tickets(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_settings'):
        show_admin_settings(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_block'):
        admin_modes[admin_id] = 'block_user'
        bot.send_message(admin_id, t(lang, 'block_instruction'),
                        reply_markup=cancel_keyboard(lang))
    
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

def show_admin_stats(admin_id: int, lang: str):
    """Показ статистики админа"""
    stats = db.get_admin_stats()
    
    stats_text = f"""👑 <b>Статистика бота</b>

<b>📊 Основные метрики:</b>
├ Всего пользователей: <b>{stats['total_users']}</b>
├ Активных сегодня: <b>{stats['today_active']}</b>
├ Всего сообщений: <b>{stats['total_messages']}</b>
├ Заблокированных: <b>{stats['blocked_users']}</b>
└ Открытых тикетов: <b>{stats['open_tickets']}</b>"""
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard(lang))

def start_broadcast(admin_id: int, message, lang: str):
    """Запуск рассылки"""
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
        
        if total == 0:
            bot.send_message(admin_id, "❌ Нет пользователей")
            return
        
        sent = 0
        failed = 0
        blocked = 0
        
        progress_msg = bot.send_message(admin_id, f"⏳ Начинаю рассылку... Всего: {total}")
        
        for user_id in users:
            try:
                if db.is_user_blocked(user_id):
                    blocked += 1
                    continue
                
                bot.send_message(user_id, text, parse_mode="HTML")
                sent += 1
                time.sleep(0.05)
            except:
                failed += 1
        
        bot.edit_message_text(
            chat_id=admin_id,
            message_id=progress_msg.message_id,
            text=f"""✅ <b>Рассылка завершена!</b>

<b>📊 Результаты:</b>
├ Всего пользователей: <b>{total}</b>
├ Успешно отправлено: <b>{sent}</b>
├ Не удалось отправить: <b>{failed}</b>
└ Пропущено (заблок.): <b>{blocked}</b>"""
        )
        
        # Логирование
        db.add_admin_log("broadcast", admin_id, None, f"Sent: {sent}/{total}")
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

def find_user_info(admin_id: int, query: str, lang: str):
    """Поиск информации о пользователе"""
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
        
        username = f"@{user['username']}" if user['username'] else "❌ нет"
        receive_status = "✅ Включено" if user['receive_messages'] else "❌ Выключено"
        block_status = "🔴 ЗАБЛОКИРОВАН" if is_blocked else "🟢 АКТИВЕН"
        
        user_info = f"""🔍 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

<b>👤 Основные данные:</b>
├ ID: <code>{user['user_id']}</code>
├ Имя: <b>{user['first_name']}</b>
├ Юзернейм: {username}
├ Зарегистрирован: {format_time(user['created_at'], lang)}
└ Последняя активность: {format_time(user['last_active'], lang)}

<b>📊 Статистика:</b>
├ 📨 Получено: <b>{stats['messages_received']}</b>
├ 📤 Отправлено: <b>{stats['messages_sent']}</b>
├ 🔗 Переходов: <b>{stats['link_clicks']}</b>
└ ⚙️ Приём сообщений: {receive_status}

<b>🚫 Статус:</b> {block_status}"""
        
        bot.send_message(admin_id, user_info, 
                        reply_markup=get_admin_user_keyboard(user['user_id'], is_blocked, lang))
        
    except Exception as e:
        logger.error(f"Find user error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard(lang))

def handle_block_user(admin_id: int, query: str, lang: str):
    """Обработка блокировки пользователя"""
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
                db.add_admin_log("unblock", admin_id, user['user_id'], "Admin panel")
                bot.send_message(admin_id, t(lang, 'unblock_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'user_not_blocked_msg'),
                               reply_markup=admin_keyboard(lang))
        else:
            if db.block_user(user['user_id'], admin_id, "Block panel"):
                db.add_admin_log("block", admin_id, user['user_id'], "Admin panel")
                bot.send_message(admin_id, t(lang, 'block_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'user_already_blocked'),
                               reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Block user error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard(lang))

def show_message_logs(admin_id: int, lang: str):
    """Показ логов сообщений"""
    show_text = admin_modes.get(admin_id, {}).get('show_text', True) if isinstance(admin_modes.get(admin_id), dict) else True
    messages = db.get_recent_messages(limit=10, include_text=show_text)
    
    if not messages:
        bot.send_message(admin_id, t(lang, 'no_logs'), reply_markup=get_admin_log_keyboard(show_text, lang))
        return
    
    logs_text = f"{t(lang, 'logs')}:\n\n"
    
    for i, msg in enumerate(messages, 1):
        sender_name = msg.get('sender_name', '?')
        receiver_name = msg.get('receiver_name', '?')
        
        logs_text += f"{i}. {format_time(msg['timestamp'], lang)}\n"
        logs_text += f"   👤 Отправитель: {msg['sender_id']} - {sender_name}\n"
        logs_text += f"   🎯 Получатель: {msg['receiver_id']} - {receiver_name}\n"
        logs_text += f"   📝 Тип: {msg['message_type']}\n"
        
        if msg['text']:
            logs_text += f"   💬 Текст: {msg['text']}\n"
        
        logs_text += "\n"
    
    bot.send_message(admin_id, logs_text, reply_markup=get_admin_log_keyboard(show_text, lang))

def show_support_tickets(admin_id: int, lang: str):
    """Показ тикетов поддержки"""
    tickets = db.get_open_support_tickets()
    
    if not tickets:
        bot.send_message(admin_id, t(lang, 'no_tickets'), reply_markup=admin_keyboard(lang))
        return
    
    tickets_text = f"{t(lang, 'tickets')} ({len(tickets)}):\n\n"
    
    for i, ticket in enumerate(tickets, 1):
        tickets_text += f"{i}. Тикет #{ticket['id']}\n"
        tickets_text += f"   👤 Пользователь: {ticket['user_id']} - {ticket['first_name']}\n"
        tickets_text += f"   📱 Username: {f'@{ticket['username']}' if ticket['username'] else 'нет'}\n"
        tickets_text += f"   📅 Создан: {format_time(ticket['created_at'], lang)}\n"
        
        if ticket['message']:
            preview = ticket['message'][:100] + "..." if len(ticket['message']) > 100 else ticket['message']
            tickets_text += f"   💬 Сообщение: {preview}\n"
        
        tickets_text += f"   📝 Тип: {ticket['message_type']}\n\n"
    
    bot.send_message(admin_id, tickets_text, reply_markup=admin_keyboard(lang))

def show_admin_settings(admin_id: int, lang: str):
    """Показ настроек админа"""
    notifications = db.get_setting('notifications_enabled', '1')
    notifications_status = "✅ Enabled" if notifications == '1' else "❌ Disabled"
    channel_status = "✅ Настроен" if CHANNEL and CHANNEL != "" else "❌ Не настроен"
    
    settings_text = f"""⚙️ <b>Настройки администратора</b>

<b>🔔 Уведомления:</b>
├ В боте: {notifications_status}
├ В канал: {channel_status}
└ Антиспам: {ANTISPAM_INTERVAL} сек.

<b>⚡ Производительность:</b>
├ База данных: ✅ Работает
└ Кэширование: ✅ Активно"""
    
    bot.send_message(admin_id, settings_text, reply_markup=admin_keyboard(lang))

# ====== FLASK РОУТЫ ======
@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик вебхука Telegram"""
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
    """Проверка здоровья приложения"""
    try:
        stats = db.get_admin_stats()
        return jsonify({
            'status': 'ok', 
            'time': datetime.now().isoformat(),
            'bot': 'Anony SMS',
            'version': '9.0',
            'users': stats['total_users'],
            'messages': stats['total_messages'],
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    """Пинг для поддержания активности"""
    return jsonify({'status': 'active', 'timestamp': time.time()})

@app.route('/admin', methods=['GET'])
def admin_panel_web():
    """Веб-панель админа (из v7.0)"""
    if not CHANNEL:
        return "Admin panel not configured"
    
    stats = db.get_admin_stats()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Anony SMS Admin</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); padding: 30px; border-radius: 20px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); }}
            .header {{ text-align: center; margin-bottom: 40px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }}
            .stat-card {{ background: rgba(255, 255, 255, 0.2); padding: 25px; border-radius: 15px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); transition: transform 0.3s; }}
            .stat-card:hover {{ transform: translateY(-5px); }}
            .stat-value {{ font-size: 36px; font-weight: bold; margin: 15px 0; color: #fff; }}
            .stat-label {{ font-size: 14px; opacity: 0.9; }}
            h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
            .footer {{ text-align: center; margin-top: 40px; opacity: 0.7; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 Anony SMS Admin Panel</h1>
                <p>Real-time bot statistics and management</p>
            </div>
            <div class="stats">
                <div class="stat-card"><div class="stat-label">👥 Users</div><div class="stat-value">{stats['total_users']}</div></div>
                <div class="stat-card"><div class="stat-label">📨 Messages</div><div class="stat-value">{stats['total_messages']}</div></div>
                <div class="stat-card"><div class="stat-label">🚫 Blocked</div><div class="stat-value">{stats['blocked_users']}</div></div>
                <div class="stat-card"><div class="stat-label">🆘 Tickets</div><div class="stat-value">{stats['open_tickets']}</div></div>
                <div class="stat-card"><div class="stat-label">📈 Today Active</div><div class="stat-value">{stats['today_active']}</div></div>
            </div>
            <div class="footer">
                <p>Anony SMS Bot v9.0 | Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>© 2024 Anony SMS. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ====== МОНИТОРИНГ ======
def monitor_bot():
    """Мониторинг состояния бота"""
    while True:
        try:
            stats = db.get_admin_stats()
            
            # Проверка низкой активности
            if stats['messages_24h'] < 10 and stats['total_users'] > 100:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Low activity\nLast 24h: {stats['messages_24h']} messages\nUsers: {stats['total_users']}")
                except:
                    pass
            
            # Проверка большого количества тикетов
            if stats['open_tickets'] > 10:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Many tickets: {stats['open_tickets']}")
                except:
                    pass
            
            # Проверка целостности БД
            try:
                with db.get_connection() as conn:
                    c = conn.cursor()
                    c.execute('PRAGMA integrity_check')
                    result = c.fetchone()
                    if result[0] != 'ok':
                        bot.send_message(ADMIN_ID, f"⚠️ DB integrity issue: {result[0]}")
            except Exception as e:
                logger.error(f"DB check error: {e}")
            
            # Очистка старых кэшей
            current_time = time.time()
            keys_to_delete = []
            for key, timestamp in session_timestamps.items():
                if current_time - timestamp > SESSION_TIMEOUT * 2:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del session_timestamps[key]
                if key in user_sessions:
                    del user_sessions[key]
                if key in admin_modes:
                    del admin_modes[key]
            
            time.sleep(3600)  # Проверка каждый час
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(300)

def keep_alive():
    """Поддержание активности на Render"""
    while True:
        try:
            if WEBHOOK_HOST:
                response = requests.get(f"{WEBHOOK_HOST}/ping", timeout=10)
                if response.status_code == 200:
                    logger.debug("✅ Ping successful")
                else:
                    logger.warning(f"⚠️ Ping failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ping error: {e}")
        time.sleep(300)  # Пинг каждые 5 минут

# ====== ЗАПУСК БОТА ======
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Anony SMS Bot v9.0 - Merged Professional Edition")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # Проверка токена
    if not TOKEN:
        logger.error("❌ Bot token not found! Set PLAY environment variable.")
        sys.exit(1)
    
    try:
        bot_info = bot.get_me()
        logger.info(f"🤖 Bot: @{bot_info.username} ({bot_info.first_name})")
        logger.info(f"👑 Admin ID: {ADMIN_ID}")
        logger.info(f"📢 Channel: {CHANNEL if CHANNEL else 'Not configured'}")
        logger.info(f"🌐 Webhook: {WEBHOOK_HOST if WEBHOOK_HOST else 'Polling mode'}")
        logger.info(f"💾 Database: {DB_PATH}")
    except Exception as e:
        logger.error(f"❌ Bot initialization error: {e}")
        sys.exit(1)
    
    # Запуск мониторинга
    try:
        monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
        monitor_thread.start()
        logger.info("✅ Monitoring started")
        
        # Keep-alive для Render
        if WEBHOOK_HOST:
            ping_thread = threading.Thread(target=keep_alive, daemon=True)
            ping_thread.start()
            logger.info("✅ Keep-alive service started")
            
    except Exception as e:
        logger.error(f"❌ Background services error: {e}")
    
    # Запуск бота
    try:
        if WEBHOOK_HOST:
            logger.info(f"🌐 Setting up webhook for {WEBHOOK_HOST}")
            
            try:
                bot.remove_webhook()
                time.sleep(1)
            except:
                pass
            
            bot.set_webhook(
                url=f"{WEBHOOK_HOST}/webhook",
                max_connections=100,
                timeout=60,
                drop_pending_updates=True,
                allowed_updates=None
            )
            logger.info("✅ Webhook configured successfully")
            
            # Запуск Flask
            app.run(
                host='0.0.0.0',
                port=PORT,
                debug=False,
                threaded=True,
                use_reloader=False
            )
            
        else:
            logger.info("🔄 Starting in polling mode")
            bot.remove_webhook()
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=20,
                long_polling_timeout=20,
                logger_level=logging.INFO
            )
            
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
