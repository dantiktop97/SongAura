# main.py — YouTube → MP3 бот
# aiogram 3.x + aiohttp + healthcheck
# Render Web Service совместим

import os, asyncio, logging
from aiohttp import web, ClientSession
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from youtubesearchpython import VideosSearch

# === ENV ===
TOKEN = os.getenv("PLAY")  # ← заменено
PORT = int(os.getenv("PORT", "8000"))

# === Bot ===
bot = Bot(TOKEN)
dp = Dispatcher()

# === YouTube Search ===
async def search_youtube(query: str) -> str:
    search = VideosSearch(query, limit=1)
    result = await search.next()
    video_id = result["result"][0]["id"]
    return video_id

# === MP3 API ===
async def get_mp3_url(video_id: str) -> str:
    url = f"https://api.download-lagu-mp3.com/@api/json/mp3/{video_id}"
    async with ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            for item in data.get("vidInfo", {}).values():
                if item.get("bitrate") == 128:
                    return "https:" + item["dloadUrl"]
    return None

# === Bot Handler ===
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("🎵 Отправь название трека, и я пришлю MP3 с YouTube.")

@dp.message()
async def music(msg: Message):
    query = msg.text.strip()
    await msg.answer(f"🔍 Ищу: {query}")
    try:
        video_id = await search_youtube(query)
        mp3_url = await get_mp3_url(video_id)
        if mp3_url:
            await bot.send_audio(chat_id=msg.chat.id, audio=mp3_url, title=query)
        else:
            await msg.answer("⚠️ Не удалось получить MP3.")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")

# === Healthcheck ===
async def health(request): return web.Response(text="Bot is running")
async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# === Run ===
async def main():
    asyncio.create_task(start_web())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
