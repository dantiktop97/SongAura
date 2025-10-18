import os
import asyncio
import json
from datetime import datetime, timedelta
from aiohttp import web, ClientSession, ClientTimeout

BOT_TOKEN = os.getenv("AVTO")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CLIENT_TIMEOUT = ClientTimeout(total=50)
session: ClientSession | None = None

user_activity: dict[int, dict[int, datetime]] = {}  # chat_id → {user_id → timestamp}
user_names: dict[int, dict[int, str]] = {}          # chat_id → {user_id → username}
known_chats: dict[int, str] = {}                    # chat_id → title

async def send(method: str, payload: dict):
    async with session.post(f"{API_URL}/{method}", json=payload, timeout=CLIENT_TIMEOUT) as resp:
        return await resp.json()

async def handle_update(update: dict):
    if "message" in update:
        msg = update["message"]
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type")
        text = msg.get("text", "").strip()
        user = msg.get("from", {})
        user_id = user.get("id")
        username = user.get("username") or user.get("first_name", "").strip()

        if chat_type in ["group", "supergroup"]:
            known_chats[chat_id] = chat.get("title", f"Чат {chat_id}")
            user_activity.setdefault(chat_id, {})[user_id] = datetime.utcnow()
            user_names.setdefault(chat_id, {})[user_id] = username

        elif chat_type == "private" and text == "/чаты":
            buttons = [
                [{"text": title, "callback_data": f"чат_{cid}"}]
                for cid, title in known_chats.items()
            ]
            await send("sendMessage", {
                "chat_id": chat_id,
                "text": "Выбери чат для просмотра активности:",
                "reply_markup": {"inline_keyboard": buttons}
            })

    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        cb_id = cb.get("id", "")

        if data.startswith("чат_"):
            target_chat_id = int(data.split("_")[1])
            cutoff = datetime.utcnow() - timedelta(hours=1)
            active = [
                user_names[target_chat_id].get(uid, f"id{uid}")
                for uid, ts in user_activity.get(target_chat_id, {}).items()
                if ts >= cutoff
            ]
            result = "\n".join([f"@{name}" for name in active]) or "❌ Никто не писал за последний час."
            await send("sendMessage", {"chat_id": chat_id, "text": result})
            await send("answerCallbackQuery", {"callback_query_id": cb_id})

async def poll_loop():
    offset = 0
    while True:
        try:
            async with session.get(f"{API_URL}/getUpdates", params={"offset": offset, "timeout":30}, timeout=CLIENT_TIMEOUT) as resp:
                data = await resp.json()
                for upd in data.get("result", []):
                    offset = upd["update_id"] + 1
                    await handle_update(upd)
        except:
            await asyncio.sleep(1)

async def healthcheck(request):
    return web.Response(text="ok")

async def run():
    global session
    session = ClientSession(timeout=CLIENT_TIMEOUT)
    app = web.Application()
    app.router.add_get("/", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", "8000"))).start()
    await poll_loop()

if __name__ == "__main__":
    asyncio.run(run())
