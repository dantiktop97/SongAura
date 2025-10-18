import os
import asyncio
import json
from datetime import datetime, timedelta
from aiohttp import web, ClientSession, ClientTimeout

BOT_TOKEN = os.getenv("AVTO")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "vzref2")
ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID", "-1003079638308"))
PORT = int(os.getenv("PORT", "8000"))

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_INTERVAL = 1.0
LONG_POLL_TIMEOUT = 30
CLIENT_TIMEOUT = ClientTimeout(total=LONG_POLL_TIMEOUT + 20)

session: ClientSession | None = None
active_users = {}

MAIN_TEXT = "👋 Добро пожаловать!\n\nВыберите действие:"
INSTRUCTION_TEXT = (
    "📌 Как работает бот:\n\n"
    "1️⃣ Бот отслеживает всех, кто писал в чате за последние 60 минут.\n"
    "2️⃣ Он не пишет в группу — только собирает данные.\n"
    "3️⃣ В личке ты получаешь готовое сообщение с упоминаниями.\n"
    "4️⃣ Ты сам вставляешь его в чат вручную.\n"
    "5️⃣ Все активные участники получают уведомление."
)

def update_activity(chat_id: int, user_id: int):
    now = datetime.utcnow()
    if chat_id not in active_users:
        active_users[chat_id] = {}
    active_users[chat_id][user_id] = now

def get_mentions(chat_id: int, cutoff_minutes=60):
    now = datetime.utcnow()
    mentions = []
    for uid, ts in active_users.get(chat_id, {}).items():
        if (now - ts).total_seconds() <= cutoff_minutes * 60:
            mentions.append(f"[⠀](tg://user?id={uid})")
    return "".join(mentions)

async def send_method(method: str, payload: dict):
    url = f"{API_URL}/{method}"
    try:
        async with session.post(url, json=payload, timeout=CLIENT_TIMEOUT) as resp:
            text = await resp.text()
            try:
                data = json.loads(text)
            except Exception:
                data = {"ok": False, "raw": text}
            return data
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def handle_update(update: dict):
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user = msg.get("from", {})
        user_id = user.get("id")
        username = f"@{user.get('username')}" if user.get("username") else user.get("first_name", "").strip()

        if msg["chat"]["type"] in ["group", "supergroup"]:
            update_activity(chat_id, user_id)

        if text and text.strip().startswith("/start"):
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📄 Инструкция", "callback_data": "show_instruction"}],
                    [{"text": "👥 Активные за 60 мин", "callback_data": "show_active"}]
                ]
            }
            await send_method("sendMessage", {"chat_id": chat_id, "text": MAIN_TEXT, "reply_markup": keyboard})

    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        message_id = cb.get("message", {}).get("message_id")
        user_id = cb.get("from", {}).get("id")

        if data == "show_instruction":
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            keyboard = {"inline_keyboard": [[{"text": "⬅️ Назад", "callback_data": "back_to_main"}]]}
            await send_method("sendMessage", {"chat_id": chat_id, "text": INSTRUCTION_TEXT, "reply_markup": keyboard})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        elif data == "show_active":
            users = []
            for cid, members in active_users.items():
                for uid, ts in members.items():
                    if (datetime.utcnow() - ts).total_seconds() <= 3600:
                        users.append(f"🆔 {uid}")
            user_list = "\n".join(users) if users else "Нет активных пользователей."
            keyboard = {"inline_keyboard": [[{"text": "📋 Скопировать", "callback_data": "copy_mentions"}], [{"text": "⬅️ Назад", "callback_data": "back_to_main"}]]}
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            await send_method("sendMessage", {"chat_id": chat_id, "text": f"👥 Активные:\n\n{user_list}", "reply_markup": keyboard})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        elif data == "copy_mentions":
            mentions = ""
            for cid in active_users:
                mentions += get_mentions(cid)
            final = f"УПОМ {mentions}" if mentions else "Нет активных упоминаний."
            await send_method("sendMessage", {"chat_id": chat_id, "text": final})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        elif data == "back_to_main":
            keyboard = {
                "inline_keyboard": [
                    [{"text": "📄 Инструкция", "callback_data": "show_instruction"}],
                    [{"text": "👥 Активные за 60 мин", "callback_data": "show_active"}]
                ]
            }
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            await send_method("sendMessage", {"chat_id": chat_id, "text": MAIN_TEXT, "reply_markup": keyboard})
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
                print("getUpdates error:", data)
            for upd in data.get("result", []):
                offset = max(offset, upd.get("update_id", 0) + 1)
                await handle_update(upd)
        except Exception as e:
            await asyncio.sleep(1)
        await asyncio.sleep(POLL_INTERVAL)

async def healthcheck(request):
    return web.Response(text="ok")

async def run():
    global session
    session = ClientSession(timeout=CLIENT_TIMEOUT)
    app = web.Application()
    app.router.add_get("/", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    loop = asyncio.get_running_loop()
    poll_task = loop.create_task(poll_loop())

    stop = asyncio.Event()
    try:
        await stop.wait()
    finally:
        poll_task.cancel()
        await session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(run())
