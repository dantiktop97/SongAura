#!/usr/bin/env python3
"""
Anony SMS Bot - Premium Version v3.0
Полностью переработанный и исправленный бот
"""

import os
import sys
import time
import json
import logging
import qrcode
import re
import threading
from datetime import datetime, timedelta
from io import BytesIO
from contextlib import contextmanager
import sqlite3
import requests
from collections import Counter

from flask import Flask, request, jsonify
from telebot import TeleBot, types
from telebot.apihelper import ApiException

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
CHANNEL = os.getenv("CHANNEL", "")  # ID канала для уведомлений
WEBHOOK_HOST = "https://songaura.onrender.com"
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = "data.db"

ANTISPAM_INTERVAL = 2  # Уменьшил до 2 секунд
MAX_MESSAGES_PER_DAY = 50  # Лимит сообщений в день

# ====== ЛОГГИРОВАНИЕ ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

bot = TeleBot(TOKEN, parse_mode="HTML")
app = Flask(__name__)

# Глобальные переменные
last_message_time = {}
user_reply_targets = {}  # {user_id: target_id}
admin_modes = {}
user_daily_messages = {}  # {user_id: {'count': X, 'date': 'YYYY-MM-DD'}}
admin_log_settings = {ADMIN_ID: {'show_text': True}}  # Настройки показа текста для админа

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
                    receive_messages INTEGER DEFAULT 1,
                    theme TEXT DEFAULT 'classic',
                    level INTEGER DEFAULT 1,
                    exp INTEGER DEFAULT 0,
                    is_premium INTEGER DEFAULT 0,
                    premium_until INTEGER DEFAULT 0
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
                    reason TEXT
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
            
            # Достижения
            c.execute('''
                CREATE TABLE IF NOT EXISTS achievements (
                    user_id INTEGER,
                    achievement_id TEXT,
                    unlocked_at INTEGER,
                    UNIQUE(user_id, achievement_id)
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
            
            # Вставка дефолтных настроек
            c.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value) 
                VALUES ('notifications_enabled', '1')
            ''')
            
            logger.info("✅ База данных инициализирована")
    
    # ====== ПОЛЬЗОВАТЕЛИ ======
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
    
    # ====== СООБЩЕНИЯ ======
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
            
            # Получаем слова из сообщений
            c.execute('SELECT text FROM messages WHERE sender_id = ? AND text IS NOT NULL AND text != ""', (user_id,))
            messages = c.fetchall()
            
            words = []
            for msg in messages:
                text = msg[0]
                if text:
                    words.extend(re.findall(r'\b\w+\b', text.lower()))
            
            top_words = []
            if words:
                word_counts = Counter(words)
                top_words = word_counts.most_common(5)
            
            # Статистика
            c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ?', (user_id,))
            sent_count = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE receiver_id = ?', (user_id,))
            received_count = c.fetchone()[0]
            
            # Часто используемые эмодзи
            c.execute('SELECT text FROM messages WHERE sender_id = ?', (user_id,))
            all_texts = [row[0] for row in c.fetchall() if row[0]]
            emojis = []
            for text in all_texts:
                emojis.extend(re.findall(r'[^\w\s,.]', text))
            
            top_emojis = []
            if emojis:
                emoji_counts = Counter(emojis)
                top_emojis = emoji_counts.most_common(5)
            
            return {
                'messages_sent': sent_count,
                'messages_received': received_count,
                'top_words': top_words,
                'top_emojis': top_emojis
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
    
    def get_today_message_count(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            today_start = int(time.time()) - (time.time() % 86400)
            c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ? AND timestamp > ?', 
                     (user_id, today_start))
            return c.fetchone()[0]
    
    # ====== БЛОКИРОВКИ ======
    def is_user_blocked(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            return c.fetchone() is not None
    
    def block_user(self, user_id, admin_id, reason=""):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('INSERT OR REPLACE INTO blocked_users VALUES (?, ?, ?, ?)', 
                     (user_id, now, admin_id, reason))
    
    def unblock_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
    
    def get_blocked_users_count(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM blocked_users')
            return c.fetchone()[0]
    
    # ====== ПОДДЕРЖКА ======
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
    
    # ====== ДОСТИЖЕНИЯ ======
    def unlock_achievement(self, user_id, achievement_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            try:
                c.execute('''
                    INSERT OR IGNORE INTO achievements (user_id, achievement_id, unlocked_at)
                    VALUES (?, ?, ?)
                ''', (user_id, achievement_id, now))
                return True
            except:
                return False
    
    def get_user_achievements(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT achievement_id, unlocked_at FROM achievements WHERE user_id = ?', (user_id,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    # ====== ЛОГИ ======
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
    
    # ====== НАСТРОЙКИ ======
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
    
    # ====== СТАТИСТИКА ======
    def get_admin_stats(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            
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
            
            return {
                'total_users': total_users,
                'total_messages': total_messages,
                'blocked_users': blocked_users,
                'new_users_24h': new_users_24h,
                'messages_24h': messages_24h,
                'open_tickets': open_tickets
            }

db = Database()

# ====== УТИЛИТЫ ======
def format_time(timestamp):
    if not timestamp:
        return "никогда"
    
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return "только что"
        elif diff.seconds < 3600:
            return f"{diff.seconds // 60} мин. назад"
        else:
            return f"{diff.seconds // 3600} ч. назад"
    elif diff.days == 1:
        return "вчера"
    elif diff.days < 7:
        return f"{diff.days} дн. назад"
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

def check_daily_limit(user_id):
    today = datetime.now().strftime('%Y-%m-%d')
    
    if user_id not in user_daily_messages:
        user_daily_messages[user_id] = {'date': today, 'count': 1}
        return True
    
    if user_daily_messages[user_id]['date'] != today:
        user_daily_messages[user_id] = {'date': today, 'count': 1}
        return True
    
    if user_daily_messages[user_id]['count'] >= MAX_MESSAGES_PER_DAY:
        return False
    
    user_daily_messages[user_id]['count'] += 1
    return True

def get_message_reply_keyboard(target_id):
    """Клавиатура для ответа на сообщение"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💌 Ответить", callback_data=f"reply_{target_id}"),
        types.InlineKeyboardButton("🚫 Игнор", callback_data="ignore")
    )
    return keyboard

def get_admin_ticket_keyboard(ticket_id, user_id):
    """Клавиатура для тикета поддержки"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("📝 Ответить", callback_data=f"support_reply_{ticket_id}"),
        types.InlineKeyboardButton("✅ Закрыть", callback_data=f"support_close_{ticket_id}")
    )
    keyboard.add(
        types.InlineKeyboardButton("👤 Профиль", callback_data=f"admin_user_{user_id}"),
        types.InlineKeyboardButton("🚫 Блок", callback_data=f"admin_block_{user_id}")
    )
    return keyboard

def get_admin_log_keyboard():
    """Клавиатура для логов"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    show_text = admin_log_settings.get(ADMIN_ID, {}).get('show_text', True)
    keyboard.add(
        types.InlineKeyboardButton("📋 Обновить", callback_data="refresh_logs"),
        types.InlineKeyboardButton(f"{'🔕 Скрыть текст' if show_text else '🔔 Показать текст'}", 
                                 callback_data="toggle_text")
    )
    return keyboard

def get_admin_user_keyboard(user_id):
    """Клавиатура для админа при просмотре пользователя"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🚫 Заблокировать", callback_data=f"admin_block_{user_id}"),
        types.InlineKeyboardButton("✉️ Написать ему", callback_data=f"admin_msg_{user_id}")
    )
    return keyboard

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin=False):
    """Главное меню"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        types.KeyboardButton("📩 Моя ссылка"),
        types.KeyboardButton("👤 Профиль"),
        types.KeyboardButton("⚙️ Настройки"),
        types.KeyboardButton("📱 QR-код"),
        types.KeyboardButton("ℹ️ Помощь"),
        types.KeyboardButton("🆘 Поддержка")
    ]
    
    if is_admin:
        buttons.append(types.KeyboardButton("👑 Админ"))
    
    keyboard.add(*buttons)
    return keyboard

def settings_keyboard():
    """Меню настроек"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("🔔 Вкл. сообщения"),
        types.KeyboardButton("🔕 Выкл. сообщения"),
        types.KeyboardButton("🌐 Язык"),
        types.KeyboardButton("🎨 Тема"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard():
    """Админ-панель"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("📊 Статистика"),
        types.KeyboardButton("📢 Рассылка"),
        types.KeyboardButton("👥 Пользователи"),
        types.KeyboardButton("🔍 Найти"),
        types.KeyboardButton("📋 Логи"),
        types.KeyboardButton("🆘 Тикеты"),
        types.KeyboardButton("⚙️ Настройки"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

def cancel_keyboard():
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Отмена")

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"START: user_id={user_id}")
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, "🚫 Вы заблокированы в этом боте.")
        return
    
    # Регистрируем пользователя
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    # Разблокируем первое достижение
    db.unlock_achievement(user_id, "first_join")
    
    # Проверяем параметры команды
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        # Пользователь перешел по ссылке
        target_id = int(args[1])
        handle_link_click(user_id, target_id)
        return
    
    # Новое приветствие
    link = generate_link(user_id)
    welcome_text = f"""🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉

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

👇 <b>Жми кнопки ниже и погнали!</b> 🚀"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, welcome_text, reply_markup=main_keyboard(is_admin))

def handle_link_click(clicker_id, target_id):
    """Обработка перехода по ссылке"""
    if not check_spam(clicker_id):
        bot.send_message(clicker_id, "⏳ Подождите 2 секунды перед следующим сообщением.")
        return
    
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, "❌ Пользователь не найден.")
        return
    
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, "❌ Этот пользователь отключил получение сообщений.")
        return
    
    # Сохраняем цель для ответа
    user_reply_targets[clicker_id] = target_id
    
    db.increment_stat(target_id, 'link_clicks')
    
    bot.send_message(
        clicker_id,
        f"""💌 <b>Пиши анонимное сообщение для</b> <i>{target_user['first_name']}</i>!

<b>📝 Можно отправить:</b>
• Текст ✍️
• Фото 📸
• Видео 🎬
• Голосовое 🎤
• Стикер 😜
• GIF 🎞️
• Документ 📎

<i>💭 Сообщение будет <b>полностью анонимным</b>!
Получатель не узнает, кто его отправил 👻</i>""",
        reply_markup=cancel_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработка inline кнопок"""
    user_id = call.from_user.id
    data = call.data
    
    try:
        if data == "ignore":
            bot.answer_callback_query(call.id, "✅ Сообщение проигнорировано")
            return
        
        elif data == "refresh_logs":
            if user_id == ADMIN_ID:
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, "✅ Логи обновлены")
            return
        
        elif data == "toggle_text":
            if user_id == ADMIN_ID:
                current = admin_log_settings.get(user_id, {}).get('show_text', True)
                admin_log_settings[user_id] = {'show_text': not current}
                show_message_logs(admin_id=user_id)
                status = "скрыт" if not current else "показан"
                bot.answer_callback_query(call.id, f"✅ Текст {status}")
            return
        
        elif data.startswith("reply_"):
            target_id = int(data.split("_")[1])
            user_reply_targets[user_id] = target_id
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=call.message.text + "\n\n💌 <i>Отправь ответ анонимно!</i>"
            )
            bot.answer_callback_query(call.id)
        
        elif data.startswith("admin_block_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Только для админа")
                return
            
            target_id = int(data.split("_")[2])
            db.block_user(target_id, ADMIN_ID, "Через админ-панель")
            db.add_admin_log("block", user_id, target_id, "Через админ-панель")
            bot.answer_callback_query(call.id, "✅ Пользователь заблокирован")
            
            # Обновляем сообщение
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + "\n\n🚫 <b>Пользователь заблокирован</b>"
                )
            except:
                pass
        
        elif data.startswith("admin_msg_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Только для админа")
                return
            
            target_id = int(data.split("_")[2])
            admin_modes[user_id] = f'direct_msg_{target_id}'
            
            bot.send_message(
                user_id,
                f"""✉️ <b>Отправь сообщение для пользователя</b> <code>{target_id}</code>

<i>Сообщение придёт как от бота 🤖
Можно отправить текст, фото или видео.</i>""",
                reply_markup=cancel_keyboard()
            )
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_reply_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Только для админа")
                return
            
            ticket_id = int(data.split("_")[2])
            admin_modes[user_id] = f'support_reply_{ticket_id}'
            
            bot.send_message(
                user_id,
                f"""📝 <b>Отправь ответ на тикет #{ticket_id}</b>

<i>Ответ отправится пользователю.</i>""",
                reply_markup=cancel_keyboard()
            )
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_close_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Только для админа")
                return
            
            ticket_id = int(data.split("_")[2])
            db.update_support_ticket(ticket_id, user_id, "Закрыто без ответа", "closed")
            db.add_admin_log("ticket_close", user_id, None, f"Тикет #{ticket_id}")
            
            bot.answer_callback_query(call.id, "✅ Тикет закрыт")
            
            # Обновляем сообщение
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + "\n\n✅ <b>Тикет закрыт</b>"
                )
            except:
                pass
        
        elif data.startswith("admin_user_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ Только для админа")
                return
            
            target_id = int(data.split("_")[2])
            find_user_info(admin_id=user_id, query=str(target_id))
            bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Ошибка в callback: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")

# ====== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ======
@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    # Пропускаем команды
    if message.text and message.text.startswith('/'):
        return
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, "🚫 Вы заблокированы в этом боте.")
        return
    
    # Обновляем активность
    db.update_last_active(user_id)
    
    # Обработка отмены
    if text == "❌ Отмена":
        clear_user_state(user_id)
        is_admin = user_id == ADMIN_ID
        bot.send_message(user_id, "❌ Действие отменено", reply_markup=main_keyboard(is_admin))
        return
    
    # Проверяем лимит сообщений
    if not check_daily_limit(user_id):
        bot.send_message(
            user_id,
            "⚠️ <b>Достигнут дневной лимит сообщений!</b>\n\n"
            "<i>Вы отправили максимальное количество сообщений за сегодня.\n"
            "Лимит сбросится через 24 часа ⏰</i>",
            reply_markup=main_keyboard(user_id == ADMIN_ID)
        )
        return
    
    # Админ отправляет сообщение пользователю
    if user_id == ADMIN_ID and user_id in admin_modes:
        mode = admin_modes[user_id]
        
        if mode.startswith('direct_msg_'):
            target_id = int(mode.split('_')[2])
            send_direct_admin_message(message, target_id)
            if user_id in admin_modes:
                del admin_modes[user_id]
            return
        
        elif mode.startswith('support_reply_'):
            ticket_id = int(mode.split('_')[2])
            reply_to_support_ticket(message, ticket_id)
            if user_id in admin_modes:
                del admin_modes[user_id]
            return
    
    # Обработка поддержки
    if text == "🆘 Поддержка":
        handle_support_request(message)
        return
    
    # Проверяем ожидание (отправка анонимки)
    if user_id in user_reply_targets:
        target_id = user_reply_targets[user_id]
        send_anonymous_message(user_id, target_id, message)
        # Не удаляем target_id, чтобы можно было отправлять несколько сообщений
        return
    
    # Проверяем, пишет ли пользователь в поддержку
    if user_id in admin_modes and admin_modes[user_id] == 'support':
        create_support_ticket(message)
        if user_id in admin_modes:
            del admin_modes[user_id]
        return
    
    # Обработка кнопок главного меню
    if message_type == 'text':
        handle_text_button(user_id, text)

def clear_user_state(user_id):
    """Очистка состояний пользователя"""
    if user_id in user_reply_targets:
        del user_reply_targets[user_id]
    if user_id in admin_modes:
        del admin_modes[user_id]

def handle_text_button(user_id, text):
    is_admin = user_id == ADMIN_ID
    
    if text == "📩 Моя ссылка":
        link = generate_link(user_id)
        bot.send_message(
            user_id,
            f"""🔗 <b>Твоя уникальная ссылка для анонимок:</b>

<code>{link}</code>

<i>📤 Поделись с друзьями в:
• Чатах 💬
• Соцсетях 🌐
• Сторис 📲

🎭 Каждый переход — новый анонимный отправитель!
🔥 Чем больше делишься, тем больше тайн узнаёшь 😏</i>""",
            reply_markup=main_keyboard(is_admin)
        )
    
    elif text == "👤 Профиль":
        show_profile(user_id)
    
    elif text == "⚙️ Настройки":
        bot.send_message(
            user_id,
            "⚙️ <b>Настройки</b>\n\n"
            "<i>Настрой бота под себя:</i>",
            reply_markup=settings_keyboard()
        )
    
    elif text == "📱 QR-код":
        generate_qr_code(user_id)
    
    elif text == "ℹ️ Помощь":
        show_help(user_id)
    
    elif text == "🔔 Вкл. сообщения":
        db.set_receive_messages(user_id, True)
        bot.send_message(
            user_id, 
            "✅ <b>Приём анонимных сообщений включён!</b>\n\n"
            "<i>Теперь друзья могут отправлять тебе тайные послания 🔮</i>",
            reply_markup=settings_keyboard()
        )
    
    elif text == "🔕 Выкл. сообщения":
        db.set_receive_messages(user_id, False)
        bot.send_message(
            user_id, 
            "✅ <b>Приём анонимных сообщений отключён!</b>\n\n"
            "<i>Ты не будешь получать новые анонимки 🔒\n"
            "Можешь включить в любой момент ⚡</i>",
            reply_markup=settings_keyboard()
        )
    
    elif text == "🌐 Язык":
        show_language_selection(user_id)
    
    elif text == "🎨 Тема":
        show_theme_selection(user_id)
    
    elif text == "⬅️ Назад":
        bot.send_message(user_id, "Главное меню:", reply_markup=main_keyboard(is_admin))
    
    # Админские команды
    elif is_admin:
        handle_admin_command(user_id, text)

def show_profile(user_id):
    """Показать профиль пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ <b>Профиль не найден.</b>\n\n<i>Попробуйте начать с команды /start</i>",
                        reply_markup=main_keyboard(user_id == ADMIN_ID))
        return
    
    stats = db.get_user_messages_stats(user_id)
    achievements = db.get_user_achievements(user_id)
    today_messages = db.get_today_message_count(user_id)
    
    # Разблокируем достижения
    if stats['messages_sent'] >= 1 and len([a for a in achievements if a['achievement_id'] == 'first_message']) == 0:
        db.unlock_achievement(user_id, 'first_message')
        achievements = db.get_user_achievements(user_id)
    
    if stats['messages_received'] >= 10 and len([a for a in achievements if a['achievement_id'] == 'popular']) == 0:
        db.unlock_achievement(user_id, 'popular')
        achievements = db.get_user_achievements(user_id)
    
    profile_text = f"""👤 <b>Твой профиль</b>

<b>📊 Идентификация:</b>
├ ID: <code>{user['user_id']}</code>
├ Имя: <b>{user['first_name']}</b>
└ Юзернейм: {f'@{user['username']}' if user['username'] else '❌ отсутствует'}

<b>📈 Статистика:</b>
├ 📨 Получено: <b>{user['messages_received']}</b>
├ 📤 Отправлено: <b>{user['messages_sent']}</b>
├ 🔗 Переходов: <b>{user['link_clicks']}</b>
├ 📝 Сегодня: <b>{today_messages}/{MAX_MESSAGES_PER_DAY}</b>
└ 🎮 Уровень: <b>{user['level']}</b> (EXP: {user['exp']})

<b>⚙️ Настройки:</b>
├ Приём сообщений: {"✅ Включён" if user['receive_messages'] else "❌ Выключен"}
├ Тема: <b>{user['theme'].capitalize()}</b>
├ Язык: <b>{user['language'].upper()}</b>
└ Активность: {format_time(user['last_active'])}

<b>🏆 Достижения ({len(achievements)}):</b>"""
    
    if achievements:
        for ach in achievements[:5]:  # Показываем только 5 последних
            profile_text += f"\n├ {get_achievement_emoji(ach['achievement_id'])} {get_achievement_name(ach['achievement_id'])}"
        if len(achievements) > 5:
            profile_text += f"\n└ ... и ещё {len(achievements) - 5}"
    else:
        profile_text += "\n└ <i>Пока нет достижений</i>"
    
    profile_text += f"\n\n<b>🔗 Твоя ссылка:</b>\n<code>{generate_link(user_id)}</code>"
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, profile_text, reply_markup=main_keyboard(is_admin))

def get_achievement_emoji(achievement_id):
    emoji_map = {
        'first_join': '🎯',
        'first_message': '💌',
        'popular': '🔥',
        'active_user': '⚡',
        'link_master': '🔗'
    }
    return emoji_map.get(achievement_id, '🏆')

def get_achievement_name(achievement_id):
    name_map = {
        'first_join': 'Первый шаг',
        'first_message': 'Анонимный отправитель',
        'popular': 'Популярность',
        'active_user': 'Активный пользователь',
        'link_master': 'Мастер ссылок'
    }
    return name_map.get(achievement_id, 'Достижение')

def send_anonymous_message(sender_id, receiver_id, message):
    """Отправка анонимного сообщения"""
    try:
        if not check_spam(sender_id):
            bot.send_message(sender_id, "⏳ Подождите 2 секунды перед следующим сообщением.")
            return
        
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, "❌ Этот пользователь отключил получение сообщений.")
            return
        
        # Получаем информацию об отправителе
        sender = db.get_user(sender_id)
        
        # Сохраняем сообщение
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
        
        message_id = db.save_message(
            sender_id, receiver_id, 
            message_type, 
            message.text or message.caption or "", 
            file_id, file_unique_id
        )
        
        # Формируем сообщение для получателя
        caption = f"""📨 <b>Ты получил анонимное сообщение!</b>

<i>💭 Кто-то отправил тебе тайное послание...</i>

"""
        
        message_text = message.text or message.caption or ""
        if message_text:
            caption += f"💬 <b>Текст:</b>\n<code>{message_text}</code>\n\n"
        
        caption += f"<i>🎭 Отправитель останется неизвестным...</i>"
        
        # Отправляем получателю
        try:
            if message_type == 'text':
                msg = bot.send_message(receiver_id, caption, reply_markup=get_message_reply_keyboard(sender_id))
            elif message_type == 'photo':
                msg = bot.send_photo(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
            elif message_type == 'video':
                msg = bot.send_video(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
            elif message_type == 'audio':
                msg = bot.send_audio(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
            elif message_type == 'voice':
                msg = bot.send_voice(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
            elif message_type == 'document':
                msg = bot.send_document(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
            elif message_type == 'sticker':
                # Для стикеров отдельно отправляем текст и стикер
                bot.send_message(receiver_id, caption)
                msg = bot.send_sticker(receiver_id, file_id, reply_markup=get_message_reply_keyboard(sender_id))
            
            # Разблокируем достижение для отправителя
            if message_type != 'sticker':  # Для стикеров не разблокируем
                db.unlock_achievement(sender_id, 'first_message')
            
        except ApiException as e:
            if e.error_code == 403:
                bot.send_message(sender_id, "❌ Пользователь заблокировал бота.")
                return
            else:
                raise
        
        # Обновляем статистику
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Добавляем опыт
        add_user_exp(sender_id, 5)
        add_user_exp(receiver_id, 2)
        
        # Уведомляем отправителя
        bot.send_message(
            sender_id,
            f"""✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Получатель: <b>{receiver['first_name']}</b>
🔒 Твоя личность: <b>скрыта</b>
💭 Сообщение доставлено успешно!</i>

<b>Хочешь отправить ещё?</b>
Просто продолжай писать ✍️""",
            reply_markup=cancel_keyboard()
        )
        
        # Логируем для админа (если включены уведомления)
        if db.get_setting('notifications_enabled', '1') == '1':
            log_to_admin_channel(sender_id, receiver_id, message_type, message_text, file_id)
        
        # Добавляем лог для админа
        db.add_admin_log("anonymous_message", sender_id, receiver_id, 
                        f"{message_type}: {message_text[:50] if message_text else 'без текста'}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        bot.send_message(
            sender_id,
            "❌ <b>Ошибка при отправке сообщения.</b>\n\n"
            "<i>Попробуй ещё раз или обратись в поддержку 🆘</i>"
        )

def add_user_exp(user_id, exp):
    """Добавить опыт пользователю"""
    user = db.get_user(user_id)
    if not user:
        return
    
    with db.get_connection() as conn:
        c = conn.cursor()
        new_exp = user['exp'] + exp
        new_level = user['level']
        
        # Проверяем повышение уровня (каждые 100 опыта)
        if new_exp >= new_level * 100:
            new_level += 1
            new_exp = new_exp % (new_level * 100)
            
            # Уведомляем пользователя о новом уровне
            try:
                bot.send_message(user_id, f"🎉 <b>Поздравляем! Вы достигли {new_level} уровня!</b>")
            except:
                pass
        
        c.execute('UPDATE users SET exp = ?, level = ? WHERE user_id = ?', 
                 (new_exp, new_level, user_id))

def log_to_admin_channel(sender_id, receiver_id, message_type, message_text, file_id):
    """Отправить лог в канал админа"""
    if not CHANNEL:
        return
    
    try:
        sender = db.get_user(sender_id)
        receiver = db.get_user(receiver_id)
        
        log_msg = f"""📨 <b>Новое анонимное сообщение</b>

👤 От: <code>{sender_id}</code> ({sender['first_name'] if sender else '?'})
🎯 Кому: <code>{receiver_id}</code> ({receiver['first_name'] if receiver else '?'})
📝 Тип: {message_type}"""
        
        if message_text:
            log_msg += f"\n💬 Текст: <code>{message_text[:100]}</code>"
        
        if file_id and message_type in ['photo', 'video']:
            if message_type == 'photo':
                bot.send_photo(CHANNEL, file_id, caption=log_msg)
            elif message_type == 'video':
                bot.send_video(CHANNEL, file_id, caption=log_msg)
        else:
            bot.send_message(CHANNEL, log_msg)
            
    except Exception as e:
        logger.error(f"Ошибка отправки в канал: {e}")

def send_direct_admin_message(message, target_user_id):
    """Админ отправляет сообщение пользователю напрямую"""
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
        
        # Отправляем пользователю
        user_message = f"""📢 <b>Важное уведомление от администрации</b>

{message_text}

<i>С уважением, команда Anony SMS 🤖</i>"""
        
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
        
        # Уведомляем админа
        bot.send_message(
            ADMIN_ID,
            f"""✅ <b>Сообщение отправлено</b>

👤 Пользователь: <code>{target_user_id}</code>
📝 Тип: {message_type}""",
            reply_markup=admin_keyboard()
        )
        
        # Добавляем лог
        db.add_admin_log("direct_message", ADMIN_ID, target_user_id, 
                        f"{message_type}: {message_text[:50] if message_text else 'без текста'}")
        
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка при отправке сообщения")

def handle_support_request(message):
    """Обработка запроса в поддержку"""
    user_id = message.from_user.id
    
    bot.send_message(
        user_id,
        """🆘 <b>Служба поддержки</b>

<i>Опишите вашу проблему как можно подробнее 💭
Мы постараемся ответить в кратчайшие сроки ⏰</i>

<b>📎 Что можно отправить:</b>
• Текстовое описание проблемы ✍️
• Скриншот ошибки 📸
• Видео с багом 🎬
• Любой медиафайл 📎

<b>⚠️ Что НЕ нужно отправлять:</b>
• Личные данные 🔒
• Оскорбления 🚫
• Спам 📛

<i>Опиши проблему и нажми отправить 👇</i>""",
        reply_markup=cancel_keyboard()
    )
    
    # Устанавливаем режим поддержки
    admin_modes[user_id] = 'support'

def create_support_ticket(message):
    """Создание тикета поддержки"""
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    if not text and message_type == 'text':
        bot.send_message(user_id, "❌ Пожалуйста, опишите вашу проблему.")
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
        
        # Уведомляем пользователя
        bot.send_message(
            user_id,
            f"""✅ <b>Запрос в поддержку отправлен!</b>

<i>Ваш тикет: <b>#{ticket_id}</b>
Мы ответим вам в ближайшее время ⏰</i>""",
            reply_markup=main_keyboard(user_id == ADMIN_ID)
        )
        
        # Отправляем уведомление админу
        notify_admin_about_ticket(ticket_id, user_id, message_type, text, file_id)
        
        # Добавляем лог
        db.add_admin_log("support_ticket", user_id, None, f"Тикет #{ticket_id}")
        
    except Exception as e:
        logger.error(f"Ошибка создания тикета: {e}")
        bot.send_message(user_id, "❌ Ошибка при создании запроса в поддержку.")

def notify_admin_about_ticket(ticket_id, user_id, message_type, text, file_id):
    """Уведомление админа о новом тикете"""
    user = db.get_user(user_id)
    
    notification = f"""🆘 <b>Новый тикет поддержки</b>

<b>📋 Тикет:</b> #{ticket_id}
<b>👤 Пользователь:</b> <code>{user_id}</code>
<b>📝 Имя:</b> {user['first_name'] if user else 'Неизвестно'}
<b>📱 Юзернейм:</b> {f'@{user['username']}' if user and user['username'] else '❌ отсутствует'}
<b>📅 Время:</b> {format_time(int(time.time()))}

<b>📝 Тип:</b> {message_type}"""
    
    if text:
        notification += f"\n<b>💬 Сообщение:</b>\n<code>{text[:200]}</code>"
    
    notification += f"\n\n<i>Для ответа нажмите кнопку ниже 👇</i>"
    
    try:
        if file_id and message_type in ['photo', 'video']:
            if message_type == 'photo':
                msg = bot.send_photo(ADMIN_ID, file_id, caption=notification, 
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id))
            elif message_type == 'video':
                msg = bot.send_video(ADMIN_ID, file_id, caption=notification,
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id))
        else:
            msg = bot.send_message(ADMIN_ID, notification,
                                 reply_markup=get_admin_ticket_keyboard(ticket_id, user_id))
        
        # Также отправляем в канал, если указан
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
        logger.error(f"Ошибка уведомления админа: {e}")

def reply_to_support_ticket(message, ticket_id):
    """Ответ на тикет поддержки"""
    try:
        # Получаем информацию о тикете
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
            bot.send_message(ADMIN_ID, "❌ Пожалуйста, введите текст ответа.")
            return
        
        file_id = None
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        
        # Обновляем тикет в БД
        db.update_support_ticket(ticket_id, ADMIN_ID, reply_text, 'answered')
        
        # Отправляем ответ пользователю
        user_reply = f"""🆘 <b>Ответ от поддержки</b>

<i>Спасибо за обращение! Мы рассмотрели ваш запрос 🤝</i>

<b>📋 Ваше сообщение:</b>
<code>{user_message[:500]}</code>

<b>💬 Наш ответ:</b>
<code>{reply_text}</code>

<i>Если проблема не решена — создайте новый тикет 💭</i>"""
        
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
        
        # Уведомляем админа
        bot.send_message(
            ADMIN_ID,
            f"""✅ <b>Ответ на тикет #{ticket_id} отправлен</b>

👤 Пользователь: <code>{user_id}</code>
📝 Тип ответа: {message_type}""",
            reply_markup=admin_keyboard()
        )
        
        # Добавляем лог
        db.add_admin_log("support_reply", ADMIN_ID, user_id, f"Тикет #{ticket_id}")
        
    except Exception as e:
        logger.error(f"Ошибка ответа на тикет: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка при отправке ответа.")

def generate_qr_code(user_id):
    """Генерация QR-кода"""
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.send_photo(
            user_id,
            photo=bio,
            caption=f"""📱 <b>Твой персональный QR-код</b>

<i>Сканируй и отправляй анонимные сообщения мгновенно! ⚡</i>

<b>🔗 Ссылка:</b>
<code>{link}</code>

<b>💡 Как использовать:</b>
1. Покажи друзьям 📲
2. Пусть отсканируют камерой 📸
3. Отправляют анонимки сразу! 🎭

<i>Быстро, удобно, анонимно! 😉</i>""",
            reply_markup=main_keyboard(user_id == ADMIN_ID)
        )
    except Exception as e:
        logger.error(f"Ошибка генерации QR: {e}")
        bot.send_message(user_id, "❌ Ошибка при генерации QR-кода.")

def show_help(user_id):
    """Показать справку"""
    help_text = """ℹ️ <b>Полное руководство по Anony SMS</b>

<b>🎯 Что это такое?</b>
Anony SMS — это бот для <b>полностью анонимных</b> сообщений! 
Никто не узнает, кто отправил послание 👻

<b>📨 КАК ПОЛУЧАТЬ сообщения:</b>
1. Нажми «📩 Моя ссылка»
2. Скопируй свою уникальную ссылку
3. Поделись с друзьями в:
   • Телеграм-чатах 💬
   • Социальных сетях 🌐
   • Сторис Instagram 📱
4. Жди анонимные сообщения! 💌

<b>✉️ КАК ОТПРАВЛЯТЬ сообщения:</b>
1. Перейди по чужой ссылке
2. Напиши сообщение (текст, фото, видео, голосовое)
3. Отправь — получатель не узнает твою личность! 🎭

<b>📎 ЧТО МОЖНО ОТПРАВИТЬ:</b>
✅ Текстовые сообщения ✍️
✅ Фотографии 📸
✅ Видео 🎬
✅ Голосовые сообщения 🎤
✅ Стикеры 😜
✅ GIF анимации 🎞️
✅ Документы 📎

<b>⚙️ НАСТРОЙКИ:</b>
• Включить/выключить приём сообщений
• Просмотр статистики
• Генерация QR-кода
• Смена темы оформления
• Выбор языка

<b>🔒 БЕЗОПАСНОСТЬ:</b>
• <b>Полная анонимность</b> — мы не храним данные отправителей
• Возможность блокировки нежелательных сообщений
• Конфиденциальность гарантирована 🔐

<b>🆘 ПОДДЕРЖКА:</b>
Возникли проблемы? Нажми «🆘 Поддержка» и опиши ситуацию!
Мы поможем в кратчайшие сроки ⚡

<b>👇 Начни сейчас — открой мир тайных посланий!</b> 🚀"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, help_text, reply_markup=main_keyboard(is_admin))

def show_language_selection(user_id):
    """Показать выбор языка"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en"),
        types.InlineKeyboardButton("🇪🇸 Español", callback_data="lang_es"),
        types.InlineKeyboardButton("🇩🇪 Deutsch", callback_data="lang_de")
    )
    
    bot.send_message(
        user_id,
        "🌐 <b>Выберите язык</b>\n\n"
        "<i>Выбор языка изменит интерфейс бота.</i>",
        reply_markup=keyboard
    )

def show_theme_selection(user_id):
    """Показать выбор темы"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🎨 Classic", callback_data="theme_classic"),
        types.InlineKeyboardButton("🌙 Dark", callback_data="theme_dark"),
        types.InlineKeyboardButton("💖 Pink", callback_data="theme_pink"),
        types.InlineKeyboardButton("🌊 Ocean", callback_data="theme_ocean"),
        types.InlineKeyboardButton("🍀 Nature", callback_data="theme_nature"),
        types.InlineKeyboardButton("🔥 Fire", callback_data="theme_fire")
    )
    
    bot.send_message(
        user_id,
        "🎨 <b>Выберите тему оформления</b>\n\n"
        "<i>Тема изменит внешний вид бота.</i>",
        reply_markup=keyboard
    )

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id, text):
    """Обработка админских команд"""
    
    if text == "📊 Статистика":
        show_admin_stats(admin_id)
    
    elif text == "📢 Рассылка":
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(
            admin_id,
            """📢 <b>Создание рассылки</b>

<i>Отправь сообщение которое будет отправлено всем пользователям.</i>

<b>📎 Можно отправить:</b>
• Текст с HTML-разметкой ✍️
• Фото с подписью 📸
• Видео с описанием 🎬
• Документ с комментарием 📎
• Стикер 😜

<b>⚠️ Внимание:</b>
Рассылка отправится всем пользователям, кроме заблокировавших бота.""",
            reply_markup=cancel_keyboard()
        )
    
    elif text == "👥 Пользователи":
        show_users_stats(admin_id)
    
    elif text == "🔍 Найти":
        admin_modes[admin_id] = 'find_user'
        bot.send_message(
            admin_id,
            "🔍 <b>Поиск пользователя</b>\n\n"
            "<i>Введите ID пользователя или юзернейм (без @):</i>\n\n"
            "<b>Примеры:</b>\n"
            "<code>123456789</code> - поиск по ID\n"
            "<code>username</code> - поиск по юзернейму",
            reply_markup=cancel_keyboard()
        )
    
    elif text == "📋 Логи":
        show_message_logs(admin_id)
    
    elif text == "🆘 Тикеты":
        show_support_tickets(admin_id)
    
    elif text == "⚙️ Настройки":
        show_admin_settings(admin_id)
    
    elif text == "⬅️ Назад":
        bot.send_message(admin_id, "Главное меню:", reply_markup=main_keyboard(True))
    
    # Обработка ввода в режиме админа
    elif admin_id in admin_modes:
        mode = admin_modes[admin_id]
        
        if mode == 'broadcast':
            start_broadcast(admin_id, text)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'find_user':
            find_user_info(admin_id, text)
            if admin_id in admin_modes:
                del admin_modes[admin_id]

def show_admin_stats(admin_id):
    """Показать статистику для админа"""
    stats = db.get_admin_stats()
    today_active = db.get_today_active_users()
    blocked_count = db.get_blocked_users_count()
    
    stats_text = f"""👑 <b>Статистика бота</b>

<b>📊 ОСНОВНЫЕ МЕТРИКИ:</b>
├ Всего пользователей: <b>{stats['total_users']}</b>
├ Активных сегодня: <b>{today_active}</b>
├ Всего сообщений: <b>{stats['total_messages']}</b>
├ Сообщений за 24ч: <b>{stats['messages_24h']}</b>
├ Новых за 24ч: <b>{stats['new_users_24h']}</b>
├ Заблокированных: <b>{blocked_count}</b>
└ Открытых тикетов: <b>{stats['open_tickets']}</b>

<b>📈 АКТИВНОСТЬ:</b>
<i>Бот работает стабильно и принимает сообщения ⚡</i>

<b>💾 БАЗА ДАННЫХ:</b>
<i>Все функции работают исправно ✅</i>"""
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard())

def start_broadcast(admin_id, text):
    """Начать рассылку"""
    try:
        # Если это не текст, а медиа
        if admin_id in admin_modes and admin_modes[admin_id] == 'broadcast':
            # Сохраняем сообщение для рассылки
            broadcast_message = text
            admin_modes[admin_id] = ('broadcast_msg', broadcast_message)
            bot.send_message(admin_id, "✅ Сообщение сохранено. Начинаю рассылку...")
            
            # Запускаем рассылку в отдельном потоке
            threading.Thread(target=process_broadcast, args=(admin_id, broadcast_message)).start()
            return
        
        # Если это медиафайл
        broadcast_message = text
        threading.Thread(target=process_broadcast, args=(admin_id, broadcast_message)).start()
        
    except Exception as e:
        logger.error(f"Ошибка начала рассылки: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard())

def process_broadcast(admin_id, message):
    """Обработка рассылки в отдельном потоке"""
    try:
        users = db.get_all_users()
        total = db.get_all_users_count()
        sent = 0
        failed = 0
        blocked = 0
        
        progress_msg = bot.send_message(admin_id, f"⏳ <b>Начинаю рассылку...</b>\n\nВсего пользователей: {total}")
        
        for i, user in enumerate(users):
            try:
                # Проверяем, не заблокирован ли пользователь
                if db.is_user_blocked(user['user_id']):
                    blocked += 1
                    continue
                
                # Отправляем сообщение
                if isinstance(message, types.Message):
                    # Это медиафайл
                    send_broadcast_media(user['user_id'], message)
                else:
                    # Это текст
                    bot.send_message(user['user_id'], message, parse_mode="HTML")
                
                sent += 1
                
                # Обновляем прогресс каждые 20 пользователей
                if sent % 20 == 0:
                    try:
                        bot.edit_message_text(
                            chat_id=admin_id,
                            message_id=progress_msg.message_id,
                            text=f"⏳ <b>Рассылка в процессе...</b>\n\nОтправлено: {sent}/{total}"
                        )
                    except:
                        pass
                
                # Небольшая задержка для антифлуда
                time.sleep(0.05)
                
            except ApiException as e:
                if e.error_code == 403:
                    # Пользователь заблокировал бота
                    failed += 1
                else:
                    logger.error(f"Ошибка при рассылке: {e}")
                    failed += 1
            except Exception as e:
                logger.error(f"Ошибка при рассылке: {e}")
                failed += 1
        
        # Итоговый отчет
        report = f"""✅ <b>Рассылка завершена!</b>

<b>📊 РЕЗУЛЬТАТЫ:</b>
├ Всего пользователей: <b>{total}</b>
├ Успешно отправлено: <b>{sent}</b>
├ Не удалось отправить: <b>{failed}</b>
└ Пропущено (заблок.): <b>{blocked}</b>

<i>💡 Недоставленные сообщения — пользователи, которые заблокировали бота.</i>"""
        
        try:
            bot.edit_message_text(
                chat_id=admin_id,
                message_id=progress_msg.message_id,
                text=report
            )
        except:
            bot.send_message(admin_id, report)
        
        # Добавляем лог
        db.add_admin_log("broadcast", admin_id, None, f"Отправлено: {sent}/{total}")
        
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        bot.send_message(admin_id, f"❌ Ошибка при рассылке: {e}")

def send_broadcast_media(user_id, message):
    """Отправить медиа в рассылке"""
    message_type = message.content_type
    
    if message_type == 'photo':
        bot.send_photo(user_id, message.photo[-1].file_id, 
                      caption=message.caption or "", parse_mode="HTML")
    elif message_type == 'video':
        bot.send_video(user_id, message.video.file_id,
                      caption=message.caption or "", parse_mode="HTML")
    elif message_type == 'document':
        bot.send_document(user_id, message.document.file_id,
                         caption=message.caption or "", parse_mode="HTML")
    elif message_type == 'sticker':
        bot.send_sticker(user_id, message.sticker.file_id)
    elif message_type == 'text':
        bot.send_message(user_id, message.text, parse_mode="HTML")

def show_users_stats(admin_id):
    """Показать статистику пользователей"""
    stats = db.get_admin_stats()
    today_active = db.get_today_active_users()
    blocked_count = db.get_blocked_users_count()
    
    users_stats = f"""👥 <b>Статистика пользователей</b>

<b>📊 ОБЩАЯ:</b>
├ Всего пользователей: <b>{stats['total_users']}</b>
├ Активных сегодня: <b>{today_active}</b>
├ Заблокированных: <b>{blocked_count}</b>
└ Новых за 24ч: <b>{stats['new_users_24h']}</b>

<b>📈 АКТИВНОСТЬ:</b>
├ Всего сообщений: <b>{stats['total_messages']}</b>
└ За 24 часа: <b>{stats['messages_24h']}</b>

<b>🆘 ПОДДЕРЖКА:</b>
└ Открытых тикетов: <b>{stats['open_tickets']}</b>

<i>Для поиска конкретного пользователя используйте "🔍 Найти"</i>"""
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_users"))
    
    bot.send_message(admin_id, users_stats, reply_markup=keyboard)

def find_user_info(admin_id, query):
    """Найти информацию о пользователе"""
    try:
        user = None
        
        if query.isdigit():
            # Поиск по ID
            user_id = int(query)
            user = db.get_user(user_id)
        else:
            # Поиск по юзернейму (без @)
            username = query.lstrip('@')
            user = db.get_user_by_username(username)
        
        if not user:
            bot.send_message(admin_id, f"❌ Пользователь не найден: {query}", reply_markup=admin_keyboard())
            return
        
        # Получаем статистику сообщений
        stats = db.get_user_messages_stats(user['user_id'])
        is_blocked = db.is_user_blocked(user['user_id'])
        achievements = db.get_user_achievements(user['user_id'])
        today_messages = db.get_today_message_count(user['user_id'])
        
        user_info = f"""🔍 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

<b>👤 ОСНОВНЫЕ ДАННЫЕ:</b>
├ ID: <code>{user['user_id']}</code>
├ Имя: <b>{user['first_name']}</b>
├ Юзернейм: {f'@{user['username']}' if user['username'] else '❌ отсутствует'}
├ Зарегистрирован: {format_time(user['created_at'])}
├ Последняя активность: {format_time(user['last_active'])}
└ Премиум: {"✅ До " + format_time(user['premium_until']) if user['premium_until'] > time.time() else "❌ Нет"}

<b>📊 СТАТИСТИКА:</b>
├ 📨 Получено сообщений: <b>{user['messages_received']}</b>
├ 📤 Отправлено сообщений: <b>{user['messages_sent']}</b>
├ 🔗 Переходов по ссылке: <b>{user['link_clicks']}</b>
├ 📝 Сегодня отправил: <b>{today_messages}</b>
├ ⚙️ Приём сообщений: {"✅ Включён" if user['receive_messages'] else "❌ Выключен"}
└ 🎮 Уровень: <b>{user['level']}</b> (EXP: {user['exp']})

<b>🔤 ТОП-5 СЛОВ:</b>"""
        
        if stats['top_words']:
            for word, count in stats['top_words']:
                user_info += f"\n├ '{word}': {count} раз"
            user_info += "\n└"
        else:
            user_info += "\n└ <i>Нет данных о словах</i>"
        
        user_info += f"\n\n<b>😊 ТОП-5 ЭМОДЗИ:</b>"
        if stats['top_emojis']:
            for emoji, count in stats['top_emojis']:
                user_info += f"\n├ {emoji}: {count} раз"
            user_info += "\n└"
        else:
            user_info += "\n└ <i>Нет данных об эмодзи</i>"
        
        user_info += f"\n\n<b>🏆 ДОСТИЖЕНИЯ ({len(achievements)}):</b>"
        if achievements:
            for ach in achievements[:3]:
                user_info += f"\n├ {get_achievement_emoji(ach['achievement_id'])} {get_achievement_name(ach['achievement_id'])}"
            if len(achievements) > 3:
                user_info += f"\n└ ... и ещё {len(achievements) - 3}"
        else:
            user_info += "\n└ <i>Нет достижений</i>"
        
        user_info += f"\n\n<b>🚫 СТАТУС:</b> {'🔴 ЗАБЛОКИРОВАН' if is_blocked else '🟢 АКТИВЕН'}"
        
        bot.send_message(admin_id, user_info, reply_markup=get_admin_user_keyboard(user['user_id']))
        
    except Exception as e:
        logger.error(f"Ошибка поиска пользователя: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard())

def show_message_logs(admin_id):
    """Показать логи сообщений"""
    show_text = admin_log_settings.get(admin_id, {}).get('show_text', True)
    messages = db.get_recent_messages(limit=10, include_text=show_text)
    
    if not messages:
        bot.send_message(admin_id, "📋 <b>Логи сообщений пусты</b>\n\n<i>Пока нет отправленных сообщений.</i>", 
                        reply_markup=get_admin_log_keyboard())
        return
    
    logs_text = "📋 <b>Последние 10 анонимных сообщений:</b>\n\n"
    
    for i, msg in enumerate(messages, 1):
        sender_name = msg.get('sender_name', 'Неизвестно')
        receiver_name = msg.get('receiver_name', 'Неизвестно')
        sender_username = f" (@{msg['sender_username']})" if msg.get('sender_username') else ""
        receiver_username = f" (@{msg['receiver_username']})" if msg.get('receiver_username') else ""
        
        logs_text += f"<b>{i}. {format_time(msg['timestamp'])}</b>\n"
        logs_text += f"   👤 От: <code>{msg['sender_id']}</code> - {sender_name}{sender_username}\n"
        logs_text += f"   🎯 Кому: <code>{msg['receiver_id']}</code> - {receiver_name}{receiver_username}\n"
        logs_text += f"   📝 Тип: {msg['message_type']}\n"
        
        if msg['text']:
            logs_text += f"   💬 Текст: <code>{msg['text']}</code>\n"
        
        logs_text += "\n"
    
    bot.send_message(admin_id, logs_text, reply_markup=get_admin_log_keyboard())

def show_support_tickets(admin_id):
    """Показать тикеты поддержки"""
    tickets = db.get_open_support_tickets()
    
    if not tickets:
        bot.send_message(admin_id, "🆘 <b>Открытых тикетов нет</b>\n\n<i>Все обращения обработаны ✅</i>",
                        reply_markup=admin_keyboard())
        return
    
    tickets_text = f"🆘 <b>Открытые тикеты ({len(tickets)}):</b>\n\n"
    
    for i, ticket in enumerate(tickets, 1):
        tickets_text += f"<b>{i}. Тикет #{ticket['id']}</b>\n"
        tickets_text += f"   👤 Пользователь: <code>{ticket['user_id']}</code> - {ticket['first_name']}\n"
        tickets_text += f"   📱 Юзернейм: {f'@{ticket['username']}' if ticket['username'] else '❌ отсутствует'}\n"
        tickets_text += f"   📅 Создан: {format_time(ticket['created_at'])}\n"
        
        if ticket['message']:
            preview = ticket['message'][:100] + "..." if len(ticket['message']) > 100 else ticket['message']
            tickets_text += f"   💬 Сообщение: <code>{preview}</code>\n"
        
        tickets_text += f"   📝 Тип: {ticket['message_type']}\n\n"
    
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("🔄 Обновить", callback_data="refresh_tickets"))
    
    bot.send_message(admin_id, tickets_text, reply_markup=keyboard)

def show_admin_settings(admin_id):
    """Показать настройки админа"""
    notifications = db.get_setting('notifications_enabled', '1')
    
    settings_text = f"""⚙️ <b>Настройки администратора</b>

<b>🔔 УВЕДОМЛЕНИЯ:</b>
├ Новые сообщения: {"✅ Включены" if notifications == '1' else "❌ Выключены"}
└ В канал: {"✅ Настроен" if CHANNEL else "❌ Не настроен"}

<b>⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:</b>
├ Антиспам: {ANTISPAM_INTERVAL} сек.
├ Лимит сообщений: {MAX_MESSAGES_PER_DAY} в день
└ База данных: ✅ Работает

<b>🔧 УПРАВЛЕНИЕ:</b>
<i>Используйте кнопки ниже для настройки</i>"""
    
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(f"{'🔕 Выкл. уведомления' if notifications == '1' else '🔔 Вкл. уведомления'}", 
                                 callback_data="toggle_notifications"),
        types.InlineKeyboardButton("🔄 Перезагрузить", callback_data="reload_bot")
    )
    
    bot.send_message(admin_id, settings_text, reply_markup=keyboard)

# ====== FLASK РОУТЫ ======
@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка вебхука от Telegram"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data(as_text=True)
            update = types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        else:
            return 'Invalid content type', 400
    except Exception as e:
        logger.error(f"Ошибка в webhook: {e}")
        return 'ERROR', 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья сервера"""
    try:
        # Проверяем подключение к БД
        db.get_admin_stats()
        
        return jsonify({
            'status': 'ok', 
            'time': datetime.now().isoformat(),
            'bot': 'Anony SMS Premium',
            'version': '3.0',
            'users': db.get_all_users_count(),
            'uptime': int(time.time() - start_time)
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    """Пинг для поддержания активности"""
    return jsonify({'status': 'active', 'timestamp': time.time()})

@app.route('/admin', methods=['GET'])
def admin_panel():
    """Веб-панель админа"""
    if not CHANNEL:
        return "Admin panel not configured"
    
    stats = db.get_admin_stats()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Anony SMS Admin Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            .container {{
                max-width: 1000px;
                margin: 0 auto;
            }}
            .header {{
                text-align: center;
                margin-bottom: 30px;
            }}
            .stats {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: rgba(255, 255, 255, 0.1);
                padding: 20px;
                border-radius: 10px;
                text-align: center;
                backdrop-filter: blur(10px);
            }}
            .stat-value {{
                font-size: 2em;
                font-weight: bold;
                margin: 10px 0;
            }}
            .stat-label {{
                font-size: 0.9em;
                opacity: 0.8;
            }}
            .logs {{
                background: rgba(255, 255, 255, 0.1);
                padding: 20px;
                border-radius: 10px;
                margin-top: 20px;
                backdrop-filter: blur(10px);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 Anony SMS Admin Panel</h1>
                <p>Панель управления ботом для анонимных сообщений</p>
            </div>
            
            <div class="stats">
                <div class="stat-card">
                    <div class="stat-label">Пользователей</div>
                    <div class="stat-value">{stats['total_users']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Сообщений</div>
                    <div class="stat-value">{stats['total_messages']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Новых за 24ч</div>
                    <div class="stat-value">{stats['new_users_24h']}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Тикетов</div>
                    <div class="stat-value">{stats['open_tickets']}</div>
                </div>
            </div>
            
            <div class="logs">
                <h3>📋 Последние логи</h3>
                <p>Для полного управления используйте Telegram бота</p>
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
            # Проверяем количество пользователей
            user_count = db.get_all_users_count()
            
            # Проверяем количество сообщений за последний час
            hour_ago = int(time.time()) - 3600
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', (hour_ago,))
                messages_last_hour = c.fetchone()[0]
            
            # Если активность низкая, отправляем уведомление
            if messages_last_hour < 5 and user_count > 100:
                try:
                    bot.send_message(
                        ADMIN_ID,
                        f"⚠️ <b>Низкая активность бота</b>\n\n"
                        f"За последний час отправлено всего {messages_last_hour} сообщений.\n"
                        f"Всего пользователей: {user_count}"
                    )
                except:
                    pass
            
            # Проверяем открытые тикеты
            tickets = db.get_open_support_tickets()
            if len(tickets) > 5:
                try:
                    bot.send_message(
                        ADMIN_ID,
                        f"⚠️ <b>Много открытых тикетов</b>\n\n"
                        f"Открыто {len(tickets)} тикетов поддержки."
                    )
                except:
                    pass
            
            # Ждем 1 час до следующей проверки
            time.sleep(3600)
            
        except Exception as e:
            logger.error(f"Ошибка мониторинга: {e}")
            time.sleep(300)

# ====== ЗАПУСК ======
start_time = time.time()

def keep_alive():
    """Функция для поддержания активности на Render"""
    while True:
        try:
            requests.get(f"{WEBHOOK_HOST}/ping", timeout=10)
            logger.info("✅ Ping отправлен для поддержания активности")
        except Exception as e:
            logger.error(f"❌ Ошибка ping: {e}")
        time.sleep(300)  # 5 минут

if __name__ == '__main__':
    logger.info("=== Anony SMS Bot Premium v3.0 запущен ===")
    
    # Запускаем потоки
    if WEBHOOK_HOST:
        try:
            # Поток для пинга
            ping_thread = threading.Thread(target=keep_alive, daemon=True)
            ping_thread.start()
            logger.info("✅ Пингер запущен для 24/7 работы")
            
            # Поток для мониторинга
            monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
            monitor_thread.start()
            logger.info("✅ Мониторинг запущен")
        except:
            pass
    
    try:
        if WEBHOOK_HOST:
            logger.info(f"Настройка вебхука для {WEBHOOK_HOST}")
            
            # Удаляем старый вебхук
            try:
                bot.remove_webhook()
                time.sleep(1)
            except:
                pass
            
            # Устанавливаем новый вебхук
            bot.set_webhook(
                url=f"{WEBHOOK_HOST}/webhook",
                max_connections=100,
                timeout=60
            )
            logger.info("✅ Вебхук настроен")
            
            # Запускаем Flask
            app.run(
                host='0.0.0.0',
                port=PORT,
                debug=False,
                threaded=True
            )
        else:
            # Локальный запуск
            logger.info("Локальный запуск (polling)")
            bot.remove_webhook()
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=20,
                long_polling_timeout=20
            )
            
    except Exception as e:
        logger.error(f"Критическая ошибка запуска: {e}")
        sys.exit(1)
