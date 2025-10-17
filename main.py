import os
import asyncio
import json
from datetime import datetime
from aiohttp import web, ClientSession

BOT_TOKEN = os.getenv("AVTO")
CHANNEL_USERNAME = "vzref2"
REF_LINK = "https://t.me/Hshzgsbot?start=7549204023"
ADMIN_CHANNEL_ID = "-1003079638308"

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_INTERVAL = 1.0
LONG_POLL_TIMEOUT = 30

async def send_method(session: ClientSession, method: str, payload: dict):
    url = f"{API_URL}/{method}"
    async with session.post(url, json=payload, timeout=LONG_POLL_TIMEOUT + 10) as resp:
        return await resp.json()

def build_start_keyboard():
    keyboard = {
        "inline_keyboard": [
            [{"text": "📢 Перейти в канал", "url": f"https://t.me/{CHANNEL_USERNAME}"}],
            [{"text": "✅ Проверить подписку", "callback_data": "check_sub"}]
        ]
    }
    return keyboard

async def handle_update(session: ClientSession, update: dict):
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        if text and text.strip().startswith("/start"):
            # reply to user
            payload = {
                "chat_id": chat_id,
                "text": "👋 Добро пожаловать. Подпишись на канал и нажми кнопку ниже:",
                "reply_markup": build_start_keyboard()
            }
            await send_method(session, "sendMessage", payload)

            # send report to admin channel
            user = msg.get("from", {})
            username = f"@{user.get('username')}" if user.get("username") else f"{user.get('first_name','')}".strip()
            user_id = user.get("id")
            timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
            report = (
                "👤 Новый пользователь\n"
                f"🧑 Username: {username}\n"
                f"🆔 ID: {user_id}\n"
                f"🕒 Время: {timestamp}"
            )
            await send_method(session, "sendMessage", {"chat_id": ADMIN_CHANNEL_ID, "text": report})
    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        from_user = cb.get("from", {})
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        if data == "check_sub":
            user_id = from_user.get("id")
            # getChatMember
            async with session.get(f"{API_URL}/getChatMember", params={"chat_id": f"@{CHANNEL_USERNAME}", "user_id": user_id}) as resp:
                info = await resp.json()
            status = info.get("result", {}).get("status", "")
            if status in ["member", "creator", "administrator"]:
                payload = {
                    "chat_id": chat_id,
                    "text": "📣 Тут тебя уже ждёт авто-рассылка",
                    "reply_markup": {"inline_keyboard": [[{"text": "🚀 Перейти к авто-рассылке", "url": REF_LINK}]]}
                }
                await send_method(session, "sendMessage", payload)
            else:
                await send_method(session, "sendMessage", {"chat_id": chat_id, "text": "❌ Подписка не найдена. Подпишись и нажми ещё раз."})
            # answerCallbackQuery to remove loading
            await send_method(session, "answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

async def poll_loop():
    offset = 0
    async with ClientSession() as session:
        while True:
            try:
                params = {"timeout": LONG_POLL_TIMEOUT, "offset": offset, "limit": 50}
                async with session.get(f"{API_URL}/getUpdates", params=params, timeout=LONG_POLL_TIMEOUT + 10) as resp:
                    data = await resp.json()
                for upd in data.get("result", []):
                    offset = max(offset, upd.get("update_id", 0) + 1)
                    await handle_update(session, upd)
            except Exception:
                await asyncio.sleep(1)
            await asyncio.sleep(POLL_INTERVAL)

async def healthcheck(request):
    return web.Response(text="ok")

async def run():
    app = web.Application()
    app.router.add_get("/", healthcheck)
    port = int(os.getenv("PORT", "8000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    await poll_loop()

if __name__ == "__main__":
    asyncio.run(run())
