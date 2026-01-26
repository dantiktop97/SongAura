import logging
import sys
import time
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from flask import Flask, request

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TOKEN = '8388985383:AAHv9ZFslSAanH_465zonkNPp02SecqI-Ik'
WEBHOOK_HOST = 'https://songaura.onrender.com'
PORT = 1000

# Flask приложение
flask_app = Flask(__name__)
application = None

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [
            InlineKeyboardButton("👩 Девушка", callback_data='woman'),
            InlineKeyboardButton("👨 Мужчина", callback_data='man')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Привет! Выберите, кто вы:",
        reply_markup=reply_markup
    )

# Обработчик нажатий на кнопки
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == 'woman':
        response = "ДЕВУШКИ ТУПЫЕ"
    elif query.data == 'man':
        response = "У МУЖЧИН ЕСТЬ ПРАВА. И ОНИ НЕ ТУПЫЕ В ОТЛИЧИИ НЕКОТОРЫХ"
    else:
        response = "Ошибка выбора"
    
    await query.edit_message_text(text=response)

# Обработчик ошибок
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Ошибка: {context.error}")

# Flask маршрут для webhook
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    if request.method == "POST":
        update = Update.de_json(request.get_json(force=True), application.bot)
        application.update_queue.put(update)
    return 'ok'

# Flask маршрут для проверки работоспособности
@flask_app.route('/')
def index():
    return '🤖 Бот работает! Отправьте /start в Telegram'

def setup_bot():
    global application
    
    application = Application.builder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_error_handler(error_handler)
    
    return application

def main():
    global application
    
    # Настройка бота
    application = setup_bot()
    
    # Настройка webhook
    logger.info(f"🌐 Настройка webhook для {WEBHOOK_HOST}")
    
    try:
        # Удаляем старый webhook
        application.bot.delete_webhook()
        time.sleep(1)
        logger.info("✅ Старый webhook удален")
    except Exception as e:
        logger.warning(f"Ошибка удаления вебхука: {e}")
    
    # Устанавливаем новый webhook
    webhook_url = f"{WEBHOOK_HOST}/webhook"
    application.bot.set_webhook(
        url=webhook_url,
        drop_pending_updates=True
    )
    logger.info(f"✅ Webhook установлен: {webhook_url}")
    
    # Запускаем Flask сервер
    logger.info(f"🚀 Запуск сервера на порту {PORT}")
    flask_app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False,
        use_reloader=False
    )

if __name__ == '__main__':
    main()
