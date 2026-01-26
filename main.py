import telebot
from flask import Flask, request
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = '8388985383:AAHv9ZFslSAanH_465zonkNPp02SecqI-Ik'
WEBHOOK_URL = 'https://songaura.onrender.com/webhook'

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

def make_keyboard():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton("👩 Девушка", callback_data="girl"),
        InlineKeyboardButton("👨 Мужчина", callback_data="boy")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Выберите, кто вы:", reply_markup=make_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == "girl":
        text = "ДЕВУШКИ ТУПЫЕ"
    else:
        text = "У МУЖЧИН ЕСТЬ ПРАВА. И ОНИ НЕ ТУПЫЕ В ОТЛИЧИИ НЕКОТОРЫХ"
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=text
    )

@app.route('/webhook', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

@app.route('/')
def home():
    return 'Бот работает'

if __name__ == '__main__':
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host='0.0.0.0', port=1000)
