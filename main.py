import os
import asyncio
import json
from datetime import datetime
from aiohttp import web, ClientSession, ClientTimeout

BOT_TOKEN = os.getenv("AVTO")
CHANNEL_USERNAME = "vzref2"
REF_LINK = "https://t.me/Hshzgsbot?start=7549204023"
ADMIN_CHANNEL_ID = -1003079638308  # обязательно число, не строка

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_INTERVAL = 1.0
LONG_POLL_TIMEOUT = 30
CLIENT_TIMEOUT = ClientTimeout(total=LONG_POLL_TIMEOUT + 20)

session: ClientSession | None = None  # глобальная сессия

async def send_method(method: str, payload: dict):
    url = f"{API_URL}/{method}"
    try:
        async with session.post(url, json=payload, timeout=CLIENT_TIMEOUT) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except Exception:
                data = {"ok": False, "raw": text}
            print(f"{method} request payload: {payload}")
            print(f"{method} response: {data}")
            return data
    except Exception as e:
        print(f"{method} exception: {repr(e)}")
        return {"ok": False, "error": str(e)}

def build_start_keyboard():
    return {
        "inline_keyboard": [
            [{"text": "📢 Перейти в канал", "url": f"https://t.me/{CHANNEL_USERNAME}"}],
            [{"text": "✅ Проверить подписку", "callback_data": "check_sub"}]
        ]
    }

async def handle_update(update: dict):
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        if text and text.strip().startswith("/start"):
            payload = {
                "chat_id": chat_id,
                "text": "👋 Добро пожаловать. Подпишись на канал и нажми кнопку ниже:",
                "reply_markup": build_start_keyboard()
            }
            await send_method("sendMessage", payload)

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
            await send_method("sendMessage", {"chat_id": ADMIN_CHANNEL_ID, "text": report})

    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        from_user = cb.get("from", {})
        message = cb.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        if data == "check_sub":
            user_id = from_user.get("id")
            async with session.get(f"{API_URL}/getChatMember", params={"chat_id": f"@{CHANNEL_USERNAME}", "user_id": user_id}, timeout=CLIENT_TIMEOUT) as resp:
                info_text = await resp.text()
                try:
                    info = json.loads(info_text)
                except Exception:
                    info = {"ok": False, "raw": info_text}
            print("getChatMember response:", info)
            status = info.get("result", {}).get("status", "")
            if status in ["member", "creator", "administrator"]:
                payload = {
                    "chat_id": chat_id,
                    "text": "📣 Тут тебя уже ждёт авто-рассылка",
                    "reply_markup": {"inline_keyboard": [[{"text": "🚀 Перейти к авто-рассылке", "url": REF_LINK}]]}
                }
                await send_method("sendMessage", payload)
            else:
                await send_method("sendMessage", {"chat_id": chat_id, "text": "❌ Подписка не найдена. Подпишись и нажми ещё раз."})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

async def poll_loop():
    offset = 0
    while True:
        try:
            params = {"timeout": LONG_POLL_TIMEOUT, "offset": offset, "limit": 50}
            async with session.get(f"{API_URL}/getUpdates", params=params, timeout=CLIENT_TIMEOUT) as resp:
                text = await resp.text()
                try:
                    data = json.loads(text)
                except Exception:
                    data = {"ok": False, "raw": text}
            if not data.get("ok"):
                print("getUpdates returned error:", data)
            for upd in data.get("result", []):
                offset = max(offset, upd.get("update_id", 0) + 1)
                await handle_update(upd)
        except Exception as e:
            print("poll_loop exception:", repr(e))
            await asyncio.sleep(1)
        await asyncio.sleep(POLL_INTERVAL)

async def healthcheck(request):
    return web.Response(text="ok")

async def run():
    global session
    session = ClientSession(timeout=CLIENT_TIMEOUT)
    app = web.Application()
    app.router.add_get("/", healthcheck)
    port = int(os.getenv("PORT", "8000"))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    loop = asyncio.get_running_loop()
    poll_task = loop.create_task(poll_loop())

    stop = asyncio.Event()
    for sig in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(asyncio, "SIGBREAK", 0), lambda: stop.set())
        except Exception:
            pass

    try:
        await stop.wait()
    finally:
        poll_task.cancel()
        await session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(run())
