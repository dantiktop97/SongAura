#!/usr/bin/env python3
"""
Anony SMS Bot - Premium версия
"""

import os
import sys
import time
import json
import logging
import qrcode
import re
import threading
from datetime import datetime
from io import BytesIO
from contextlib import contextmanager
import sqlite3
import requests

from flask import Flask, request, jsonify
from telebot import TeleBot, types
from telebot.apihelper import ApiException

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
WEBHOOK_HOST = "https://songaura.onrender.com"
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = "data.db"

ANTISPAM_INTERVAL = 10

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
active_support_chats = {}  # {user_id: admin_id}
admin_modes = {}
user_reply_targets = {}  # {user_id: target_id}
admin_waiting_reply = {}  # {admin_id: user_id}

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
                CREATE TABLE IF NOT EXISTS support_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    admin_id INTEGER,
                    message TEXT,
                    file_id TEXT,
                    message_type TEXT,
                    timestamp INTEGER,
                    is_from_admin INTEGER DEFAULT 0
                )
            ''')
            
            # Логи сообщений для админа
            c.execute('''
                CREATE TABLE IF NOT EXISTS message_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER,
                    receiver_id INTEGER,
                    message_type TEXT,
                    text TEXT,
                    timestamp INTEGER
                )
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
    
    def get_all_users(self, limit=1000):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT ?', (limit,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    # ====== СООБЩЕНИЯ ======
    def save_message(self, sender_id, receiver_id, message_type, text="", file_id=None, replied_to=0):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO messages 
                (sender_id, receiver_id, message_type, text, file_id, timestamp, replied_to) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (sender_id, receiver_id, message_type, text, file_id, int(time.time()), replied_to))
            
            # Сохраняем в логи для админа
            if text:
                c.execute('''
                    INSERT INTO message_logs (sender_id, receiver_id, message_type, text, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                ''', (sender_id, receiver_id, message_type, text[:500], int(time.time())))
    
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
            
            return {
                'messages_sent': sent_count,
                'messages_received': received_count,
                'top_words': top_words
            }
    
    def get_recent_messages(self, limit=10):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT m.*, u1.first_name as sender_name, u1.username as sender_username,
                       u2.first_name as receiver_name, u2.username as receiver_username
                FROM messages m
                LEFT JOIN users u1 ON m.sender_id = u1.user_id
                LEFT JOIN users u2 ON m.receiver_id = u2.user_id
                ORDER BY m.timestamp DESC LIMIT ?
            ''', (limit,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
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
    
    # ====== ПОДДЕРЖКА ======
    def save_support_message(self, user_id, admin_id, message, file_id=None, message_type="text", is_from_admin=False):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO support_messages 
                (user_id, admin_id, message, file_id, message_type, timestamp, is_from_admin) 
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, admin_id, message, file_id, message_type, int(time.time()), 1 if is_from_admin else 0))
    
    def get_support_chats(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT DISTINCT user_id FROM support_messages 
                WHERE is_from_admin = 0 
                ORDER BY timestamp DESC
            ''')
            return [row[0] for row in c.fetchall()]
    
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
            
            return {
                'total_users': total_users,
                'total_messages': total_messages,
                'blocked_users': blocked_users,
                'new_users_24h': new_users_24h
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

def get_message_reply_keyboard(target_id):
    """Клавиатура для ответа на сообщение"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("💌 Ответить", callback_data=f"reply_{target_id}"),
        types.InlineKeyboardButton("🚫 Игнор", callback_data="ignore")
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
        types.KeyboardButton("👥 Все пользователи"),
        types.KeyboardButton("🔍 Найти пользователя"),
        types.KeyboardButton("📋 Логи сообщений"),
        types.KeyboardButton("🚫 Блокировки"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

cancel_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Отмена")

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
        bot.send_message(clicker_id, "⏳ Подождите 10 секунд перед следующим сообщением.")
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
        f"💌 <b>Пиши анонимное сообщение для</b> <i>{target_user['first_name']}</i>!\n\n"
        f"<b>📝 Можно отправить:</b>\n"
        f"• Текст ✍️\n• Фото 📸\n• Видео 🎬\n• Голосовое 🎤\n• Стикер 😜\n• GIF 🎞️\n\n"
        f"<i>💭 Сообщение будет <b>полностью анонимным</b>!\n"
        f"Получатель не узнает, кто его отправил 👻</i>",
        reply_markup=cancel_keyboard
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработка inline кнопок"""
    user_id = call.from_user.id
    data = call.data
    
    if data == "ignore":
        bot.answer_callback_query(call.id, "✅ Сообщение проигнорировано")
        return
    
    elif data.startswith("reply_"):
        target_id = int(data.split("_")[1])
        user_reply_targets[user_id] = target_id
        
        bot.send_message(
            user_id,
            f"💌 <b>Отправь ответ анонимно!</b>\n\n"
            f"<i>Твоё сообщение будет отправлено как анонимное 💭</i>",
            reply_markup=cancel_keyboard
        )
        bot.answer_callback_query(call.id)
    
    elif data.startswith("admin_block_"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Только для админа")
            return
        
        target_id = int(data.split("_")[2])
        db.block_user(target_id, ADMIN_ID, "Через админ-панель")
        bot.answer_callback_query(call.id, "✅ Пользователь заблокирован")
        bot.send_message(user_id, f"✅ Пользователь <code>{target_id}</code> заблокирован.")
    
    elif data.startswith("admin_msg_"):
        if user_id != ADMIN_ID:
            bot.answer_callback_query(call.id, "❌ Только для админа")
            return
        
        target_id = int(data.split("_")[2])
        admin_waiting_reply[user_id] = target_id
        
        bot.send_message(
            user_id,
            f"✉️ <b>Отправь сообщение для пользователя</b> <code>{target_id}</code>\n\n"
            f"<i>Сообщение придёт как от бота 🤖</i>",
            reply_markup=cancel_keyboard
        )
        bot.answer_callback_query(call.id)

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
    
    # Ответ админа пользователю в поддержке
    if user_id == ADMIN_ID and user_id in active_support_chats:
        target_user_id = active_support_chats[user_id]
        send_admin_to_user(message, target_user_id)
        return
    
    # Админ пишет пользователю напрямую
    if user_id == ADMIN_ID and user_id in admin_waiting_reply:
        target_user_id = admin_waiting_reply[user_id]
        send_direct_admin_message(message, target_user_id)
        return
    
    # Проверяем ожидание (отправка анонимки)
    if user_id in user_reply_targets:
        target_id = user_reply_targets[user_id]
        send_anonymous_message(user_id, target_id, message)
        return
    
    # Обработка кнопок главного меню
    if message_type == 'text':
        handle_text_button(user_id, text)

def clear_user_state(user_id):
    """Очистка состояний пользователя"""
    if user_id in user_reply_targets:
        del user_reply_targets[user_id]
    if user_id in admin_waiting_reply:
        del admin_waiting_reply[user_id]
    if user_id in active_support_chats.values():
        # Находим админа, который общался с этим пользователем
        for admin_id, target_id in active_support_chats.items():
            if target_id == user_id:
                del active_support_chats[admin_id]
                break

def handle_text_button(user_id, text):
    is_admin = user_id == ADMIN_ID
    
    if text == "📩 Моя ссылка":
        link = generate_link(user_id)
        bot.send_message(
            user_id,
            f"🔗 <b>Твоя уникальная ссылка для анонимок:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"<i>📤 Поделись с друзьями в:\n• Чатах 💬\n• Соцсетях 🌐\n• Сторис 📲\n\n"
            f"🎭 Каждый переход — новый анонимный отправитель!\n"
            f"🔥 Чем больше делишься, тем больше тайн узнаёшь 😏</i>",
            reply_markup=main_keyboard(is_admin)
        )
    
    elif text == "👤 Профиль":
        show_profile(user_id)
    
    elif text == "⚙️ Настройки":
        bot.send_message(
            user_id,
            "⚙️ <b>Настройки приватности</b>\n\n"
            "<i>Управляй получением анонимных сообщений:</i>",
            reply_markup=settings_keyboard()
        )
    
    elif text == "📱 QR-код":
        generate_qr_code(user_id)
    
    elif text == "ℹ️ Помощь":
        show_help(user_id)
    
    elif text == "🆘 Поддержка":
        bot.send_message(
            user_id,
            "🆘 <b>Служба поддержки</b>\n\n"
            "<i>Расскажи о проблеме или задай вопрос 💭\n"
            "Мы ответим в ближайшее время ⏰</i>\n\n"
            "<b>📎 Можно отправить:</b>\n"
            "• Текст описания проблемы ✍️\n"
            "• Скриншот бага 📸\n"
            "• Видео с ошибкой 🎬\n"
            "• Любой медиафайл 📎\n\n"
            "<i>Опиши проблему как можно подробнее 🔍</i>",
            reply_markup=cancel_keyboard
        )
        # Отмечаем, что пользователь пишет в поддержку
        active_support_chats[user_id] = 'waiting'
    
    elif text == "👑 Админ" and is_admin:
        bot.send_message(
            user_id,
            "👑 <b>Панель администратора</b>\n\n"
            "<i>Доступ к управлению ботом 🔧</i>",
            reply_markup=admin_keyboard()
        )
    
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
    
    elif text == "⬅️ Назад":
        bot.send_message(user_id, "Главное меню:", reply_markup=main_keyboard(is_admin))
    
    # Админские команды
    elif is_admin:
        handle_admin_command(user_id, text)

def show_profile(user_id):
    """Показать профиль пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        profile_text = "👤 <b>Профиль</b>\n\n"
        profile_text += "❌ <i>Данные не найдены</i>"
        is_admin = user_id == ADMIN_ID
        bot.send_message(user_id, profile_text, reply_markup=main_keyboard(is_admin))
        return
    
    stats = db.get_user_messages_stats(user_id)
    
    profile_text = f"""👤 <b>Твой профиль</b>

<b>📊 Идентификация:</b>
├ ID: <code>{user['user_id']}</code>
├ Имя: <b>{user['first_name']}</b>
└ Юзернейм: {f'@{user['username']}' if user['username'] else '❌ отсутствует'}

<b>📈 Статистика:</b>
├ 📨 Получено: <b>{user['messages_received']}</b>
├ 📤 Отправлено: <b>{user['messages_sent']}</b>
└ 🔗 Переходов: <b>{user['link_clicks']}</b>

<b>⚙️ Настройки:</b>
├ Приём сообщений: {"✅ Включён" if user['receive_messages'] else "❌ Выключен"}
└ Последняя активность: {format_time(user['last_active'])}

<b>🔗 Твоя ссылка:</b>
<code>{generate_link(user_id)}</code>"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, profile_text, reply_markup=main_keyboard(is_admin))

def send_anonymous_message(sender_id, receiver_id, message):
    """Отправка анонимного сообщения"""
    try:
        if not check_spam(sender_id):
            bot.send_message(sender_id, "⏳ Подождите 10 секунд перед следующим сообщением.")
            return
        
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, "❌ Этот пользователь отключил получение сообщений.")
            clear_user_state(sender_id)
            bot.send_message(sender_id, "Главное меню:", reply_markup=main_keyboard(sender_id == ADMIN_ID))
            return
        
        # Получаем информацию об отправителе для логов
        sender = db.get_user(sender_id)
        
        # Сохраняем сообщение
        file_id = None
        if message.content_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message.content_type == 'video':
            file_id = message.video.file_id
        elif message.content_type == 'audio':
            file_id = message.audio.file_id
        elif message.content_type == 'voice':
            file_id = message.voice.file_id
        elif message.content_type == 'document':
            file_id = message.document.file_id
        elif message.content_type == 'sticker':
            file_id = message.sticker.file_id
        
        db.save_message(
            sender_id, receiver_id, 
            message.content_type, 
            message.text or message.caption or "", 
            file_id
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
        if message.content_type == 'text':
            msg = bot.send_message(receiver_id, caption, reply_markup=get_message_reply_keyboard(sender_id))
        elif message.content_type == 'photo':
            msg = bot.send_photo(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
        elif message.content_type == 'video':
            msg = bot.send_video(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
        elif message.content_type == 'audio':
            msg = bot.send_audio(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
        elif message.content_type == 'voice':
            msg = bot.send_voice(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
        elif message.content_type == 'document':
            msg = bot.send_document(receiver_id, file_id, caption=caption, reply_markup=get_message_reply_keyboard(sender_id))
        elif message.content_type == 'sticker':
            bot.send_message(receiver_id, caption)
            msg = bot.send_sticker(receiver_id, file_id)
        
        # Обновляем статистику
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Уведомляем отправителя
        bot.send_message(
            sender_id,
            f"""✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Получатель: <b>{receiver['first_name']}</b>
🔒 Твоя личность: <b>скрыта</b>
💭 Сообщение доставлено успешно!</i>

<b>Хочешь отправить ещё?</b>
Просто продолжай писать ✍️""",
            reply_markup=cancel_keyboard
        )
        
        # Логируем для админа
        log_msg = f"""📨 <b>Новое анонимное сообщение</b>

👤 От: <code>{sender_id}</code> ({sender['first_name'] if sender else '?'})
🎯 Кому: <code>{receiver_id}</code> ({receiver['first_name']})
📝 Тип: {message.content_type}"""
        
        if message_text:
            log_msg += f"\n💬 Текст: <code>{message_text[:100]}</code>"
        
        try:
            bot.send_message(ADMIN_ID, log_msg)
        except:
            pass
        
        # Очищаем состояние пользователя
        # Не очищаем user_reply_targets, чтобы можно было отправлять несколько сообщений
        
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        bot.send_message(
            sender_id,
            "❌ <b>Ошибка при отправке сообщения.</b>\n\n"
            "<i>Попробуй ещё раз или обратись в поддержку 🆘</i>"
        )

def send_admin_to_user(message, target_user_id):
    """Админ отвечает пользователю в поддержке"""
    try:
        user_info = db.get_user(target_user_id)
        file_id = None
        message_type = message.content_type
        
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        
        # Сохраняем в БД
        db.save_support_message(
            target_user_id, 
            message.from_user.id,
            message.text or message.caption or "",
            file_id,
            message_type,
            is_from_admin=True
        )
        
        # Отправляем пользователю
        response_text = f"""🆘 <b>Ответ от поддержки</b>

<i>Мы получили твоё обращение и готовы помочь! 🤝</i>

💬 <b>Сообщение:</b>
<code>{message.text or message.caption or ''}</code>

<i>Если проблема не решена — пиши ещё! 💭</i>"""
        
        try:
            if message_type == 'text':
                bot.send_message(target_user_id, response_text)
            elif message_type == 'photo':
                bot.send_photo(target_user_id, file_id, caption=response_text)
            elif message_type == 'video':
                bot.send_video(target_user_id, file_id, caption=response_text)
            elif message_type == 'document':
                bot.send_document(target_user_id, file_id, caption=response_text)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю: {e}")
            bot.send_message(ADMIN_ID, f"❌ Не удалось отправить сообщение пользователю {target_user_id}")
        
        # Уведомляем админа
        bot.send_message(
            ADMIN_ID,
            f"✅ <b>Ответ отправлен пользователю</b>\n\n"
            f"👤 Пользователь: <code>{target_user_id}</code>\n"
            f"📝 Тип: {message_type}",
            reply_markup=admin_keyboard()
        )
        
        # Очищаем чат поддержки
        if ADMIN_ID in active_support_chats:
            del active_support_chats[ADMIN_ID]
        
    except Exception as e:
        logger.error(f"Ошибка отправки ответа: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка при отправке ответа")

def send_direct_admin_message(message, target_user_id):
    """Админ отправляет сообщение пользователю напрямую"""
    try:
        file_id = None
        message_type = message.content_type
        
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        
        message_text = message.text or message.caption or ""
        
        # Отправляем пользователю
        user_message = f"""📢 <b>Важное уведомление</b>

{message_text}

<i>С уважением, команда бота 🤖</i>"""
        
        try:
            if message_type == 'text':
                bot.send_message(target_user_id, user_message)
            elif message_type == 'photo':
                bot.send_photo(target_user_id, file_id, caption=user_message)
            elif message_type == 'video':
                bot.send_video(target_user_id, file_id, caption=user_message)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение: {e}")
            bot.send_message(ADMIN_ID, f"❌ Не удалось отправить сообщение пользователю {target_user_id}")
            return
        
        # Уведомляем админа
        bot.send_message(
            ADMIN_ID,
            f"✅ <b>Сообщение отправлено</b>\n\n"
            f"👤 Пользователь: <code>{target_user_id}</code>\n"
            f"📝 Тип: {message_type}",
            reply_markup=admin_keyboard()
        )
        
        # Очищаем состояние
        if ADMIN_ID in admin_waiting_reply:
            del admin_waiting_reply[ADMIN_ID]
        
    except Exception as e:
        logger.error(f"Ошибка отправки: {e}")
        bot.send_message(ADMIN_ID, "❌ Ошибка при отправке сообщения")

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

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id, text):
    """Обработка админских команд"""
    
    if text == "📊 Статистика":
        show_admin_stats(admin_id)
    
    elif text == "📢 Рассылка":
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(
            admin_id,
            "📢 <b>Создание рассылки</b>\n\n"
            "<i>Отправь сообщение (текст, фото, видео, стикер, GIF), "
            "и оно будет отправлено всем пользователям бота.</i>\n\n"
            "<b>💡 Подсказка:</b>\n"
            "• Используй HTML-разметку для форматирования\n"
            "• Можно отправлять медиафайлы\n"
            "• Рассылка идёт всем, кто не заблокировал бота",
            reply_markup=cancel_keyboard
        )
    
    elif text == "👥 Все пользователи":
        show_all_users(admin_id)
    
    elif text == "🔍 Найти пользователя":
        admin_modes[admin_id] = 'find_user'
        bot.send_message(
            admin_id,
            "🔍 <b>Поиск пользователя</b>\n\n"
            "<i>Введите:</i>\n"
            "• <b>ID пользователя</b> (например: 123456789)\n"
            "• <b>Юзернейм</b> (например: @username)\n\n"
            "<b>Я покажу полную информацию о пользователе 🔎</b>",
            reply_markup=cancel_keyboard
        )
    
    elif text == "📋 Логи сообщений":
        show_message_logs(admin_id)
    
    elif text == "🚫 Блокировки":
        show_blocked_users(admin_id)
    
    elif text == "⬅️ Назад":
        bot.send_message(admin_id, "Главное меню:", reply_markup=main_keyboard(True))
    
    # Обработка ввода в режиме админа
    elif admin_id in admin_modes:
        mode = admin_modes[admin_id]
        
        if mode == 'broadcast':
            broadcast_message(admin_id, text)
            del admin_modes[admin_id]
        
        elif mode == 'find_user':
            find_user_info(admin_id, text)
            del admin_modes[admin_id]

def show_admin_stats(admin_id):
    """Показать статистику для админа"""
    stats = db.get_admin_stats()
    
    stats_text = f"""👑 <b>Статистика бота</b>

<b>📊 ОСНОВНЫЕ МЕТРИКИ:</b>
├ Всего пользователей: <b>{stats['total_users']}</b>
├ Всего сообщений: <b>{stats['total_messages']}</b>
├ Заблокированных: <b>{stats['blocked_users']}</b>
└ Новых за 24ч: <b>{stats['new_users_24h']}</b>

<b>📈 АКТИВНОСТЬ:</b>
<i>Бот работает стабильно и принимает сообщения ⚡</i>

<b>🔧 УПРАВЛЕНИЕ:</b>
<i>Используй меню ниже для управления ботом 🔧</i>"""
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard())

def broadcast_message(admin_id, text):
    """Рассылка сообщения всем пользователям"""
    try:
        bot.send_message(admin_id, "⏳ <b>Начинаю рассылку...</b>")
        
        users = db.get_all_users()
        sent = 0
        failed = 0
        total = len(users)
        
        for user in users:
            try:
                # Пытаемся отправить сообщение
                bot.send_message(user['user_id'], text, parse_mode="HTML")
                sent += 1
                
                # Небольшая задержка для антифлуда
                time.sleep(0.05)
                
                # Обновляем прогресс каждые 50 пользователей
                if sent % 50 == 0:
                    bot.send_message(admin_id, f"📤 Отправлено: {sent}/{total}")
                    
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
└ Не удалось отправить: <b>{failed}</b>

<i>💡 Недоставленные сообщения — пользователи, которые заблокировали бота.</i>"""
        
        bot.send_message(admin_id, report, reply_markup=admin_keyboard())
        logger.info(f"РАССЫЛКА: отправлено={sent}, не отправлено={failed}")
        
    except Exception as e:
        logger.error(f"Ошибка рассылки: {e}")
        bot.send_message(admin_id, f"❌ Ошибка при рассылке: {e}", reply_markup=admin_keyboard())

def show_all_users(admin_id):
    """Показать всех пользователей"""
    users = db.get_all_users(limit=50)
    
    if not users:
        bot.send_message(admin_id, "❌ Нет пользователей.", reply_markup=admin_keyboard())
        return
    
    response = f"👥 <b>Последние {len(users)} пользователей:</b>\n\n"
    
    for i, user in enumerate(users, 1):
        status = "✅" if user['receive_messages'] else "🔕"
        block_status = "🚫" if db.is_user_blocked(user['user_id']) else "✅"
        
        response += f"{i}. {status}{block_status} <code>{user['user_id']}</code> - {user['first_name']}"
        if user['username']:
            response += f" (@{user['username']})"
        response += f"\n   📨 {user['messages_received']} | 📤 {user['messages_sent']} | 🔗 {user['link_clicks']}\n\n"
    
    response += f"\n<i>Всего пользователей в базе: {len(users)}</i>"
    
    bot.send_message(admin_id, response, reply_markup=admin_keyboard())

def find_user_info(admin_id, query):
    """Найти информацию о пользователе"""
    try:
        user = None
        
        if query.startswith('@'):
            # Поиск по юзернейму
            username = query[1:]  # Убираем @
            user = db.get_user_by_username(username)
        elif query.isdigit():
            # Поиск по ID
            user_id = int(query)
            user = db.get_user(user_id)
        
        if not user:
            bot.send_message(admin_id, f"❌ Пользователь не найден: {query}", reply_markup=admin_keyboard())
            return
        
        # Получаем статистику сообщений
        stats = db.get_user_messages_stats(user['user_id'])
        is_blocked = db.is_user_blocked(user['user_id'])
        
        user_info = f"""🔍 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

<b>👤 ОСНОВНЫЕ ДАННЫЕ:</b>
├ ID: <code>{user['user_id']}</code>
├ Имя: <b>{user['first_name']}</b>
├ Юзернейм: {f'@{user['username']}' if user['username'] else '❌ отсутствует'}
├ Зарегистрирован: {format_time(user['created_at'])}
└ Последняя активность: {format_time(user['last_active'])}

<b>📊 СТАТИСТИКА:</b>
├ 📨 Получено сообщений: <b>{user['messages_received']}</b>
├ 📤 Отправлено сообщений: <b>{user['messages_sent']}</b>
├ 🔗 Переходов по ссылке: <b>{user['link_clicks']}</b>
└ ⚙️ Приём сообщений: {"✅ Включён" if user['receive_messages'] else "❌ Выключен"}

<b>🔤 ТОП-5 СЛОВ в сообщениях:</b>"""
        
        if stats['top_words']:
            for word, count in stats['top_words']:
                user_info += f"\n├ '{word}': {count} раз"
            user_info += "\n└"
        else:
            user_info += "\n└ <i>Нет данных о словах</i>"
        
        user_info += f"\n\n<b>🚫 СТАТУС БЛОКИРОВКИ:</b> {'✅ Заблокирован' if is_blocked else '✅ Активен'}"
        
        bot.send_message(admin_id, user_info, reply_markup=get_admin_user_keyboard(user['user_id']))
        
    except Exception as e:
        logger.error(f"Ошибка поиска пользователя: {e}")
        bot.send_message(admin_id, f"❌ Ошибка: {e}", reply_markup=admin_keyboard())

def show_message_logs(admin_id):
    """Показать логи сообщений"""
    messages = db.get_recent_messages(limit=10)
    
    if not messages:
        bot.send_message(admin_id, "❌ Нет логов сообщений.", reply_markup=admin_keyboard())
        return
    
    logs_text = "📋 <b>Последние 10 анонимных сообщений:</b>\n\n"
    
    for i, msg in enumerate(messages, 1):
        sender_name = msg.get('sender_name', 'Неизвестно')
        receiver_name = msg.get('receiver_name', 'Неизвестно')
        sender_username = f" (@{msg['sender_username']})" if msg.get('sender_username') else ""
        receiver_username = f" (@{msg['receiver_username']})" if msg.get('receiver_username') else ""
        
        logs_text += f"{i}. <b>{format_time(msg['timestamp'])}</b>\n"
        logs_text += f"   👤 От: <code>{msg['sender_id']}</code> - {sender_name}{sender_username}\n"
        logs_text += f"   🎯 Кому: <code>{msg['receiver_id']}</code> - {receiver_name}{receiver_username}\n"
        logs_text += f"   📝 Тип: {msg['message_type']}\n"
        
        if msg['text'] and len(msg['text']) > 0:
            text_preview = msg['text'][:100] + "..." if len(msg['text']) > 100 else msg['text']
            logs_text += f"   💬 Текст: <code>{text_preview}</code>\n"
        
        logs_text += "\n"
    
    bot.send_message(admin_id, logs_text, reply_markup=admin_keyboard())

def show_blocked_users(admin_id):
    """Показать заблокированных пользователей"""
    # В этой версии просто покажем количество
    stats = db.get_admin_stats()
    
    blocked_text = f"""🚫 <b>Блокировки пользователей</b>

<b>📊 СТАТИСТИКА:</b>
├ Заблокировано всего: <b>{stats['blocked_users']}</b>
└ Активных пользователей: <b>{stats['total_users'] - stats['blocked_users']}</b>

<i>💡 Для просмотра и управления блокировками 
используйте поиск пользователя и блокировку через его профиль 🔧</i>"""
    
    bot.send_message(admin_id, blocked_text, reply_markup=admin_keyboard())

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
    return jsonify({
        'status': 'ok', 
        'time': datetime.now().isoformat(),
        'bot': 'Anony SMS',
        'version': '2.0'
    })

@app.route('/ping', methods=['GET'])
def ping():
    """Пинг для поддержания активности"""
    return jsonify({'status': 'active', 'timestamp': time.time()})

@app.route('/')
def index():
    """Главная страница"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Anony SMS Bot</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
                background: rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }
            h1 {
                font-size: 2.5em;
                margin-bottom: 20px;
            }
            .status {
                font-size: 1.2em;
                margin: 20px 0;
                padding: 15px;
                background: rgba(255, 255, 255, 0.2);
                border-radius: 10px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Anony SMS Bot</h1>
            <div class="status">✅ Бот работает стабильно</div>
            <p>Отправляй и получай анонимные сообщения в Telegram!</p>
            <p><a href="https://t.me/anonysms_bot" style="color: white; text-decoration: underline;">Перейти в бот</a></p>
        </div>
    </body>
    </html>
    """

# ====== ЗАПУСК ======
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
    logger.info("=== Anony SMS Bot запущен ===")
    
    # Запускаем поток для поддержания активности
    if WEBHOOK_HOST:
        try:
            ping_thread = threading.Thread(target=keep_alive, daemon=True)
            ping_thread.start()
            logger.info("✅ Пингер запущен для 24/7 работы")
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
