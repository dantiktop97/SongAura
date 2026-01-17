#!/usr/bin/env python3
"""
Anony SMS Bot - Ultimate Professional Version v8.0
Fully functional with all security features and optimizations
"""

import os
import sys
import time
import json
import logging
import qrcode
import threading
import random
import string
from datetime import datetime, timedelta
from io import BytesIO
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import requests
from typing import Dict, List, Optional, Any, Tuple
import csv
import gzip

from flask import Flask, request, jsonify
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
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_MESSAGE_LENGTH = 4000
SESSION_TIMEOUT = 300  # 5 минут

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
bot_info = None

# Получаем информацию о боте
try:
    bot_info = bot.get_me()
    logger.info(f"🤖 Bot initialized: @{bot_info.username}")
except Exception as e:
    logger.error(f"Failed to get bot info: {e}")
    bot_info = types.User(id=0, is_bot=False, first_name="Bot")

# ====== ПЕРЕВОДЫ (СОКРАЩЕННЫЕ ДЛЯ КРАТКОСТИ) ======
TRANSLATIONS = {
    'ru': {
        'start': """🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉

Рады видеть тебя 💬✨
Здесь тайны и эмоции превращаются в сообщения 👀💌

<b>🔗 Твоя личная ссылка:</b>
<code>{link}</code>

👇 <b>Жми кнопки ниже и погнали!</b> 🚀""",
        
        'my_link': """🔗 <b>Твоя уникальная ссылка для анонимок:</b>

<code>{link}</code>

<i>📤 Поделись с друзьями в:
• Чатах 💬
• Соцсетях 🌐
• Сторис 📲</i>""",
        
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

<b>🔗 Твоя ссылка:</b>
<code>{link}</code>""",
        
        'anonymous_message': """📨 <b>Ты получил анонимное сообщение!</b>

<i>💭 Кто-то отправил тебе тайное послание...</i>

{text}

<b>💌 Хочешь ответить анонимно?</b>
Нажми кнопку «Ответить» ниже 👇""",
        
        'message_sent': """✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Получатель: <b>{receiver_name}</b>
🔒 Твоя личность: <b>скрыта</b>
💭 Сообщение доставлено успешно!</i>""",
        
        'settings': "⚙️ <b>Настройки</b>\n\n<i>Настрой бот под себя:</i>",
        'turn_on': "✅ <b>Приём анонимных сообщений включён!</b>",
        'turn_off': "✅ <b>Приём анонимных сообщений отключён!</b>",
        'language': "🌐 <b>Выберите язык</b>",
        'blocked': "🚫 <b>Вы заблокированы в этом боте.</b>",
        'user_not_found': "❌ Пользователь не найден.",
        'messages_disabled': "❌ Этот пользователь отключил получение сообщений.",
        'spam_wait': "⏳ Подождите 2 секунды перед следующим сообщением.",
        'canceled': "❌ Действие отменено",
        'qr_code': """📱 <b>Твой персональный QR-код</b>
<code>{link}</code>""",
        
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
        
        'btn_reply': "💌 Ответить",
        'btn_ignore': "🚫 Игнор",
        'btn_block': "🚫 Заблокировать",
        'btn_unblock': "✅ Разблокировать",
        'btn_message': "✉️ Написать ему",
        'btn_refresh': "🔄 Обновить",
        'btn_toggle_text': "🔕 Скрыть текст",
        'btn_show_text': "🔔 Показать текст",
    },
    
    'en': {
        'start': """🎉 <b>Welcome to Anony SMS!</b> 🎉

Glad to see you 💬✨
Here secrets and emotions turn into messages 👀💌

<b>🔗 Your personal link:</b>
<code>{link}</code>

👇 <b>Click the buttons below and let's go!</b> 🚀""",
        
        'my_link': """🔗 <b>Your unique link for anonymous messages:</b>

<code>{link}</code>

<i>📤 Share with friends in:
• Chats 💬
• Social networks 🌐
• Stories 📲</i>""",
        
        'profile': """👤 <b>Your profile</b>

<b>📊 Identification:</b>
├ ID: <code>{user_id}</code>
├ Name: <b>{first_name}</b>
└ Username: {username}

<b>📈 Statistics:</b>
├ 📨 Received: <b>{received}</b>
├ 📤 Sent: <b>{sent}</b>
├ 🔗 Clicks: <b>{clicks}</b>
└ ⏱️ Avg. response time: <b>{response_time}</b>

<b>🔗 Your link:</b>
<code>{link}</code>""",
        
        'anonymous_message': """📨 <b>You received an anonymous message!</b>

<i>💭 Someone sent you a secret message...</i>

{text}

<b>💌 Want to reply anonymously?</b>
Click the "Reply" button below 👇""",
        
        'message_sent': """✅ <b>Message sent anonymously!</b>

<i>🎯 Recipient: <b>{receiver_name}</b>
🔒 Your identity: <b>hidden</b>
💭 Message delivered successfully!</i>""",
        
        'settings': "⚙️ <b>Settings</b>\n\n<i>Customize the bot for yourself:</i>",
        'turn_on': "✅ <b>Anonymous message reception enabled!</b>",
        'turn_off': "✅ <b>Anonymous message reception disabled!</b>",
        'language': "🌐 <b>Choose language</b>",
        'blocked': "🚫 <b>You are blocked in this bot.</b>",
        'user_not_found': "❌ User not found.",
        'messages_disabled': "❌ This user has disabled message reception.",
        'spam_wait': "⏳ Wait 2 seconds before the next message.",
        'canceled': "❌ Action canceled",
        'qr_code': """📱 <b>Your personal QR code</b>
<code>{link}</code>""",
        
        # Buttons
        'btn_my_link': "📩 My link",
        'btn_profile': "👤 Profile",
        'btn_stats': "📊 Statistics",
        'btn_settings': "⚙️ Settings",
        'btn_qr': "📱 QR code",
        'btn_help': "ℹ️ Help",
        'btn_support': "🆘 Support",
        'btn_admin': "👑 Admin",
        'btn_turn_on': "🔔 Enable messages",
        'btn_turn_off': "🔕 Disable messages",
        'btn_language': "🌐 Language",
        'btn_back': "⬅️ Back",
        'btn_cancel': "❌ Cancel",
        'btn_history': "📜 History",
        
        'btn_reply': "💌 Reply",
        'btn_ignore': "🚫 Ignore",
        'btn_block': "🚫 Block",
        'btn_unblock': "✅ Unblock",
        'btn_message': "✉️ Message",
        'btn_refresh': "🔄 Refresh",
        'btn_toggle_text': "🔕 Hide text",
        'btn_show_text': "🔔 Show text",
    }
}

# ====== УТИЛИТЫ ======
def t(lang: str, key: str, **kwargs) -> str:
    """Функция перевода с fallback на русский"""
    if lang not in TRANSLATIONS:
        lang = 'ru'
    if key not in TRANSLATIONS[lang]:
        if 'ru' in TRANSLATIONS and key in TRANSLATIONS['ru']:
            return TRANSLATIONS['ru'][key].format(**kwargs) if kwargs else TRANSLATIONS['ru'][key]
        return key
    return TRANSLATIONS[lang][key].format(**kwargs) if kwargs else TRANSLATIONS[lang][key]

def format_time(timestamp: Optional[int], lang: str = 'ru') -> str:
    """Форматирование времени"""
    if not timestamp:
        return "никогда"
    
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return "только что"
        elif diff.seconds < 3600:
            minutes = diff.seconds // 60
            return f"{minutes} минут назад"
        else:
            hours = diff.seconds // 3600
            return f"{hours} часов назад"
    elif diff.days == 1:
        return "вчера"
    elif diff.days < 7:
        return f"{diff.days} дней назад"
    else:
        return dt.strftime("%d.%m.%Y")

def generate_link(user_id: int) -> str:
    """Генерация ссылки на бота с user_id"""
    try:
        if not bot_info or not hasattr(bot_info, 'username'):
            bot_info_local = bot.get_me()
            bot_username = bot_info_local.username
        else:
            bot_username = bot_info.username
        
        if not bot_username:
            return f"https://t.me/{bot_info.id}?start={user_id}"
        
        return f"https://t.me/{bot_username}?start={user_id}"
    except Exception as e:
        logger.error(f"Link generation error: {e}")
        return f"https://t.me/anonymous_sms_bot?start={user_id}"

def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """Проверка ограничения скорости запросов"""
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

def generate_captcha() -> Tuple[Image.Image, str]:
    """Генерация капчи"""
    captcha_text = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6))
    
    image = Image.new('RGB', (200, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
    
    # Накладываем шум
    for _ in range(100):
        x = random.randint(0, 200)
        y = random.randint(0, 80)
        draw.point((x, y), fill=(
            random.randint(150, 255),
            random.randint(150, 255),
            random.randint(150, 255)
        ))
    
    # Рисуем текст
    for i, char in enumerate(captcha_text):
        x = 20 + i * 30 + random.randint(-5, 5)
        y = 20 + random.randint(-5, 5)
        draw.text((x, y), char, font=font, fill=(
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100)
        ))
    
    # Добавляем линии
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
    """Расширенная админская клавиатура"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("📊 Статистика"),
        types.KeyboardButton("📢 Рассылка"),
        types.KeyboardButton("👥 Массовое управление"),
        types.KeyboardButton("🔍 Найти пользователя"),
        types.KeyboardButton("🚫 Блок/Разблок"),
        types.KeyboardButton("📋 Логи"),
        types.KeyboardButton("🆘 Тикеты"),
        types.KeyboardButton("📢 Автопостинг"),
        types.KeyboardButton("📡 Мониторинг"),
        types.KeyboardButton("📊 Аналитика"),
        types.KeyboardButton("🛡️ Автомодерация"),
        types.KeyboardButton("🔔 Уведомления"),
        types.KeyboardButton("💾 Бэкапы"),
        types.KeyboardButton("🧪 A/B тесты"),
        types.KeyboardButton("💰 Монетизация"),
        types.KeyboardButton("⚙️ Настройки"),
        types.KeyboardButton("⬅️ Назад")
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

def get_message_reply_keyboard(target_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для ответа на сообщение"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply'), callback_data=f"reply_{target_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_ignore'), callback_data="ignore")
    )
    return keyboard

def get_admin_ticket_keyboard(ticket_id: int, user_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для тикета"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply_ticket'), callback_data=f"support_reply_{ticket_id}"),
        types.InlineKeyboardButton("✅ Закрыть", callback_data=f"support_close_{ticket_id}")
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
        types.InlineKeyboardButton(t(lang, 'btn_toggle_text') if show_text else t(lang, 'btn_show_text'), 
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
        conn.execute('PRAGMA cache_size=-10000')
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
                    is_premium INTEGER DEFAULT 0
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
            
            # Статистика пользователя
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
                    timestamp INTEGER,
                    user_agent TEXT
                )
            ''')
            
            # Капчи
            c.execute('''
                CREATE TABLE IF NOT EXISTS captcha_attempts (
                    user_id INTEGER PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    last_attempt INTEGER,
                    captcha_text TEXT
                )
            ''')
            
            # Индексы для производительности
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_created ON support_tickets(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_blocked_users ON blocked_users(user_id)')
            
            logger.info("✅ Database initialized")
    
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
        """Получение статистики админа с кэшированием"""
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
            
            return {
                'total_users': total_users,
                'today_active': today_active,
                'total_messages': total_messages,
                'messages_24h': messages_24h,
                'new_users_24h': new_users_24h,
                'blocked_users': blocked_users,
                'open_tickets': open_tickets,
            }
    
    # ====== ОСНОВНЫЕ МЕТОДЫ ======
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
            c.execute('SELECT user_id FROM users')
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
            
            c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ?', (user_id,))
            sent_count = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE receiver_id = ?', (user_id,))
            received_count = c.fetchone()[0]
            
            return {
                'messages_sent': sent_count,
                'messages_received': received_count
            }
    
    def get_user_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        """История сообщений пользователя"""
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
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Проверка блокировки пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            return c.fetchone() is not None
    
    def block_user(self, user_id: int, admin_id: int, reason: str = "") -> bool:
        """Блокировка пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            try:
                c.execute('''
                    INSERT OR IGNORE INTO blocked_users (user_id, blocked_at, blocked_by, reason)
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

db = Database()

# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======
def clear_user_state(user_id: int):
    """Очистка состояния пользователя"""
    if user_id in user_sessions:
        del user_sessions[user_id]
    if user_id in admin_modes:
        del admin_modes[user_id]
    if user_id in captcha_data:
        del captcha_data[user_id]

def show_my_link(user_id: int, lang: str, is_admin: bool):
    """Показ личной ссылки"""
    link = generate_link(user_id)
    bot.send_message(user_id, t(lang, 'my_link', link=link),
                    reply_markup=main_keyboard(is_admin, lang))

def show_settings_menu(user_id: int, lang: str):
    """Показ меню настроек"""
    bot.send_message(user_id, t(lang, 'settings'),
                    reply_markup=settings_keyboard(lang))

def turn_messages_on(user_id: int, lang: str):
    """Включение получения сообщений"""
    db.set_receive_messages(user_id, True)
    bot.send_message(user_id, t(lang, 'turn_on'),
                    reply_markup=settings_keyboard(lang))

def turn_messages_off(user_id: int, lang: str):
    """Выключение получения сообщений"""
    db.set_receive_messages(user_id, False)
    bot.send_message(user_id, t(lang, 'turn_off'),
                    reply_markup=settings_keyboard(lang))

def show_language_menu(user_id: int, lang: str):
    """Показ меню выбора языка"""
    bot.send_message(user_id, t(lang, 'language'),
                    reply_markup=language_keyboard())

def show_main_menu(user_id: int, lang: str, is_admin: bool):
    """Показ главного меню"""
    bot.send_message(user_id, "🏠 Главное меню",
                    reply_markup=main_keyboard(is_admin, lang))

def show_admin_panel(user_id: int, lang: str):
    """Показ админ-панели"""
    if user_id == ADMIN_ID:
        bot.send_message(user_id, "👑 Панель администратора",
                        reply_markup=admin_keyboard(lang))

def cancel_action(user_id: int, lang: str, is_admin: bool):
    """Отмена действия"""
    clear_user_state(user_id)
    bot.send_message(user_id, t(lang, 'canceled'),
                    reply_markup=main_keyboard(is_admin, lang))

def show_profile(user_id: int, lang: str):
    """Показ профиля пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ Профиль не найден", 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    
    receive_status = "✅ Включен" if user['receive_messages'] else "❌ Выключен"
    username = f"@{user['username']}" if user['username'] else "❌ нет"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=stats['messages_received'],
                    sent=stats['messages_sent'],
                    clicks=user['link_clicks'],
                    response_time="N/A",
                    link=generate_link(user_id))
    
    bot.send_message(user_id, profile_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_history(user_id: int, lang: str):
    """Показ истории сообщений"""
    history = db.get_user_history(user_id, limit=20)
    
    if not history:
        bot.send_message(user_id, "📜 У тебя пока нет сообщений",
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    history_text = "📜 История сообщений:\n\n"
    
    for i, item in enumerate(history, 1):
        direction = "⬇️ От" if item['direction'] == 'incoming' else "⬆️ Кому"
        name = item['partner_name'] or f"ID: {item['partner_id']}"
        time_str = format_time(item['timestamp'], lang)
        
        history_text += f"{i}. {direction} {name} ({time_str})\n"
        history_text += f"💬 {item['preview']}\n\n"
    
    bot.send_message(user_id, history_text,
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

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
    help_text = """ℹ️ Помощь по боту:

📨 Как получать сообщения:
1. Нажми «📩 Моя ссылка»
2. Скопируй свою уникальную ссылку
3. Поделись с друзьями
4. Жди анонимные сообщения!

✉️ Как отправлять сообщения:
1. Перейди по чужой ссылке
2. Напиши сообщение
3. Отправь — получатель не узнает твою личность!

📎 Что можно отправить:
✅ Текстовые сообщения
✅ Фотографии
✅ Видео
✅ Голосовые сообщения
✅ Стикеры
✅ Документы

🔒 Безопасность:
• Полная анонимность
• Конфиденциальность гарантирована
• Автоматическая модерация
• Защита от спама"""
    
    bot.send_message(user_id, help_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start', 'lang', 'menu', 'stats', 'history', 'help', 'support'])
def start_command(message):
    """Обработчик команды /start и других"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"COMMAND: {message.text} from user_id={user_id}")
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    # Проверка ограничения скорости
    allowed, wait_time = check_rate_limit(user_id)
    if not allowed:
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, f"⏳ Слишком много запросов. Подождите {wait_time} секунд.")
        return
    
    # Регистрация/обновление пользователя
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    # Обновление сессии
    session_timestamps[user_id] = time.time()
    
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
        show_main_menu(user_id, lang, user_id == ADMIN_ID)
        return
    
    # Обработка команды /stats
    if message.text.startswith('/stats'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_profile(user_id, lang)
        return
    
    # Обработка команды /history
    if message.text.startswith('/history'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_user_history(user_id, lang)
        return
    
    # Обработка команды /help
    if message.text.startswith('/help'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_help(user_id, lang)
        return
    
    # Обработка команды /support
    if message.text.startswith('/support'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        handle_support_request(user_id, lang)
        return
    
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
    # Проверка ограничения скорости
    allowed, wait_time = check_rate_limit(clicker_id)
    if not allowed:
        user = db.get_user(clicker_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(clicker_id, f"⏳ Слишком много запросов. Подождите {wait_time} секунд.")
        return
    
    # Проверка антиспама
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
    
    user_sessions[clicker_id] = target_id
    db.increment_stat(target_id, 'link_clicks')
    
    user = db.get_user(clicker_id)
    lang = user['language'] if user else 'ru'
    
    bot.send_message(
        clicker_id,
        f"💌 <b>Отправь анонимное сообщение</b> <i>{target_user['first_name']}</i>!\n\n"
        f"<i>Напиши сообщение, фото, видео или голосовое сообщение</i>",
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
                show_message_logs(user_id, lang)
                bot.answer_callback_query(call.id, "✅ Обновлено")
            return
        
        elif data == "toggle_text":
            if user_id == ADMIN_ID:
                current = admin_modes.get(user_id, {}).get('show_text', True)
                admin_modes[user_id] = {'show_text': not current}
                show_message_logs(user_id, lang)
                bot.answer_callback_query(call.id, "✅ Настройки изменены")
            return
        
        elif data.startswith("lang_"):
            language = data.split("_")[1]
            db.set_language(user_id, language)
            bot.answer_callback_query(call.id, "✅ Язык изменен")
            
            link = generate_link(user_id)
            bot.send_message(user_id, t(language, 'start', link=link), 
                           reply_markup=main_keyboard(user_id == ADMIN_ID, language))
            return
        
        elif data.startswith("reply_"):
            target_id = int(data.split("_")[1])
            user_sessions[user_id] = target_id
            
            target_user = db.get_user(target_id)
            if target_user:
                bot.send_message(user_id, f"💌 Отправь ответное сообщение {target_user['first_name']}", 
                               reply_markup=cancel_keyboard(lang))
            else:
                bot.send_message(user_id, "💌 Отправь ответное сообщение", 
                               reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("admin_block_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            if db.block_user(target_id, ADMIN_ID, "Admin panel"):
                bot.answer_callback_query(call.id, f"✅ Пользователь {target_id} заблокирован.")
                
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + "\n\n🚫 Пользователь заблокирован",
                        reply_markup=get_admin_user_keyboard(target_id, True, lang)
                    )
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, "✅ Пользователь уже заблокирован")
        
        elif data.startswith("admin_unblock_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            if db.unblock_user(target_id):
                bot.answer_callback_query(call.id, f"✅ Пользователь {target_id} разблокирован.")
                
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
                bot.answer_callback_query(call.id, "✅ Пользователь не был заблокирован")
        
        elif data.startswith("admin_msg_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            target_id = int(data.split("_")[2])
            admin_modes[user_id] = f'direct_msg_{target_id}'
            
            bot.send_message(user_id, f"✉️ Отправь сообщение для пользователя {target_id}",
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_reply_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            ticket_id = int(data.split("_")[2])
            admin_modes[user_id] = f'support_reply_{ticket_id}'
            
            bot.send_message(user_id, f"📝 Ответить на тикет #{ticket_id}",
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_close_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Нет доступа")
                return
            
            ticket_id = int(data.split("_")[2])
            db.update_support_ticket(ticket_id, user_id, "Closed", "closed")
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
            find_user_info(admin_id=user_id, query=str(target_id), lang=lang)
            bot.answer_callback_query(call.id)
        
        else:
            bot.answer_callback_query(call.id, "⚠️ Неизвестная команда")
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

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
        bot.send_message(user_id, f"⏳ Слишком много запросов. Подождите {wait_time} секунд.")
        return
    
    # Проверка сессии
    if not check_session_timeout(user_id):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, "⏰ Сессия истекла. Начните заново.")
        show_main_menu(user_id, lang, user_id == ADMIN_ID)
        return
    
    db.update_last_active(user_id)
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    
    # Обработка кнопки "Отмена"
    if text == t(lang, 'btn_cancel'):
        cancel_action(user_id, lang, user_id == ADMIN_ID)
        return
    
    # Обработка кнопки "Админ"
    if text == "👑 Админ" and user_id == ADMIN_ID:
        show_admin_panel(user_id, lang)
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
    
    # Обработка анонимных сообщений
    if user_id in user_sessions:
        target_id = user_sessions[user_id]
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

def handle_text_button(user_id: int, text: str, lang: str):
    """Обработка текстовых кнопок"""
    is_admin = user_id == ADMIN_ID
    
    # Словарь обработчиков кнопок
    button_handlers = {
        t(lang, 'btn_my_link'): lambda: show_my_link(user_id, lang, is_admin),
        t(lang, 'btn_profile'): lambda: show_profile(user_id, lang),
        t(lang, 'btn_stats'): lambda: show_profile(user_id, lang),
        t(lang, 'btn_settings'): lambda: show_settings_menu(user_id, lang),
        t(lang, 'btn_qr'): lambda: generate_qr_code(user_id, lang),
        t(lang, 'btn_help'): lambda: show_help(user_id, lang),
        t(lang, 'btn_support'): lambda: handle_support_request(user_id, lang),
        t(lang, 'btn_history'): lambda: show_user_history(user_id, lang),
        t(lang, 'btn_admin'): lambda: show_admin_panel(user_id, lang) if is_admin else None,
        t(lang, 'btn_turn_on'): lambda: turn_messages_on(user_id, lang),
        t(lang, 'btn_turn_off'): lambda: turn_messages_off(user_id, lang),
        t(lang, 'btn_language'): lambda: show_language_menu(user_id, lang),
        t(lang, 'btn_back'): lambda: show_main_menu(user_id, lang, is_admin),
        t(lang, 'btn_cancel'): lambda: cancel_action(user_id, lang, is_admin),
    }
    
    # Проверяем есть ли обработчик для кнопки
    if text in button_handlers:
        handler = button_handlers[text]
        if handler:
            handler()
    elif is_admin:
        # Обработка админских команд
        handle_admin_command(user_id, text, lang)
    else:
        # Если это не кнопка, возможно это сообщение
        if user_id in user_sessions:
            target_id = user_sessions[user_id]
            send_anonymous_message(user_id, target_id, 
                                  type('Message', (), {'content_type': 'text', 'text': text}), 
                                  lang)
        else:
            # Если это просто текст, покажем главное меню
            show_main_menu(user_id, lang, is_admin)

def send_anonymous_message(sender_id: int, receiver_id: int, message, lang: str):
    """Отправка анонимного сообщения"""
    try:
        # Проверка ограничения скорости
        allowed, wait_time = check_rate_limit(sender_id)
        if not allowed:
            bot.send_message(sender_id, f"⏳ Слишком много запросов. Подождите {wait_time} секунд.")
            return
        
        # Проверка антиспама
        if not check_spam(sender_id):
            bot.send_message(sender_id, t(lang, 'spam_wait'))
            return
        
        # Проверка получателя
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, t(lang, 'messages_disabled'))
            return
        
        message_type = message.content_type
        text = message.text or message.caption or ""
        
        # Проверка длины сообщения
        if len(text) > MAX_MESSAGE_LENGTH:
            bot.send_message(sender_id, f"❌ Сообщение слишком длинное (максимум {MAX_MESSAGE_LENGTH} символов).")
            return
        
        # Проверка модерации
        if not check_content_moderation(text):
            bot.send_message(sender_id, "❌ Сообщение содержит запрещённые слова.")
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
            bot.send_message(sender_id, f"❌ Файл слишком большой (максимум {max_size_mb}MB).")
            return
        
        # Сохранение сообщения
        message_id = db.save_message(sender_id, receiver_id, message_type, 
                       text, file_id, file_unique_id, file_size)
        
        # Формирование сообщения для получателя
        receiver_lang = receiver['language'] if receiver else 'ru'
        caption = t(receiver_lang, 'anonymous_message', 
                   text=f"💬 Текст:\n<code>{html.escape(text)}</code>\n\n" if text else "")
        
        try:
            # Отправка сообщения получателю
            if message_type == 'text':
                msg = bot.send_message(receiver_id, caption, 
                                      reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'photo':
                msg = bot.send_photo(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'video':
                msg = bot.send_video(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'audio':
                msg = bot.send_audio(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'voice':
                msg = bot.send_voice(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'document':
                msg = bot.send_document(receiver_id, file_id, caption=caption,
                                      reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'sticker':
                if caption:
                    bot.send_message(receiver_id, caption)
                msg = bot.send_sticker(receiver_id, file_id, 
                                     reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(sender_id, "❌ Пользователь заблокировал бота.")
                return
            elif e.error_code == 400:
                bot.send_message(sender_id, "❌ Ошибка: неверный формат сообщения")
            else:
                logger.error(f"Send error: {e}")
                bot.send_message(sender_id, "❌ Произошла системная ошибка.")
            return
        
        # Обновление статистики
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Уведомление отправителя
        bot.send_message(sender_id, t(lang, 'message_sent', receiver_name=receiver['first_name']),
                        reply_markup=cancel_keyboard(lang))
        
        # Логирование в канал
        if CHANNEL and CHANNEL != "":
            try:
                sender = db.get_user(sender_id)
                log_msg = f"""📨 Новое анонимное сообщение

👤 От: {sender_id} ({sender['first_name'] if sender else '?'})
🎯 Кому: {receiver_id} ({receiver['first_name'] if receiver else '?'})
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
        
        # Очистка сессии после успешной отправки
        if sender_id in user_sessions:
            del user_sessions[sender_id]
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.send_message(sender_id, "❌ Произошла системная ошибка.")

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
        bot.send_message(ADMIN_ID, f"✅ Сообщение отправлено\n👤 Пользователь: {target_user_id}\n📝 Тип: {message_type}",
                        reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка отправки")

def handle_support_request(user_id: int, lang: str):
    """Обработка запроса в поддержку"""
    bot.send_message(user_id, "🆘 Опишите вашу проблему как можно подробнее", 
                    reply_markup=cancel_keyboard(lang))
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
        
        bot.send_message(user_id, f"✅ Запрос в поддержку отправлен!\nВаш тикет: #{ticket_id}",
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
        
        user_reply = f"""🆘 Ответ службы поддержки

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
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ Пользователь {user_id} заблокировал бота.")
            else:
                raise
        
        bot.send_message(ADMIN_ID, f"✅ Ответ на тикет #{ticket_id} отправлен",
                        reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Reply error: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка отправки ответа")

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id: int, text: str, lang: str):
    """Обработка админских команд"""
    
    if text == "📊 Статистика":
        show_admin_stats(admin_id, lang)
    
    elif text == "📢 Рассылка":
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(admin_id, "📢 Создание рассылки\nОтправь сообщение которое будет отправлено всем пользователям.", 
                        reply_markup=cancel_keyboard(lang))
    
    elif text == "👥 Массовое управление":
        mass_management_menu(admin_id, lang)
    
    elif text == "🔍 Найти пользователя":
        admin_modes[admin_id] = 'find_user'
        bot.send_message(admin_id, "🔍 Введите ID пользователя или юзернейм (без @):", 
                        reply_markup=cancel_keyboard(lang))
    
    elif text == "🚫 Блок/Разблок":
        admin_modes[admin_id] = 'block_user'
        bot.send_message(admin_id, "🚫 Введите ID пользователя или юзернейм (без @):", 
                        reply_markup=cancel_keyboard(lang))
    
    elif text == "📋 Логи":
        show_message_logs(admin_id, lang)
    
    elif text == "🆘 Тикеты":
        show_support_tickets(admin_id, lang)
    
    elif text == "📢 Автопостинг":
        auto_posting_menu(admin_id, lang)
    
    elif text == "📡 Мониторинг":
        realtime_monitoring(admin_id, lang)
    
    elif text == "📊 Аналитика":
        analytics_menu(admin_id, lang)
    
    elif text == "🛡️ Автомодерация":
        ban_templates_menu(admin_id, lang)
    
    elif text == "🔔 Уведомления":
        notifications_menu(admin_id, lang)
    
    elif text == "💾 Бэкапы":
        backup_menu(admin_id, lang)
    
    elif text == "🧪 A/B тесты":
        ab_testing_menu(admin_id, lang)
    
    elif text == "💰 Монетизация":
        monetization_menu(admin_id, lang)
    
    elif text == "⚙️ Настройки":
        show_admin_settings(admin_id, lang)
    
    elif text == "⬅️ Назад":
        show_main_menu(admin_id, lang, True)
    
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
    
    stats_text = f"""👑 Статистика бота

📊 Основные метрики:
├ Всего пользователей: <b>{stats['total_users']}</b>
├ Активных сегодня: <b>{stats['today_active']}</b>
├ Всего сообщений: <b>{stats['total_messages']}</b>
├ Сообщений за 24ч: <b>{stats['messages_24h']}</b>
├ Новых за 24ч: <b>{stats['new_users_24h']}</b>
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
            bot.send_message(admin_id, "❌ Пользователей не найдено")
            return
        
        sent = 0
        failed = 0
        blocked = 0
        
        progress_msg = bot.send_message(admin_id, f"⏳ Начинаю рассылку...\n\nВсего пользователей: {total}")
        
        # Используем ThreadPoolExecutor для параллельной отправки
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for user_id in users:
                futures.append(executor.submit(send_broadcast_message, user_id, text))
            
            for future in as_completed(futures):
                result = future.result()
                if result == 'sent':
                    sent += 1
                elif result == 'failed':
                    failed += 1
                elif result == 'blocked':
                    blocked += 1
                
                # Обновление прогресса каждые 20 сообщений
                if (sent + failed + blocked) % 20 == 0:
                    try:
                        bot.edit_message_text(
                            chat_id=admin_id,
                            message_id=progress_msg.message_id,
                            text=f"⏳ Отправлено: {sent}/{total}"
                        )
                    except:
                        pass
        
        bot.edit_message_text(
            chat_id=admin_id,
            message_id=progress_msg.message_id,
            text=f"""✅ Рассылка завершена!

📊 РЕЗУЛЬТАТЫ:
├ Всего пользователей: <b>{total}</b>
├ Успешно отправлено: <b>{sent}</b>
├ Не удалось отправить: <b>{failed}</b>
└ Пропущено (заблок.): <b>{blocked}</b>"""
        )
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

def send_broadcast_message(user_id: int, text: str) -> str:
    """Отправка одного сообщения рассылки"""
    try:
        if db.is_user_blocked(user_id):
            return 'blocked'
        
        bot.send_message(user_id, text, parse_mode="HTML")
        time.sleep(0.05)
        return 'sent'
        
    except ApiTelegramException as e:
        if e.error_code == 403:
            return 'failed'
        else:
            logger.error(f"Broadcast send error: {e}")
            return 'failed'
    except Exception as e:
        logger.error(f"Broadcast send error: {e}")
        return 'failed'

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
            bot.send_message(admin_id, "❌ Пользователь не найден", reply_markup=admin_keyboard(lang))
            return
        
        stats = db.get_user_messages_stats(user['user_id'])
        is_blocked = db.is_user_blocked(user['user_id'])
        
        username = f"@{user['username']}" if user['username'] else "❌ нет"
        receive_status = "✅ Включен" if user['receive_messages'] else "❌ Выключен"
        block_status = "🔴 ЗАБЛОКИРОВАН" if is_blocked else "🟢 АКТИВЕН"
        
        user_info = f"""🔍 ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ

👤 ОСНОВНЫЕ ДАННЫЕ:
├ ID: <code>{user['user_id']}</code>
├ Имя: <b>{user['first_name']}</b>
├ Юзернейм: {username}
├ Зарегистрирован: {format_time(user['created_at'], lang)}
└ Последняя активность: {format_time(user['last_active'], lang)}

📊 СТАТИСТИКА:
├ 📨 Получено: <b>{stats['messages_received']}</b>
├ 📤 Отправлено: <b>{stats['messages_sent']}</b>
├ 🔗 Переходов: <b>{user['link_clicks']}</b>
└ ⚙️ Приём сообщений: {receive_status}

🚫 СТАТУС: {block_status}"""
        
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
            bot.send_message(admin_id, "❌ Пользователь не найден", reply_markup=admin_keyboard(lang))
            return
        
        is_blocked = db.is_user_blocked(user['user_id'])
        
        if is_blocked:
            if db.unblock_user(user['user_id']):
                bot.send_message(admin_id, f"✅ Пользователь {user['user_id']} разблокирован.",
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, "✅ Пользователь не был заблокирован.",
                               reply_markup=admin_keyboard(lang))
        else:
            if db.block_user(user['user_id'], admin_id, "Block panel"):
                bot.send_message(admin_id, f"✅ Пользователь {user['user_id']} заблокирован.",
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, "✅ Пользователь уже заблокирован.",
                               reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Block user error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard(lang))

def show_message_logs(admin_id: int, lang: str):
    """Показ логов сообщений"""
    show_text = admin_modes.get(admin_id, {}).get('show_text', True) if isinstance(admin_modes.get(admin_id), dict) else True
    messages = db.get_recent_messages(limit=10, include_text=show_text)
    
    if not messages:
        bot.send_message(admin_id, "📋 Логи сообщений пусты", reply_markup=get_admin_log_keyboard(show_text, lang))
        return
    
    logs_text = "📋 Логи сообщений:\n\n"
    
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

def show_support_tickets(admin_id: int, lang: str):
    """Показ тикетов поддержки"""
    tickets = db.get_open_support_tickets()
    
    if not tickets:
        bot.send_message(admin_id, "🆘 Открытых тикетов нет", reply_markup=admin_keyboard(lang))
        return
    
    tickets_text = f"🆘 Открытые тикеты ({len(tickets)}):\n\n"
    
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

def show_admin_settings(admin_id: int, lang: str):
    """Показ настроек админа"""
    notifications = db.get_setting('notifications_enabled', '1')
    notifications_status = "✅ Включены" if notifications == '1' else "❌ Выключены"
    channel_status = "✅ Настроен" if CHANNEL and CHANNEL != "" else "❌ Не настроен"
    
    settings_text = f"""⚙️ Настройки администратора

🔔 УВЕДОМЛЕНИЯ:
├ Новые сообщения: {notifications_status}
└ В канал: {channel_status}

⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:
├ Антиспам: {ANTISPAM_INTERVAL} сек.
└ База данных: ✅ Работает"""
    
    bot.send_message(admin_id, settings_text, reply_markup=admin_keyboard(lang))

def mass_management_menu(admin_id: int, lang: str):
    """Меню массового управления"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("📊 Статистика по группам"),
        types.KeyboardButton("🎯 Фильтр пользователей"),
        types.KeyboardButton("📨 Массовая рассылка по фильтру"),
        types.KeyboardButton("🚫 Массовая блокировка"),
        types.KeyboardButton("📋 Экспорт по фильтру"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    bot.send_message(admin_id, "👥 Массовое управление пользователями", reply_markup=keyboard)

def auto_posting_menu(admin_id: int, lang: str):
    """Меню автопостинга"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("➕ Добавить пост", callback_data="auto_post_add"),
        types.InlineKeyboardButton("📋 Список постов", callback_data="auto_post_list"),
        types.InlineKeyboardButton("⚙️ Настройки расписания", callback_data="auto_post_schedule"),
        types.InlineKeyboardButton("▶️ Запустить", callback_data="auto_post_start"),
        types.InlineKeyboardButton("⏸️ Остановить", callback_data="auto_post_stop")
    )
    bot.send_message(admin_id, "📢 Система автопостинга", reply_markup=keyboard)

def realtime_monitoring(admin_id: int, lang: str):
    """Мониторинг в реальном времени"""
    with db.get_connection() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users WHERE last_active > ?', (int(time.time()) - 300,))
        active_5min = c.fetchone()[0]
        
        c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', (int(time.time()) - 300,))
        messages_5min = c.fetchone()[0]
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_monitoring"))
    
    message = f"""📡 Мониторинг в реальном времени
⏱️ За последние 5 минут:
├ 👥 Активных: {active_5min}
├ 📨 Сообщений: {messages_5min}
└ ⚡ Скорость: {messages_5min/5 if messages_5min > 0 else 0:.1f} сообщ/мин
"""
    bot.send_message(admin_id, message, reply_markup=keyboard)

def analytics_menu(admin_id: int, lang: str):
    """Меню аналитики"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("📈 Ежедневный отчет"),
        types.KeyboardButton("📊 Недельная аналитика"),
        types.KeyboardButton("📅 Месячный отчет"),
        types.KeyboardButton("👤 Анализ пользователей"),
        types.KeyboardButton("💬 Анализ сообщений"),
        types.KeyboardButton("📊 Конверсия"),
        types.KeyboardButton("📉 Удержание"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    bot.send_message(admin_id, "📊 Система аналитики", reply_markup=keyboard)

def ban_templates_menu(admin_id: int, lang: str):
    """Меню шаблонов банов"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("➕ Создать шаблон", callback_data="ban_template_create"),
        types.InlineKeyboardButton("📋 Список шаблонов", callback_data="ban_template_list"),
        types.InlineKeyboardButton("🚀 Автомодерация", callback_data="auto_moderation"),
        types.InlineKeyboardButton("⚠️ Проверить пользователя", callback_data="check_user_risk")
    )
    bot.send_message(admin_id, "🛡️ Система автоматической модерации", reply_markup=keyboard)

def notifications_menu(admin_id: int, lang: str):
    """Меню уведомлений"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("✅ Новые пользователи", callback_data="toggle_new_user_notif"),
        types.InlineKeyboardButton("🔔 Настройка канала", callback_data="setup_notif_channel"),
        types.InlineKeyboardButton("📱 Push-уведомления", callback_data="push_notifications"),
        types.InlineKeyboardButton("📊 Логи уведомлений", callback_data="notification_logs")
    )
    bot.send_message(admin_id, "🔔 Система уведомлений", reply_markup=keyboard)

def backup_menu(admin_id: int, lang: str):
    """Меню бэкапов"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💾 Создать бэкап", callback_data="backup_create"),
        types.InlineKeyboardButton("📥 Восстановить", callback_data="backup_restore"),
        types.InlineKeyboardButton("📋 Список бэкапов", callback_data="backup_list"),
        types.InlineKeyboardButton("⚙️ Автобэкапы", callback_data="auto_backup_settings"),
        types.InlineKeyboardButton("🔐 Шифрование", callback_data="backup_encryption")
    )
    bot.send_message(admin_id, "💾 Система бэкапов и восстановления", reply_markup=keyboard)

def ab_testing_menu(admin_id: int, lang: str):
    """Меню A/B тестирования"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🧪 Создать тест", callback_data="ab_test_create"),
        types.InlineKeyboardButton("📊 Активные тесты", callback_data="ab_test_list"),
        types.InlineKeyboardButton("📈 Результаты", callback_data="ab_test_results"),
        types.InlineKeyboardButton("⚙️ Настройки", callback_data="ab_test_settings")
    )
    bot.send_message(admin_id, "🧪 Система A/B тестирования", reply_markup=keyboard)

def monetization_menu(admin_id: int, lang: str):
    """Меню монетизации"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💎 Премиум функции", callback_data="premium_features"),
        types.InlineKeyboardButton("💰 Настройка платежей", callback_data="payment_settings"),
        types.KeyboardButton("📊 Финансовая статистика"),
        types.InlineKeyboardButton("📈 Анализ доходов", callback_data="revenue_analytics")
    )
    bot.send_message(admin_id, "💰 Система монетизации", reply_markup=keyboard)

def create_backup(admin_id: int, lang: str):
    """Создание бэкапа базы данных"""
    try:
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        with open(DB_PATH, 'rb') as f:
            db_content = f.read()
        
        # Сжатие
        compressed = gzip.compress(db_content)
        
        bio = BytesIO(compressed)
        bio.name = backup_filename + '.gz'
        
        bot.send_document(admin_id, bio, 
                         caption=f"💾 Бэкап базы данных\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        bot.send_message(admin_id, f"❌ Ошибка бэкапа: {e}")

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
            'version': '8.0',
            'users': stats['total_users'],
            'messages': stats['total_messages'],
            'uptime': time.time() - start_time if 'start_time' in globals() else 0
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    """Пинг для поддержания активности"""
    return jsonify({'status': 'active', 'timestamp': time.time()})

# ====== МОНИТОРИНГ И ОПТИМИЗАЦИЯ ======
def monitor_bot():
    """Мониторинг состояния бота"""
    while True:
        try:
            stats = db.get_admin_stats()
            
            # Проверка низкой активности
            if stats['messages_24h'] < 10 and stats['total_users'] > 100:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Низкая активность\nПоследние 24ч: {stats['messages_24h']} сообщений\nПользователей: {stats['total_users']}")
                except:
                    pass
            
            # Проверка большого количества тикетов
            if stats['open_tickets'] > 10:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Много тикетов: {stats['open_tickets']}")
                except:
                    pass
            
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
            
            # Очистка rate limit кэша
            minute = int(current_time // 60)
            keys_to_delete = []
            for key, data in rate_limit_cache.items():
                if data['minute'] != minute:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del rate_limit_cache[key]
            
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

def cleanup_old_data():
    """Очистка старых данных"""
    while True:
        try:
            # Удаляем старые сессии (старше 7 дней)
            week_ago = int(time.time()) - 604800
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('DELETE FROM user_history WHERE timestamp < ?', (week_ago,))
                deleted = c.rowcount
                if deleted > 0:
                    logger.info(f"🧹 Очищено {deleted} старых записей истории")
            
            # Очистка кэша
            if hasattr(db, '_stats_cache'):
                db._stats_cache.clear()
                db._stats_cache_time.clear()
                db._user_cache.clear()
                db._user_cache_time.clear()
            
            time.sleep(86400)  # Раз в день
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            time.sleep(3600)

# ====== ЗАПУСК БОТА ======
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Anony SMS Bot v8.0")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # Проверка токена
    if not TOKEN:
        logger.error("❌ Bot token not found! Set PLAY environment variable.")
        sys.exit(1)
    
    # Получение информации о боте
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
    
    # Запуск фоновых задач
    try:
        # Мониторинг
        monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
        monitor_thread.start()
        logger.info("✅ Monitoring started")
        
        # Очистка данных
        cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
        cleanup_thread.start()
        logger.info("✅ Cleanup service started")
        
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
            
            # Удаление старого вебхука
            try:
                bot.remove_webhook()
                time.sleep(1)
            except:
                pass
            
            # Настройка нового вебхука
            bot.set_webhook(
                url=f"{WEBHOOK_HOST}/webhook",
                max_connections=100,
                timeout=60,
                certificate=None,
                ip_address=None,
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
            # Локальный запуск (поллинг)
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
