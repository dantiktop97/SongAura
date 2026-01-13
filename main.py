#!/usr/bin/env python3
"""
Anony SMS Bot - Бот для анонимных сообщений
Версия для Render с бесплатным планом 24/7
"""

import os
import sys
import time
import json
import logging
import qrcode
from datetime import datetime
from io import BytesIO
from contextlib import contextmanager
import sqlite3

from flask import Flask, request, jsonify
from telebot import TeleBot, types
import threading
import requests

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "ВАШ_ТОКЕН_ЗДЕСЬ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
WEBHOOK_HOST = "https://songaura.onrender.com"  # Ваш домен
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = "data.db"

# Настройки безопасности
ANTISPAM_INTERVAL = 10

# ====== ЛОГГИРОВАНИЕ ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ ======
bot = TeleBot(TOKEN, parse_mode="HTML", threaded=False)
app = Flask(__name__)

# ====== ПИНГЕР ДЛЯ 24/7 ======
def keep_alive():
    """Отправляет запросы каждые 10 минут чтобы держать сервер активным"""
    while True:
        try:
            requests.get(WEBHOOK_HOST, timeout=5)
            logger.info("✅ Ping отправлен для поддержания активности")
        except Exception as e:
            logger.error(f"❌ Ошибка ping: {e}")
        time.sleep(600)  # 10 минут

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
        except:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_db(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            
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
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER,
                    receiver_id INTEGER,
                    message_type TEXT,
                    text TEXT,
                    file_id TEXT,
                    timestamp INTEGER
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id INTEGER PRIMARY KEY,
                    blocked_at INTEGER
                )
            ''')
            
            c.execute('''
                CREATE TABLE IF NOT EXISTS waiting_messages (
                    user_id INTEGER PRIMARY KEY,
                    target_id INTEGER,
                    created_at INTEGER
                )
            ''')
    
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
    
    def is_user_blocked(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            return c.fetchone() is not None
    
    def block_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('INSERT OR REPLACE INTO blocked_users VALUES (?, ?)', (user_id, now))
    
    def unblock_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
    
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
    
    def set_waiting(self, user_id, target_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('INSERT OR REPLACE INTO waiting_messages VALUES (?, ?, ?)', 
                     (user_id, target_id, now))
    
    def get_waiting(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM waiting_messages WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    def clear_waiting(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM waiting_messages WHERE user_id = ?', (user_id,))
    
    def save_message(self, sender_id, receiver_id, message_type, text="", file_id=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO messages 
                (sender_id, receiver_id, message_type, text, file_id, timestamp) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (sender_id, receiver_id, message_type, text, file_id, int(time.time())))
    
    def get_user_stats(self, user_id):
        user = self.get_user(user_id)
        if not user:
            return None
        
        return {
            'user_id': user['user_id'],
            'username': user['username'],
            'first_name': user['first_name'],
            'messages_received': user['messages_received'],
            'messages_sent': user['messages_sent'],
            'link_clicks': user['link_clicks'],
            'last_active': user['last_active'],
            'receive_messages': user['receive_messages']
        }
    
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
            
            return {
                'total_users': total_users,
                'total_messages': total_messages,
                'blocked_users': blocked_users,
                'new_users_24h': new_users_24h,
                'messages_24h': messages_24h
            }
    
    def get_all_users(self, limit=50):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT ?', (limit,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    def set_receive_messages(self, user_id, status):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET receive_messages = ? WHERE user_id = ?',
                     (1 if status else 0, user_id))

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

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin=False):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        types.KeyboardButton("📩 Моя ссылка"),
        types.KeyboardButton("📊 Статистика"),
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
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("🔔 Вкл. сообщения"),
        types.KeyboardButton("🔕 Выкл. сообщения"),
        types.KeyboardButton("📊 Моя статистика"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton("📊 Общая статистика"),
        types.KeyboardButton("📢 Рассылка"),
        types.KeyboardButton("👥 Все пользователи"),
        types.KeyboardButton("🚫 Заблокировать"),
        types.KeyboardButton("✅ Разблокировать"),
        types.KeyboardButton("⬅️ Назад")
    ]
    keyboard.add(*buttons)
    return keyboard

cancel_keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Отмена")

# ====== ОБРАБОТЧИКИ ======
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"START: user_id={user_id}")
    
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, "🚫 Вы заблокированы в этом боте.")
        return
    
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])
        handle_link_click(user_id, target_id)
        return
    
    welcome_text = f"""🎉 <b>Добро пожаловать в Anony SMS!</b>

<b>🔐 Как это работает:</b>
1. Получи свою <b>уникальную ссылку</b>
2. Отправь её друзьям
3. Получай <b>анонимные сообщения</b>
4. Отвечай одним нажатием

<b>👇 Выбери действие:</b>"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, welcome_text, reply_markup=main_keyboard(is_admin))

def handle_link_click(clicker_id, target_id):
    if not check_spam(clicker_id):
        bot.send_message(clicker_id, "⏳ Подождите 10 секунд.")
        return
    
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, "❌ Пользователь не найден.")
        return
    
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, "❌ Этот пользователь отключил получение сообщений.")
        return
    
    db.set_waiting(clicker_id, target_id)
    db.increment_stat(target_id, 'link_clicks')
    
    bot.send_message(
        clicker_id,
        f"💌 <b>Пиши анонимное сообщение для</b> {target_user['first_name']}!\n\n"
        f"<i>Сообщение будет полностью анонимным!</i>",
        reply_markup=cancel_keyboard
    )

@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    if message.text and message.text.startswith('/'):
        return
    
    if db.is_user_blocked(user_id):
        return
    
    db.update_last_active(user_id)
    
    if text == "❌ Отмена":
        db.clear_waiting(user_id)
        is_admin = user_id == ADMIN_ID
        bot.send_message(user_id, "❌ Отменено", reply_markup=main_keyboard(is_admin))
        return
    
    waiting = db.get_waiting(user_id)
    if waiting:
        if isinstance(waiting['target_id'], int):
            send_anonymous_message(user_id, waiting['target_id'], message)
        elif waiting['target_id'] == 'support':
            send_to_support(user_id, message)
        return
    
    if message_type == 'text':
        handle_text_button(user_id, text)

def handle_text_button(user_id, text):
    is_admin = user_id == ADMIN_ID
    
    if text == "📩 Моя ссылка":
        link = generate_link(user_id)
        bot.send_message(
            user_id,
            f"🔗 <b>Твоя уникальная ссылка:</b>\n\n<code>{link}</code>",
            reply_markup=main_keyboard(is_admin)
        )
    
    elif text == "📊 Статистика":
        show_user_stats(user_id)
    
    elif text == "⚙️ Настройки":
        bot.send_message(user_id, "⚙️ <b>Настройки:</b>", reply_markup=settings_keyboard())
    
    elif text == "📱 QR-код":
        generate_qr_code(user_id)
    
    elif text == "ℹ️ Помощь":
        show_help(user_id)
    
    elif text == "🆘 Поддержка":
        db.set_waiting(user_id, 'support')
        bot.send_message(user_id, "🆘 <b>Напиши свой вопрос:</b>", reply_markup=cancel_keyboard)
    
    elif text == "👑 Админ" and is_admin:
        bot.send_message(user_id, "👑 <b>Админ-панель</b>", reply_markup=admin_keyboard())
    
    elif text == "🔔 Вкл. сообщения":
        db.set_receive_messages(user_id, True)
        bot.send_message(user_id, "✅ <b>Приём сообщений включен!</b>", reply_markup=settings_keyboard())
    
    elif text == "🔕 Выкл. сообщения":
        db.set_receive_messages(user_id, False)
        bot.send_message(user_id, "✅ <b>Приём сообщений отключен!</b>", reply_markup=settings_keyboard())
    
    elif text == "📊 Моя статистика":
        show_user_stats(user_id)
    
    elif text == "⬅️ Назад":
        bot.send_message(user_id, "Главное меню:", reply_markup=main_keyboard(is_admin))
    
    elif is_admin:
        handle_admin_command(user_id, text)

def send_anonymous_message(sender_id, receiver_id, message):
    try:
        if not check_spam(sender_id):
            bot.send_message(sender_id, "⏳ Подождите 10 секунд.")
            return
        
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, "❌ Пользователь отключил получение сообщений.")
            db.clear_waiting(sender_id)
            bot.send_message(sender_id, "Главное меню:", reply_markup=main_keyboard(sender_id == ADMIN_ID))
            return
        
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
        
        db.save_message(sender_id, receiver_id, message.content_type, message.text or message.caption or "", file_id)
        
        caption = f"📨 <b>Новое анонимное сообщение!</b>\n\n"
        
        if message.content_type == 'text':
            bot.send_message(receiver_id, f"{caption}{message.text}")
        elif message.content_type == 'photo':
            bot.send_photo(receiver_id, file_id, caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'video':
            bot.send_video(receiver_id, file_id, caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'audio':
            bot.send_audio(receiver_id, file_id, caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'voice':
            bot.send_voice(receiver_id, file_id, caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'document':
            bot.send_document(receiver_id, file_id, caption=f"{caption}{message.caption or ''}")
        
        reply_markup = types.InlineKeyboardMarkup()
        reply_markup.add(types.InlineKeyboardButton("💌 Ответить анонимно", url=generate_link(receiver_id)))
        
        bot.send_message(receiver_id, "💬 Хочешь ответить?", reply_markup=reply_markup)
        
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        bot.send_message(sender_id, "✅ <b>Сообщение отправлено анонимно!</b>", reply_markup=main_keyboard(sender_id == ADMIN_ID))
        
        db.clear_waiting(sender_id)
        
        try:
            admin_msg = f"📨 <b>Новое анонимное сообщение</b>\nОт: <code>{sender_id}</code>\nКому: <code>{receiver_id}</code>\nТип: {message.content_type}"
            bot.send_message(ADMIN_ID, admin_msg)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        bot.send_message(sender_id, "❌ Ошибка при отправке сообщения.")

def send_to_support(user_id, message):
    try:
        user = db.get_user(user_id)
        username = f"@{user['username']}" if user['username'] else "Без username"
        
        admin_msg = f"🆘 <b>Сообщение в поддержку</b>\n\n👤 От: {user['first_name']}\n📱 {username}\n🆔 ID: <code>{user_id}</code>\n\n"
        
        if message.content_type == 'text':
            admin_msg += f"💬 <b>Сообщение:</b>\n{message.text}"
            bot.send_message(ADMIN_ID, admin_msg)
        else:
            bot.send_message(ADMIN_ID, admin_msg)
            if message.content_type == 'photo':
                bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=message.caption or "")
            elif message.content_type == 'video':
                bot.send_video(ADMIN_ID, message.video.file_id, caption=message.caption or "")
        
        bot.send_message(user_id, "✅ <b>Сообщение отправлено в поддержку!</b>", reply_markup=main_keyboard(user_id == ADMIN_ID))
        
        db.clear_waiting(user_id)
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        bot.send_message(user_id, "❌ Ошибка при отправке сообщения в поддержку.")

def show_user_stats(user_id):
    stats = db.get_user_stats(user_id)
    
    if not stats:
        bot.send_message(user_id, "❌ Данные не найдены.")
        return
    
    stats_text = f"""📊 <b>Твоя статистика</b>

<b>👤 Основное:</b>
• Получено: <b>{stats['messages_received']}</b>
• Отправлено: <b>{stats['messages_sent']}</b>
• Переходов: <b>{stats['link_clicks']}</b>

<b>⏰ Активность:</b>
• Последний онлайн: {format_time(stats['last_active'])}
• Приём сообщений: {"✅ Включен" if stats['receive_messages'] else "❌ Выключен"}

<b>🔗 Твоя ссылка:</b>
<code>{generate_link(user_id)}</code>"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, stats_text, reply_markup=main_keyboard(is_admin))

def generate_qr_code(user_id):
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.send_photo(user_id, photo=bio, caption=f"📱 <b>Твой QR-код</b>\n\nСсылка: <code>{link}</code>", reply_markup=main_keyboard(user_id == ADMIN_ID))
    except Exception as e:
        logger.error(f"Ошибка QR: {e}")
        bot.send_message(user_id, "❌ Ошибка при генерации QR-кода.")

def show_help(user_id):
    help_text = """ℹ️ <b>Как пользоваться ботом?</b>

<b>📨 Для получения сообщений:</b>
1. Нажми «Моя ссылка»
2. Скопируй ссылку
3. Отправь друзьям
4. Получай анонимные сообщения!

<b>✉️ Для отправки сообщений:</b>
1. Перейди по чужой ссылке
2. Напиши сообщение
3. Оно отправится анонимно

<b>🆘 Поддержка:</b>
Если есть вопросы — пиши в поддержку!"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, help_text, reply_markup=main_keyboard(is_admin))

# ====== АДМИН ======
admin_modes = {}

def handle_admin_command(admin_id, text):
    if text == "📊 Общая статистика":
        show_admin_stats(admin_id)
    
    elif text == "📢 Рассылка":
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(admin_id, "📢 <b>Отправь сообщение для рассылки:</b>", reply_markup=cancel_keyboard)
    
    elif text == "👥 Все пользователи":
        show_all_users(admin_id)
    
    elif text == "🚫 Заблокировать":
        admin_modes[admin_id] = 'block'
        bot.send_message(admin_id, "🚫 <b>Введите ID пользователя:</b>", reply_markup=cancel_keyboard)
    
    elif text == "✅ Разблокировать":
        admin_modes[admin_id] = 'unblock'
        bot.send_message(admin_id, "✅ <b>Введите ID пользователя:</b>", reply_markup=cancel_keyboard)
    
    elif admin_id in admin_modes:
        mode = admin_modes[admin_id]
        
        if mode == 'broadcast':
            broadcast_message(admin_id, text)
            del admin_modes[admin_id]
        
        elif mode == 'block' and text.isdigit():
            block_user(admin_id, int(text))
            del admin_modes[admin_id]
        
        elif mode == 'unblock' and text.isdigit():
            unblock_user(admin_id, int(text))
            del admin_modes[admin_id]

def show_admin_stats(admin_id):
    stats = db.get_admin_stats()
    
    stats_text = f"""👑 <b>Статистика бота</b>

<b>📊 Основное:</b>
• Пользователей: <b>{stats['total_users']}</b>
• Сообщений: <b>{stats['total_messages']}</b>
• Заблокированных: <b>{stats['blocked_users']}</b>

<b>📈 За 24 часа:</b>
• Новых: <b>{stats['new_users_24h']}</b>
• Сообщений: <b>{stats['messages_24h']}</b>"""
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard())

def broadcast_message(admin_id, text):
    users = db.get_all_users()
    sent = 0
    failed = 0
    
    for user in users:
        try:
            bot.send_message(user['user_id'], text, parse_mode="HTML")
            sent += 1
            time.sleep(0.05)
        except:
            failed += 1
    
    bot.send_message(admin_id, f"✅ <b>Рассылка завершена!</b>\n• Отправлено: <b>{sent}</b>\n• Не отправлено: <b>{failed}</b>", reply_markup=admin_keyboard())
    logger.info(f"BROADCAST: sent={sent}, failed={failed}")

def show_all_users(admin_id):
    users = db.get_all_users()
    
    if not users:
        bot.send_message(admin_id, "❌ Нет пользователей.")
        return
    
    response = f"👥 <b>Последние {len(users)} пользователей:</b>\n\n"
    
    for user in users:
        status = "✅" if user['receive_messages'] else "🔕"
        response += f"{status} <code>{user['user_id']}</code> - {user['first_name']}"
        if user['username']:
            response += f" (@{user['username']})"
        response += f"\n📨 {user['messages_received']} | 📤 {user['messages_sent']}\n\n"
    
    bot.send_message(admin_id, response, reply_markup=admin_keyboard())

def block_user(admin_id, target_id):
    try:
        db.block_user(target_id)
        bot.send_message(admin_id, f"✅ <code>{target_id}</code> заблокирован.", reply_markup=admin_keyboard())
        logger.info(f"BLOCK: {target_id}")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

def unblock_user(admin_id, target_id):
    try:
        db.unblock_user(target_id)
        bot.send_message(admin_id, f"✅ <code>{target_id}</code> разблокирован.", reply_markup=admin_keyboard())
        logger.info(f"UNBLOCK: {target_id}")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

# ====== FLASK РОУТЫ ======
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    return 'ERROR', 403

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

@app.route('/')
def index():
    return "Anony SMS Bot is running! ✅"

@app.route('/ping')
def ping():
    return jsonify({'status': 'active', 'timestamp': time.time()})

# ====== ЗАПУСК ======
if __name__ == '__main__':
    logger.info("=== Бот запущен ===")
    
    # Запускаем поток для пинга
    if WEBHOOK_HOST:
        ping_thread = threading.Thread(target=keep_alive, daemon=True)
        ping_thread.start()
        logger.info("✅ Пингер запущен для 24/7 работы")
    
    try:
        if WEBHOOK_HOST:
            logger.info(f"Настройка вебхука для {WEBHOOK_HOST}")
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=f"{WEBHOOK_HOST}/webhook")
            logger.info("✅ Вебхук настроен")
            
            app.run(host='0.0.0.0', port=PORT, debug=False)
        else:
            logger.info("Локальный запуск (polling)")
            bot.remove_webhook()
            bot.polling(none_stop=True, interval=0, timeout=20)
            
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
