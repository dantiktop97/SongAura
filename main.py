import os
import time
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from telebot import TeleBot, types, apihelper
import qrcode
from io import BytesIO
import json

# Импорт модулей
from config import *
from database import Database
from utils import generate_link, format_time, get_user_display_name, anti_spam

# ====== НАСТРОЙКА ЛОГГИРОВАНИЯ ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ ======
bot = TeleBot(TOKEN, parse_mode="HTML", threaded=False)
app = Flask(__name__)
db = Database()

# Кэш для ускорения
user_cache = {}
blocked_cache = set()

# ====== КЛАВИАТУРЫ ======
def main_keyboard(user_id=None):
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
    
    # Добавляем админ-панель если админ
    if user_id and user_id == ADMIN_ID:
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
        types.KeyboardButton("📜 Логи"),
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
    
    # Логируем начало
    logger.info(f"START: user_id={user_id}, username=@{username}, first_name={first_name}")
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, "🚫 Вы заблокированы в этом боте.")
        return
    
    # Регистрируем/обновляем пользователя
    db.register_user(user_id, username, first_name)
    
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
    
    bot.send_message(user_id, welcome_text, reply_markup=main_keyboard(user_id))
    
    # Уведомляем админа о новом пользователе
    if user_id != ADMIN_ID:
        try:
            admin_msg = f"👤 <b>Новый пользователь</b>\nID: <code>{user_id}</code>\n"
            admin_msg += f"Имя: {first_name}\n"
            admin_msg += f"Username: @{username}" if username else "Без username"
            bot.send_message(ADMIN_ID, admin_msg)
        except:
            pass

def handle_link_click(clicker_id, target_id):
    """Обработка перехода по ссылке"""
    # Проверяем антиспам
    if not anti_spam(clicker_id):
        bot.send_message(clicker_id, "⏳ Подождите 10 секунд перед следующим сообщением.")
        return
    
    # Проверяем, существует ли целевой пользователь
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, "❌ Пользователь не найден.")
        return
    
    # Проверяем, принимает ли целевой пользователь сообщения
    if not target_user.get('receive_messages', True):
        bot.send_message(clicker_id, "❌ Этот пользователь отключил получение сообщений.")
        return
    
    # Сохраняем в ожидание
    db.set_waiting_message(clicker_id, target_id)
    
    # Увеличиваем счетчик переходов
    db.increment_stat(target_id, 'link_clicks')
    
    # Отправляем приглашение написать
    bot.send_message(
        clicker_id,
        f"💌 <b>Пиши анонимное сообщение для</b> {target_user['first_name']}!\n\n"
        f"Отправь текст, фото, видео или голосовое сообщение.\n"
        f"<i>Сообщение будет полностью анонимным!</i>",
        reply_markup=cancel_keyboard
    )
    
    # Логируем переход
    logger.info(f"LINK_CLICK: from={clicker_id}, to={target_id}")

# ====== ОБРАБОТЧИК СООБЩЕНИЙ ======
@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    """Обработка всех сообщений"""
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    # Пропускаем служебные команды
    if message.text and message.text.startswith('/'):
        return
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        return
    
    # Обновляем активность пользователя
    db.update_last_active(user_id)
    
    # Обработка отмены
    if text == "❌ Отмена":
        db.clear_waiting_message(user_id)
        bot.send_message(user_id, "❌ Отменено", reply_markup=main_keyboard(user_id))
        return
    
    # Проверяем, ожидает ли пользователь ввода (отправка анонимки)
    waiting_data = db.get_waiting_message(user_id)
    if waiting_data:
        target_id = waiting_data['target_id']
        send_anonymous_message(user_id, target_id, message)
        return
    
    # Обработка кнопок главного меню
    if message_type == 'text':
        handle_text_button(user_id, text)

def handle_text_button(user_id, text):
    """Обработка нажатий на кнопки"""
    
    if text == "📩 Моя ссылка":
        link = generate_link(bot.get_me().username, user_id)
        bot.send_message(
            user_id,
            f"🔗 <b>Твоя уникальная ссылка:</b>\n\n"
            f"<code>{link}</code>\n\n"
            f"<i>Отправь её друзьям, чтобы получать анонимные сообщения!</i>",
            reply_markup=main_keyboard(user_id)
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
        start_support(user_id)
    
    elif text == "👑 Админ" and user_id == ADMIN_ID:
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
        bot.send_message(user_id, "Главное меню:", reply_markup=main_keyboard(user_id))
    
    # Админские команды
    elif user_id == ADMIN_ID:
        handle_admin_commands(user_id, text)

def send_anonymous_message(sender_id, receiver_id, message):
    """Отправка анонимного сообщения"""
    try:
        # Проверяем антиспам
        if not anti_spam(sender_id):
            bot.send_message(sender_id, "⏳ Подождите 10 секунд перед следующим сообщением.")
            return
        
        # Проверяем, принимает ли получатель сообщения
        receiver = db.get_user(receiver_id)
        if not receiver or not receiver.get('receive_messages', True):
            bot.send_message(sender_id, "❌ Этот пользователь отключил получение сообщений.")
            db.clear_waiting_message(sender_id)
            bot.send_message(sender_id, "Главное меню:", reply_markup=main_keyboard(sender_id))
            return
        
        # Сохраняем сообщение в БД
        message_data = {
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'message_type': message.content_type,
            'text': message.text or message.caption or "",
            'file_id': None
        }
        
        # Сохраняем file_id для медиа
        if message.content_type == 'photo':
            message_data['file_id'] = message.photo[-1].file_id
        elif message.content_type in ['video', 'audio', 'voice', 'document']:
            message_data['file_id'] = getattr(message, message.content_type).file_id
        
        db.save_message(message_data)
        
        # Отправляем получателю
        caption = f"📨 <b>Новое анонимное сообщение!</b>\n\n"
        
        if message.content_type == 'text':
            bot.send_message(receiver_id, f"{caption}{message.text}")
        else:
            # Отправляем медиа с подписью
            if message.content_type == 'photo':
                bot.send_photo(receiver_id, message.photo[-1].file_id, 
                             caption=f"{caption}{message.caption or ''}")
            elif message.content_type == 'video':
                bot.send_video(receiver_id, message.video.file_id,
                             caption=f"{caption}{message.caption or ''}")
            elif message.content_type == 'audio':
                bot.send_audio(receiver_id, message.audio.file_id,
                             caption=f"{caption}{message.caption or ''}")
            elif message.content_type == 'voice':
                bot.send_voice(receiver_id, message.voice.file_id,
                             caption=f"{caption}{message.caption or ''}")
            elif message.content_type == 'document':
                bot.send_document(receiver_id, message.document.file_id,
                                caption=f"{caption}{message.caption or ''}")
        
        # Кнопка для ответа
        reply_markup = types.InlineKeyboardMarkup()
        reply_markup.add(
            types.InlineKeyboardButton(
                "💌 Ответить анонимно",
                url=f"https://t.me/{bot.get_me().username}?start={receiver_id}"
            )
        )
        
        bot.send_message(receiver_id, "💬 Хочешь ответить?", reply_markup=reply_markup)
        
        # Обновляем статистику
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Уведомляем отправителя об успехе
        bot.send_message(
            sender_id,
            "✅ <b>Сообщение отправлено анонимно!</b>\n\n"
            "<i>Получатель не узнает, кто отправил это сообщение.</i>",
            reply_markup=main_keyboard(sender_id)
        )
        
        # Логируем отправку
        logger.info(f"ANON_MSG: from={sender_id}, to={receiver_id}, type={message.content_type}")
        
        # Очищаем ожидание
        db.clear_waiting_message(sender_id)
        
        # Уведомляем админа
        if ADMIN_ID:
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

def show_user_stats(user_id):
    """Показать статистику пользователя"""
    user_data = db.get_user_stats(user_id)
    
    if not user_data:
        bot.send_message(user_id, "❌ Данные не найдены.")
        return
    
    stats_text = f"""📊 <b>Твоя статистика</b>

<b>👤 Основное:</b>
• Сообщений получено: <b>{user_data['messages_received']}</b>
• Сообщений отправлено: <b>{user_data['messages_sent']}</b>
• Переходов по ссылке: <b>{user_data['link_clicks']}</b>

<b>⏰ Активность:</b>
• Последний онлайн: {format_time(user_data['last_active'])}
• Приём сообщений: {"✅ Включен" if user_data['receive_messages'] else "❌ Выключен"}

<b>🔗 Твоя ссылка:</b>
<code>https://t.me/{bot.get_me().username}?start={user_id}</code>"""
    
    bot.send_message(user_id, stats_text, reply_markup=main_keyboard(user_id))

def generate_qr_code(user_id):
    """Генерация QR-кода"""
    link = generate_link(bot.get_me().username, user_id)
    
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
            reply_markup=main_keyboard(user_id)
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
    
    bot.send_message(user_id, help_text, reply_markup=main_keyboard(user_id))

def start_support(user_id):
    """Начать диалог с поддержкой"""
    db.set_waiting_message(user_id, 'support')
    bot.send_message(
        user_id,
        "🆘 <b>Поддержка</b>\n\n"
        "Напиши свой вопрос или проблему.\n"
        "Мы ответим в ближайшее время!",
        reply_markup=cancel_keyboard
    )

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_commands(admin_id, text):
    """Обработка админских команд"""
    
    if text == "📊 Общая статистика":
        show_admin_stats(admin_id)
    
    elif text == "📢 Рассылка":
        db.set_admin_mode(admin_id, 'broadcast')
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
        db.set_admin_mode(admin_id, 'block')
        bot.send_message(
            admin_id,
            "🚫 <b>Блокировка пользователя</b>\n\n"
            "Введите ID пользователя для блокировки:",
            reply_markup=cancel_keyboard
        )
    
    elif text == "✅ Разблокировать":
        db.set_admin_mode(admin_id, 'unblock')
        bot.send_message(
            admin_id,
            "✅ <b>Разблокировка пользователя</b>\n\n"
            "Введите ID пользователя для разблокировки:",
            reply_markup=cancel_keyboard
        )
    
    elif text == "📜 Логи":
        send_logs(admin_id)
    
    # Обработка ввода в режиме админа
    elif db.get_admin_mode(admin_id):
        mode = db.get_admin_mode(admin_id)
        
        if mode == 'broadcast':
            broadcast_message(admin_id, text)
        
        elif mode == 'block' and text.isdigit():
            block_user(admin_id, int(text))
        
        elif mode == 'unblock' and text.isdigit():
            unblock_user(admin_id, int(text))

def show_admin_stats(admin_id):
    """Показать статистику для админа"""
    stats = db.get_admin_stats()
    
    if not stats:
        bot.send_message(admin_id, "❌ Нет данных.")
        return
    
    # Форматируем время
    now = time.time()
    today_users = sum(1 for u in stats['recent_users'] if now - u['last_active'] < 86400)
    
    stats_text = f"""👑 <b>Статистика бота</b>

<b>📊 Основные метрики:</b>
• Всего пользователей: <b>{stats['total_users']}</b>
• Активных сегодня: <b>{today_users}</b>
• Всего сообщений: <b>{stats['total_messages']}</b>
• Заблокированных: <b>{stats['blocked_users']}</b>

<b>📈 За последние 24 часа:</b>
• Новых пользователей: <b>{stats['new_users_24h']}</b>
• Отправлено сообщений: <b>{stats['messages_24h']}</b>

<b>👤 Топ отправителей:</b>"""
    
    for i, user in enumerate(stats['top_senders'][:5], 1):
        stats_text += f"\n{i}. ID: <code>{user['user_id']}</code> - {user['sent']} сообщ."
    
    stats_text += "\n\n<b>👤 Топ получателей:</b>"
    for i, user in enumerate(stats['top_receivers'][:5], 1):
        stats_text += f"\n{i}. ID: <code>{user['user_id']}</code> - {user['received']} сообщ."
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard())

def broadcast_message(admin_id, text):
    """Рассылка сообщения всем пользователям"""
    users = db.get_all_users()
    sent_count = 0
    failed_count = 0
    
    # Отправляем сообщение
    for user in users:
        try:
            bot.send_message(user['user_id'], text, parse_mode="HTML")
            sent_count += 1
            time.sleep(0.05)  # Антифлуд
        except Exception as e:
            failed_count += 1
    
    # Уведомляем админа
    bot.send_message(
        admin_id,
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"• Отправлено: <b>{sent_count}</b>\n"
        f"• Не отправлено: <b>{failed_count}</b>",
        reply_markup=admin_keyboard()
    )
    
    # Очищаем режим админа
    db.clear_admin_mode(admin_id)
    
    # Логируем рассылку
    logger.info(f"BROADCAST: admin={admin_id}, sent={sent_count}, failed={failed_count}")

def show_all_users(admin_id):
    """Показать всех пользователей"""
    users = db.get_all_users(limit=50)
    
    if not users:
        bot.send_message(admin_id, "❌ Нет пользователей.")
        return
    
    response = f"👥 <b>Последние {len(users)} пользователей:</b>\n\n"
    
    for user in users:
        status = "✅" if user.get('receive_messages', True) else "🔕"
        response += f"{status} <code>{user['user_id']}</code> - {user['first_name']}\n"
        if user.get('username'):
            response += f"  @{user['username']}\n"
        response += f"  📨 {user.get('messages_received', 0)} получ.\n\n"
    
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
    
    db.clear_admin_mode(admin_id)

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
    
    db.clear_admin_mode(admin_id)

def send_logs(admin_id):
    """Отправить логи админу"""
    try:
        with open('logs/bot.log', 'rb') as f:
            bot.send_document(admin_id, f, caption="📜 Логи бота")
    except Exception as e:
        bot.send_message(admin_id, f"❌ Не удалось отправить логи: {e}")

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
if __name__ == '__main__':
    # Создаем папку для логов
    os.makedirs('logs', exist_ok=True)
    
    # Проверяем соединение с БД
    db.test_connection()
    
    logger.info("=== Бот запущен ===")
    
    if os.environ.get('RENDER'):
        # Настройка для Render
        bot.remove_webhook()
        time.sleep(1)
        webhook_url = f"{os.environ.get('RENDER_EXTERNAL_URL')}/webhook"
        bot.set_webhook(url=webhook_url)
        logger.info(f"Webhook set to: {webhook_url}")
        
        # Запускаем Flask сервер
        port = int(os.environ.get('PORT', 10000))
        app.run(host='0.0.0.0', port=port)
    else:
        # Локальный запуск
        bot.remove_webhook()
        bot.polling(none_stop=True, interval=0, timeout=20)
