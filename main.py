import os
import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Конфигурация
TOKEN = '8388985383:AAHv9ZFslSAanH_465zonkNPp02SecqI-Ik'
WEBHOOK_URL = 'https://songaura.onrender.com'
PORT = 1000

# Создаем бота и Flask приложение
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# Создаем инлайн-кнопки
def create_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("👩 Девушка", callback_data='woman'),
        InlineKeyboardButton("👨 Мужчина", callback_data='man')
    )
    return keyboard

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "Привет! Выберите, кто вы:",
        reply_markup=create_keyboard()
    )

# Обработчик нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == 'woman':
        response = "ДЕВУШКИ ТУПЫЕ"
    elif call.data == 'man':
        response = "У МУЖЧИН ЕСТЬ ПРАВА. И ОНИ НЕ ТУПЫЕ В ОТЛИЧИИ НЕКОТОРЫХ"
    else:
        response = "Ошибка выбора"
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=response
    )

# Flask маршрут для webhook
@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

# Flask маршрут для проверки
@app.route('/')
def index():
    return '✅ Бот работает! Отправьте /start в Telegram'

# Установка webhook
@app.before_first_request
def setup_webhook():
    bot.remove_webhook()
    bot.set_webhook(url=f'{WEBHOOK_URL}/webhook')

# Запуск приложения
if __name__ == '__main__':
    print("🤖 Бот запускается...")
    print(f"🌐 Webhook URL: {WEBHOOK_URL}/webhook")
    
    # Удаляем старый webhook и устанавливаем новый
    bot.remove_webhook()
    bot.set_webhook(url=f'{WEBHOOK_URL}/webhook')
    
    # Запускаем Flask сервер
    app.run(
        host='0.0.0.0',
        port=PORT,
        debug=False
    )
