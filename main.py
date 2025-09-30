# main.py — YouTube -> MP3 bot (исправлено: aiohttp без proxies)
# aiogram 3.22.0, aiohttp 3.9.x, youtube-search-python
import os
import asyncio
import logging
from aiohttp import web, ClientSession, ClientTimeout
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from youtubesearchpython import VideosSearch

# ENV
TOKEN = os.getenv("PLAY")
PORT = int(os.getenv("PORT", "8000"))

if not TOKEN:
    raise RuntimeError("Environment variable PLAY (bot token) is required")

# Bot
bot = Bot(TOKEN)
dp = Dispatcher()

# YouTube search
async def search_youtube(query: str) -> str:
    search = VideosSearch(query, limit=1)
    result = await search.next()
    items = result.get("result", [])
    if not items:
        raise ValueError("Ничего не найдено на YouTube")
    return items[0]["id"]

# Get mp3 url from API (download-lagu-mp3.com)
async def get_mp3_url(video_id: str, session: ClientSession) -> str | None:
    api_url = f"https://api.download-lagu-mp3.com/@api/json/mp3/{video_id}"
    timeout = ClientTimeout(total=20)
    try:
        async with session.get(api_url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
    except asyncio.TimeoutError:
        return None
    except Exception:
        return None

    vid_info = data.get("vidInfo") or {}
    # Prefer 128 or highest available
    best = None
    best_bitrate = -1
    for v in vid_info.values():
        try:
            br = int(v.get("bitrate") or 0)
        except Exception:
            br = 0
        if br > best_bitrate:
            best_bitrate = br
            best = v
    if not best:
        return None
    dload = best.get("dloadUrl")
    if not dload:
        return None
    # API sometimes returns protocol-relative URL ("//..."), ensure full
    if dload.startswith("//"):
        return "https:" + dload
    if dload.startswith("http"):
        return dload
    return "https://" + dload.lstrip("/")

# Handler
@dp.message(Command("start"))
async def cmd_start(msg: Message):
    await msg.answer("🎵 Отправь название трека, и я постараюсь прислать MP3 (через внешний API).")

@dp.message()
async def on_message(msg: Message):
    query = (msg.text or "").strip()
    if not query:
        await msg.answer("Напиши название трека или исполнителя.")
        return

    status = await msg.answer(f"🔍 Ищу: {query}")
    try:
        video_id = await search_youtube(query)
    except Exception as e:
        await status.edit_text(f"❌ Ошибка поиска: {e}")
        return

    # reuse single session for requests
    async with ClientSession() as session:
        mp3_url = await get_mp3_url(video_id, session)

    if not mp3_url:
        await status.edit_text("⚠️ Не удалось получить MP3 с внешнего API.")
        return

    # Попробуем отправить как URL (Telegram поддерживает отправку по прямой ссылке)
    try:
        await bot.send_audio(chat_id=msg.chat.id, audio=mp3_url, title=query)
        await status.delete()
    except Exception as e:
        # fallback: просто отправляем ссылку
        await status.edit_text(f"Не удалось отправить аудио напрямую. Ссылка на MP3:\n{mp3_url}")

# Healthcheck web
async def health(request):
    return web.Response(text="Bot is running")

async def start_web():
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

# Run
async def main():
    asyncio.create_task(start_web())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
