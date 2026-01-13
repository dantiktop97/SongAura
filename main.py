#!/usr/bin/env python3
"""
Anony SMS Bot - Бот для анонимных сообщений
Версия для деплоя на Render с PostgreSQL
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
import psycopg2
from psycopg2.extras import RealDictCursor

from flask import Flask, request, jsonify
from telebot import TeleBot, types

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "ВАШ_ТОКЕН_ЗДЕСЬ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
WEBHOOK_HOST = os.getenv("RENDER_EXTERNAL_URL", "")
PORT = int(os.getenv("PORT", "10000"))
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройки безопасности
ANTISPAM_INTERVAL = 10  # секунд между сообщениями

# ====== НАСТРОЙКА ЛОГГИРОВАНИЯ ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ ======
bot = TeleBot(TOKEN, parse_mode="HTML", threaded=False)
app = Flask(__name__)

# Кэш для антиспама
last_message_time = {}

# ====== БАЗА ДАННЫХ (PostgreSQL) ======
class Database:
    def __init__(self):
        self.conn_params = DATABASE_URL
    
    @contextmanager
    def get_connection(self):
        conn = psycopg2.connect(self.conn_params, sslmode='require')
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def init_database(self):
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Таблица пользователей
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
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
            
            # Таблица сообщений
            c.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id SERIAL PRIMARY KEY,
                    sender_id BIGINT,
                    receiver_id BIGINT,
                    message_type TEXT,
                    text TEXT,
                    file_id TEXT,
                    timestamp INTEGER
                )
            ''')
            
            # Таблица блокировок
            c.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id BIGINT PRIMARY KEY,
                    blocked_at INTEGER
                )
            ''')
            
            # Таблица ожидания (временная)
            c.execute('''
                CREATE TABLE IF NOT EXISTS waiting_messages (
                    user_id BIGINT PRIMARY KEY,
                    target_id BIGINT,
                    created_at INTEGER
                )
            ''')
            
            logger.info("✅ База данных инициализирована")
    
    def register_user(self, user_id, username, first_name):
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            
            c.execute('''
                INSERT INTO users 
                (user_id, username, first_name, created_at, last_active) 
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_active = EXCLUDED.last_active
            ''', (user_id, username, first_name, now, now))
    
    def get_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=RealDictCursor)
            c.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            row = c.fetchone()
            return row if row else None
    
    def is_user_blocked(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM blocked_users WHERE user_id = %s', (user_id,))
            return c.fetchone() is not None
    
    def block_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO blocked_users (user_id, blocked_at) 
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                blocked_at = EXCLUDED.blocked_at
            ''', (user_id, int(time.time())))
    
    def unblock_user(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM blocked_users WHERE user_id = %s', (user_id,))
    
    def update_last_active(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET last_active = %s WHERE user_id = %s', 
                     (int(time.time()), user_id))
    
    def increment_stat(self, user_id, field):
        if field not in ['messages_received', 'messages_sent', 'link_clicks']:
            return
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(f'UPDATE users SET {field} = {field} + 1 WHERE user_id = %s', 
                     (user_id,))
    
    def set_waiting(self, user_id, target_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO waiting_messages 
                (user_id, target_id, created_at) 
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                target_id = EXCLUDED.target_id,
                created_at = EXCLUDED.created_at
            ''', (user_id, target_id, int(time.time())))
    
    def get_waiting(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor(cursor_factory=RealDictCursor)
            c.execute('SELECT * FROM waiting_messages WHERE user_id = %s', (user_id,))
            row = c.fetchone()
            return row if row else None
    
    def clear_waiting(self, user_id):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM waiting_messages WHERE user_id = %s', (user_id,))
    
    def save_message(self, sender_id, receiver_id, message_type, text="", file_id=None):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO messages 
                (sender_id, receiver_id, message_type, text, file_id, timestamp) 
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (sender_id, receiver_id, message_type, text, file_id, int(time.time())))
            return c.fetchone()[0]
    
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
            
            # Общая статистика
            c.execute('SELECT COUNT(*) as total_users FROM users')
            total_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) as total_messages FROM messages')
            total_messages = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) as blocked_users FROM blocked_users')
            blocked_users = c.fetchone()[0]
            
            # Новые пользователи за 24 часа
            c.execute('SELECT COUNT(*) FROM users WHERE created_at > %s', 
                     (int(time.time()) - 86400,))
            new_users_24h = c.fetchone()[0]
            
            # Сообщения за 24 часа
            c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > %s', 
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
            c = conn.cursor(cursor_factory=RealDictCursor)
            c.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT %s', (limit,))
            return [row for row in c.fetchall()]
    
    def set_receive_messages(self, user_id, status):
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET receive_messages = %s WHERE user_id = %s',
                     (1 if status else 0, user_id))

# Инициализируем базу данных
db = Database()

# ====== УТИЛИТЫ ======
def format_time(timestamp):
    """Форматировать время"""
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
    """Сгенерировать ссылку для пользователя"""
    bot_username = bot.get_me().username
    return f"https://t.me/{bot_username}?start={user_id}"

def check_spam(user_id):
    """Проверка на спам"""
    current_time = time.time()
    last_time = last_message_time.get(user_id, 0)
    
    if current_time - last_time < ANTISPAM_INTERVAL:
        return False
    
    last_message_time[user_id] = current_time
    return True

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin=False):
    """Главное меню"""
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
    """Меню настроек"""
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
    """Админ-панель"""
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

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"START: user_id={user_id}, username=@{username}")
    
    # Инициализация БД при первом запуске
    try:
        db.init_database()
    except:
        pass
    
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
    
    # Обычный старт
    welcome_text = f"""🎉 <b>Добро пожаловать в Anony SMS!</b>

<b>🔐 Как это работает:</b>
1. Получи свою <b>уникальную ссылку</b>
2. Отправь её друзьям
3. Получай <b>анонимные сообщения</b>
4. Отвечай одним нажатием

<b>✨ Особенности:</b>
• Полная анонимность
• Можно отправлять текст, фото, видео
• QR-код для быстрого доступа
• Статистика полученных сообщений

<b>👇 Выбери действие:</b>"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, welcome_text, reply_markup=main_keyboard(is_admin))

def handle_link_click(clicker_id, target_id):
    """Обработка перехода по ссылке"""
    # Проверка антиспама
    if not check_spam(clicker_id):
        bot.send_message(clicker_id, "⏳ Подождите 10 секунд перед следующим сообщением.")
        return
    
    # Проверяем целевого пользователя
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, "❌ Пользователь не найден.")
        return
    
    # Проверяем, принимает ли сообщения
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, "❌ Этот пользователь отключил получение сообщений.")
        return
    
    # Сохраняем в ожидание
    db.set_waiting(clicker_id, target_id)
    
    # Увеличиваем счетчик переходов
    db.increment_stat(target_id, 'link_clicks')
    
    # Отправляем приглашение
    bot.send_message(
        clicker_id,
        f"💌 <b>Пиши анонимное сообщение для</b> {target_user['first_name']}!\n\n"
        f"Отправь текст, фото, видео или голосовое сообщение.\n"
        f"<i>Сообщение будет полностью анонимным!</i>",
        reply_markup=cancel_keyboard
    )

# ====== ОСНОВНОЙ ОБРАБОТЧИК СООБЩЕНИЙ ======
@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    """Обработка всех сообщений"""
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    # Пропускаем команды
    if message.text and message.text.startswith('/'):
        return
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        return
    
    # Обновляем активность
    db.update_last_active(user_id)
    
    # Обработка отмены
    if text == "❌ Отмена":
        db.clear_waiting(user_id)
        is_admin = user_id == ADMIN_ID
        bot.send_message(user_id, "❌ Отменено", reply_markup=main_keyboard(is_admin))
        return
    
    # Проверяем ожидание (отправка анонимки или поддержка)
    waiting = db.get_waiting(user_id)
    if waiting:
        if isinstance(waiting['target_id'], int):
            # Анонимное сообщение
            send_anonymous_message(user_id, waiting['target_id'], message)
        elif waiting['target_id'] == 'support':
            # Сообщение в поддержку
            send_to_support(user_id, message)
        return
    
    # Обработка кнопок главного меню
    if message_type == 'text':
        handle_text_button(user_id, text)

def handle_text_button(user_id, text):
    """Обработка нажатий на кнопки"""
    is_admin = user_id == ADMIN_ID
    
    if text == "📩 Моя ссылка":
        link = generate_link(user_id)
        bot.send_message(
            user_id,
            f"🔗 <b>Твоя уникальная ссылка:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"<i>Отправь её друзьям, чтобы получать анонимные сообщения!</i>",
            reply_markup=main_keyboard(is_admin)
        )
    
    elif text == "📊 Статистика":
        show_user_stats(user_id)
    
    elif text == "⚙️ Настройки":
        bot.send_message(
            user_id,
            "⚙️ <b>Настройки приватности</b>\n\n"
            "Управляй получением анонимных сообщений:",
            reply_markup=settings_keyboard()
        )
    
    elif text == "📱 QR-код":
        generate_qr_code(user_id)
    
    elif text == "ℹ️ Помощь":
        show_help(user_id)
    
    elif text == "🆘 Поддержка":
        db.set_waiting(user_id, 'support')
        bot.send_message(
            user_id,
            "🆘 <b>Поддержка</b>\n\n"
            "Напиши свой вопрос или проблему.\n"
            "Мы ответим в ближайшее время!",
            reply_markup=cancel_keyboard
        )
    
    elif text == "👑 Админ" and is_admin:
        bot.send_message(user_id, "👑 <b>Админ-панель</b>", reply_markup=admin_keyboard())
    
    elif text == "🔔 Вкл. сообщения":
        db.set_receive_messages(user_id, True)
        bot.send_message(user_id, "✅ <b>Приём сообщений включен!</b>", 
                        reply_markup=settings_keyboard())
    
    elif text == "🔕 Выкл. сообщения":
        db.set_receive_messages(user_id, False)
        bot.send_message(user_id, "✅ <b>Приём сообщений отключен!</b>", 
                        reply_markup=settings_keyboard())
    
    elif text == "📊 Моя статистика":
        show_user_stats(user_id)
    
    elif text == "⬅️ Назад":
        bot.send_message(user_id, "Главное меню:", 
                        reply_markup=main_keyboard(is_admin))
    
    # Админские команды
    elif is_admin:
        handle_admin_command(user_id, text)

def send_anonymous_message(sender_id, receiver_id, message):
    """Отправка анонимного сообщения"""
    try:
        # Проверка антиспама
        if not check_spam(sender_id):
            bot.send_message(sender_id, "⏳ Подождите 10 секунд перед следующим сообщением.")
            return
        
        # Проверяем получателя
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, "❌ Этот пользователь отключил получение сообщений.")
            db.clear_waiting(sender_id)
            bot.send_message(sender_id, "Главное меню:", 
                           reply_markup=main_keyboard(sender_id == ADMIN_ID))
            return
        
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
        
        message_id = db.save_message(
            sender_id, receiver_id, 
            message.content_type, 
            message.text or message.caption or "", 
            file_id
        )
        
        # Отправляем получателю
        caption = f"📨 <b>Новое анонимное сообщение!</b>\n\n"
        
        if message.content_type == 'text':
            bot.send_message(receiver_id, f"{caption}{message.text}")
        elif message.content_type == 'photo':
            bot.send_photo(receiver_id, file_id, 
                         caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'video':
            bot.send_video(receiver_id, file_id,
                         caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'audio':
            bot.send_audio(receiver_id, file_id,
                         caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'voice':
            bot.send_voice(receiver_id, file_id,
                         caption=f"{caption}{message.caption or ''}")
        elif message.content_type == 'document':
            bot.send_document(receiver_id, file_id,
                            caption=f"{caption}{message.caption or ''}")
        
        # Кнопка для ответа
        reply_markup = types.InlineKeyboardMarkup()
        reply_markup.add(
            types.InlineKeyboardButton(
                "💌 Ответить анонимно",
                url=generate_link(receiver_id)
            )
        )
        
        bot.send_message(receiver_id, "💬 Хочешь ответить?", reply_markup=reply_markup)
        
        # Обновляем статистику
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Уведомляем отправителя
        bot.send_message(
            sender_id,
            "✅ <b>Сообщение отправлено анонимно!</b>\n\n"
            "<i>Получатель не узнает, кто отправил это сообщение.</i>",
            reply_markup=main_keyboard(sender_id == ADMIN_ID)
        )
        
        # Логируем
        logger.info(f"ANON_MSG: from={sender_id}, to={receiver_id}, type={message.content_type}, id={message_id}")
        
        # Очищаем ожидание
        db.clear_waiting(sender_id)
        
        # Уведомляем админа
        try:
            admin_msg = f"📨 <b>Новое анонимное сообщение</b>\n"
            admin_msg += f"От: <code>{sender_id}</code>\n"
            admin_msg += f"Кому: <code>{receiver_id}</code>\n"
            admin_msg += f"Тип: {message.content_type}"
            bot.send_message(ADMIN_ID, admin_msg)
        except:
            pass
            
    except Exception as e:
        logger.error(f"Error sending anonymous message: {e}")
        bot.send_message(sender_id, "❌ Ошибка при отправке сообщения.")

def send_to_support(user_id, message):
    """Отправка сообщения в поддержку"""
    try:
        user = db.get_user(user_id)
        username = f"@{user['username']}" if user['username'] else "Без username"
        
        # Отправляем админу
        admin_msg = f"🆘 <b>Сообщение в поддержку</b>\n\n"
        admin_msg += f"👤 От: {user['first_name']}\n"
        admin_msg += f"📱 {username}\n"
        admin_msg += f"🆔 ID: <code>{user_id}</code>\n\n"
        
        if message.content_type == 'text':
            admin_msg += f"💬 <b>Сообщение:</b>\n{message.text}"
            bot.send_message(ADMIN_ID, admin_msg)
        else:
            bot.send_message(ADMIN_ID, admin_msg)
            if message.content_type == 'photo':
                bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                             caption=message.caption or "")
            elif message.content_type == 'video':
                bot.send_video(ADMIN_ID, message.video.file_id,
                             caption=message.caption or "")
            elif message.content_type == 'document':
                bot.send_document(ADMIN_ID, message.document.file_id,
                                caption=message.caption or "")
        
        # Подтверждаем пользователю
        bot.send_message(
            user_id,
            "✅ <b>Сообщение отправлено в поддержку!</b>\n\n"
            "Мы ответим вам в ближайшее время.",
            reply_markup=main_keyboard(user_id == ADMIN_ID)
        )
        
        # Логируем
        logger.info(f"SUPPORT: from={user_id}")
        
        # Очищаем ожидание
        db.clear_waiting(user_id)
        
    except Exception as e:
        logger.error(f"Error sending support message: {e}")
        bot.send_message(user_id, "❌ Ошибка при отправке сообщения в поддержку.")

def show_user_stats(user_id):
    """Показать статистику пользователя"""
    stats = db.get_user_stats(user_id)
    
    if not stats:
        bot.send_message(user_id, "❌ Данные не найдены.")
        return
    
    stats_text = f"""📊 <b>Твоя статистика</b>

<b>👤 Основное:</b>
• Сообщений получено: <b>{stats['messages_received']}</b>
• Сообщений отправлено: <b>{stats['messages_sent']}</b>
• Переходов по ссылке: <b>{stats['link_clicks']}</b>

<b>⏰ Активность:</b>
• Последний онлайн: {format_time(stats['last_active'])}
• Приём сообщений: {"✅ Включен" if stats['receive_messages'] else "❌ Выключен"}

<b>🔗 Твоя ссылка:</b>
<code>{generate_link(user_id)}</code>"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, stats_text, reply_markup=main_keyboard(is_admin))

def generate_qr_code(user_id):
    """Генерация QR-кода"""
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        
        bot.send_photo(
            user_id,
            photo=bio,
            caption=f"📱 <b>Твой QR-код</b>\n\n"
                   f"Ссылка: <code>{link}</code>\n\n"
                   f"<i>Покажи друзьям для быстрого перехода!</i>",
            reply_markup=main_keyboard(user_id == ADMIN_ID)
        )
    except Exception as e:
        logger.error(f"Error generating QR: {e}")
        bot.send_message(user_id, "❌ Ошибка при генерации QR-кода.")

def show_help(user_id):
    """Показать справку"""
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

<b>⚙️ Настройки:</b>
• Можно включить/выключить приём сообщений
• Просмотр статистики
• Генерация QR-кода

<b>🔒 Безопасность:</b>
• Все сообщения полностью анонимны
• Мы не сохраняем личные данные
• Можно заблокировать нежелательные сообщения

<b>🆘 Поддержка:</b>
Если есть вопросы — пиши в поддержку!"""
    
    is_admin = user_id == ADMIN_ID
    bot.send_message(user_id, help_text, reply_markup=main_keyboard(is_admin))

# ====== АДМИНСКИЕ ФУНКЦИИ ======
admin_modes = {}  # {admin_id: mode}

def handle_admin_command(admin_id, text):
    """Обработка админских команд"""
    
    if text == "📊 Общая статистика":
        show_admin_stats(admin_id)
    
    elif text == "📢 Рассылка":
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(
            admin_id,
            "📢 <b>Рассылка сообщения</b>\n\n"
            "Отправь сообщение (текст, фото, видео), "
            "и оно будет отправлено всем пользователям.",
            reply_markup=cancel_keyboard
        )
    
    elif text == "👥 Все пользователи":
        show_all_users(admin_id)
    
    elif text == "🚫 Заблокировать":
        admin_modes[admin_id] = 'block'
        bot.send_message(
            admin_id,
            "🚫 <b>Блокировка пользователя</b>\n\n"
            "Введите ID пользователя для блокировки:",
            reply_markup=cancel_keyboard
        )
    
    elif text == "✅ Разблокировать":
        admin_modes[admin_id] = 'unblock'
        bot.send_message(
            admin_id,
            "✅ <b>Разблокировка пользователя</b>\n\n"
            "Введите ID пользователя для разблокировки:",
            reply_markup=cancel_keyboard
        )
    
    # Обработка ввода в режиме админа
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
    """Показать статистику для админа"""
    stats = db.get_admin_stats()
    
    stats_text = f"""👑 <b>Статистика бота</b>

<b>📊 Основные метрики:</b>
• Всего пользователей: <b>{stats['total_users']}</b>
• Всего сообщений: <b>{stats['total_messages']}</b>
• Заблокированных: <b>{stats['blocked_users']}</b>

<b>📈 За последние 24 часа:</b>
• Новых пользователей: <b>{stats['new_users_24h']}</b>
• Отправлено сообщений: <b>{stats['messages_24h']}</b>"""
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard())

def broadcast_message(admin_id, text):
    """Рассылка сообщения всем пользователям"""
    users = db.get_all_users()
    sent_count = 0
    failed_count = 0
    
    for user in users:
        try:
            bot.send_message(user['user_id'], text, parse_mode="HTML")
            sent_count += 1
            time.sleep(0.05)  # Антифлуд
        except:
            failed_count += 1
    
    bot.send_message(
        admin_id,
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"• Отправлено: <b>{sent_count}</b>\n"
        f"• Не отправлено: <b>{failed_count}</b>",
        reply_markup=admin_keyboard()
    )
    
    logger.info(f"BROADCAST: admin={admin_id}, sent={sent_count}, failed={failed_count}")

def show_all_users(admin_id):
    """Показать всех пользователей"""
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
        response += f"\n📨 {user['messages_received']} получ. | 📤 {user['messages_sent']} отправ.\n\n"
    
    bot.send_message(admin_id, response, reply_markup=admin_keyboard())

def block_user(admin_id, target_id):
    """Блокировка пользователя"""
    try:
        db.block_user(target_id)
        bot.send_message(
            admin_id,
            f"✅ Пользователь <code>{target_id}</code> заблокирован.",
            reply_markup=admin_keyboard()
        )
        logger.info(f"BLOCK: admin={admin_id}, target={target_id}")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

def unblock_user(admin_id, target_id):
    """Разблокировка пользователя"""
    try:
        db.unblock_user(target_id)
        bot.send_message(
            admin_id,
            f"✅ Пользователь <code>{target_id}</code> разблокирован.",
            reply_markup=admin_keyboard()
        )
        logger.info(f"UNBLOCK: admin={admin_id}, target={target_id}")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Ошибка: {e}")

# ====== ВЕБХУК ДЛЯ RENDER ======
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

# ====== ЗАПУСК ======
def create_tables():
    """Создание таблиц при запуске"""
    try:
        db.init_database()
        logger.info("✅ Таблицы созданы/проверены")
    except Exception as e:
        logger.error(f"Ошибка создания таблиц: {e}")

if __name__ == '__main__':
    logger.info("=== Бот запущен ===")
    
    # Создаем таблицы при запуске
    create_tables()
    
    try:
        # Настройка вебхука для Render
        if WEBHOOK_HOST:
            logger.info(f"Настройка вебхука для {WEBHOOK_HOST}")
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=f"{WEBHOOK_HOST}/webhook")
            logger.info("✅ Вебхук настроен")
            
            # Запуск Flask сервера
            app.run(host='0.0.0.0', port=PORT, debug=False)
        else:
            # Локальный запуск (без вебхука)
            logger.info("Локальный запуск (polling)")
            bot.remove_webhook()
            bot.polling(none_stop=True, interval=0, timeout=20)
            
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
