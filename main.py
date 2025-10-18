import os
import asyncio
import json
from datetime import datetime, timedelta
from aiohttp import web, ClientSession, ClientTimeout

BOT_TOKEN = os.getenv("AVTO")
PORT = int(os.getenv("PORT", "8000"))

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
CLIENT_TIMEOUT = ClientTimeout(total=60)
session: ClientSession | None = None

known_chats = {}  # chat_id → title
active_users = {}  # chat_id → {user_id: (name, timestamp)}

MAIN_MENU = {
    "inline_keyboard": [
        [{"text": "💬 Чаты", "callback_data": "show_chats"}],
        [{"text": "📄 Инструкция", "callback_data": "show_instruction"}]
    ]
}

INSTRUCTION_TEXT = (
    "📌 Как работает бот:\n\n"
    "1️⃣ Бот отслеживает, в каких чатах он находится.\n"
    "2️⃣ В каждом чате он фиксирует, кто писал сообщения.\n"
    "3️⃣ В личке ты можешь посмотреть список чатов и активных участников.\n"
    "4️⃣ Бот ничего не пишет в группы — всё вручную.\n"
    "5️⃣ Никаких команд, никаких рассылок — только логика и контроль."
)

def update_activity(chat_id: int, user_id: int, name: str):
    now = datetime.utcnow()
    if chat_id not in active_users:
        active_users[chat_id] = {}
    active_users[chat_id][user_id] = (name, now)

def get_active_users(chat_id: int, minutes=60):
    now = datetime.utcnow()
    result = []
    for uid, (name, ts) in active_users.get(chat_id, {}).items():
        if (now - ts).total_seconds() <= minutes * 60:
            result.append(name)
    return result

async def send(method: str, payload: dict):
    url = f"{API_URL}/{method}"
    try:
        async with session.post(url, json=payload, timeout=CLIENT_TIMEOUT) as resp:
            return await resp.json()
    except Exception as e:
        return {"ok": False, "error": str(e)}

async def handle_update(update: dict):
    if "message" in update:
        msg = update["message"]
        chat = msg["chat"]
        chat_id = chat["id"]
        chat_title = chat.get("title", f"Без названия ({chat_id})")
        user = msg.get("from", {})
        user_id = user.get("id")
        name = f"@{user.get('username')}" if user.get("username") else user.get("first_name", "Аноним")

        if chat["type"] in ["group", "supergroup"]:
            known_chats[chat_id] = chat_title
            update_activity(chat_id, user_id, name)

        if chat["type"] == "private" and msg.get("text", "").startswith("/start"):
            await send("sendMessage", {"chat_id": chat_id, "text": "👋 Добро пожаловать!\n\nВыберите действие:", "reply_markup": MAIN_MENU})

    if "my_chat_member" in update:
        chat = update["my_chat_member"]["chat"]
        chat_id = chat["id"]
        status = update["my_chat_member"]["new_chat_member"]["status"]
        if status in ["member", "administrator"]:
            known_chats[chat_id] = chat.get("title", f"Без названия ({chat_id})")
        elif status in ["left", "kicked"]:
            known_chats.pop(chat_id, None)
            active_users.pop(chat_id, None)

    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        chat_id = cb["message"]["chat"]["id"]
        msg_id = cb["message"]["message_id"]
        user_id = cb["from"]["id"]

        if data == "show_instruction":
            await send("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            await send("sendMessage", {
                "chat_id": chat_id,
                "text": INSTRUCTION_TEXT,
                "reply_markup": {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "back_to_main"}]]}
            })

        elif data == "show_chats":
            buttons = []
            for cid, title in known_chats.items():
                buttons.append([{"text": f"💬 {title}", "callback_data": f"chat_{cid}"}])
            buttons.append([{"text": "🔙 Назад", "callback_data": "back_to_main"}])
            await send("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            await send("sendMessage", {
                "chat_id": chat_id,
                "text": "📍 Чаты, где активен бот:",
                "reply_markup": {"inline_keyboard": buttons}
            })

        elif data.startswith("chat_"):
            target_id = int(data.split("_")[1])
            title = known_chats.get(target_id, f"Без названия ({target_id})")
            users = get_active_users(target_id)
            text = f"💬 Чат: {title}\n\n👥 Активные за 60 минут:\n\n" + ("\n".join(f"— {u}" for u in users) if users else "Нет активных участников.")
            await send("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            await send("sendMessage", {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": {"inline_keyboard": [[{"text": "🔙 Назад", "callback_data": "show_chats"}]]}
            })

        elif data == "back_to_main":
            await send("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
            await send("sendMessage", {"chat_id": chat_id, "text": "👋 Добро пожаловать!\n\nВыберите действие:", "reply_markup": MAIN_MENU})

async def poll_loop():
    offset = 0
    while True:
        try:
            async with session.get(f"{API_URL}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=CLIENT_TIMEOUT) as resp:
                data = await resp.json()
            for upd in data.get("result", []):
                offset = max(offset, upd["update_id"] + 1)
                await handle_update(upd)
        except Exception:
            await asyncio.sleep(1)
        await asyncio.sleep(0.5)

async def healthcheck(request):
    return web.Response(text="ok")

async def run():
    global session
    session = ClientSession(timeout=CLIENT_TIMEOUT)
    app = web.Application()
    app.router.add_get("/", healthcheck)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", PORT).start()
    await poll_loop()

if __name__ == "__main__":
    asyncio.run(run())
