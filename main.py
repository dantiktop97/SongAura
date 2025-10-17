from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.utils import executor
import aiohttp
import os
from datetime import datetime
from aiohttp import web
import asyncio

BOT_TOKEN = os.getenv("AVTO")
CHANNEL_USERNAME = "vzref2"
REF_LINK = "https://t.me/Hshzgsbot?start=7549204023"
ADMIN_CHANNEL_ID = -1003079638308

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

@dp.message_handler(commands=["start"])
async def handle_start(message: Message):
    keyboard = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("📢 Перейти в канал", url=f"https://t.me/{CHANNEL_USERNAME}"),
        InlineKeyboardButton("✅ Проверить подписку", callback_data="check_sub")
    )
    await message.answer("👋 Добро пожаловать. Подпишись на канал и нажми кнопку ниже:", reply_markup=keyboard)

    user = message.from_user
    username = f"@{user.username}" if user.username else user.full_name
    user_id = user.id
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")

    report = f"""👤 Новый пользователь
🧑 Username: {username}
🆔 ID: {user_id}
🕒 Время: {timestamp}"""
    await bot.send_message(ADMIN_CHANNEL_ID, report)

@dp.callback_query_handler(lambda c: c.data == "check_sub")
async def check_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id=@{CHANNEL_USERNAME}&user_id={user_id}"
        ) as resp:
            data = await resp.json()
            status = data.get("result", {}).get("status", "")
            if status in ["member", "creator", "administrator"]:
                keyboard = InlineKeyboardMarkup().add(
                    InlineKeyboardButton("🚀 Перейти к авто-рассылке", url=REF_LINK)
                )
                await callback.message.answer("📣 Тут тебя уже ждёт авто-рассылка", reply_markup=keyboard)
            else:
                await callback.message.answer("❌ Подписка не найдена. Подпишись и нажми ещё раз.")

# --- минимальный HTTP-сервер для Render healthcheck ---
async def handle_health(request):
    return web.Response(text="ok")

def run_webserver(loop):
    app = web.Application()
    app.router.add_get("/", handle_health)
    port = int(os.getenv("PORT", "8000"))
    runner = web.AppRunner(app)
    async def _run():
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
    loop.create_task(_run())

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    run_webserver(loop)
    executor.start_polling(dp, loop=loop)
