import os
import asyncio
import json
from datetime import datetime, timedelta
from aiohttp import web, ClientSession, ClientTimeout

BOT_TOKEN = os.getenv("AVTO")
CHANNEL_USERNAME = "vzref2"
ADMIN_CHANNEL_ID = -1003079638308

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_INTERVAL = 1.0
LONG_POLL_TIMEOUT = 30
CLIENT_TIMEOUT = ClientTimeout(total=LONG_POLL_TIMEOUT + 20)

session: ClientSession | None = None
user_activity: dict[int, datetime] = {}

MAIN_TEXT = "УПОМ\n\n📌 Как бот работает:\n1️⃣ Бот отслеживает всех пользователей, которые писали в чате.\n2️⃣ Чтобы упомянуть всех, бот создаёт одно сообщение с видимым словом 'УПОМ'.\n3️⃣ Все, кто писал в чате, получают уведомление.\n4️⃣ Используйте команду /everyone или кнопку для упоминания всех участников."

DETAILED_TEXT = """
📌 Подробная инструкция:

1️⃣ Добавьте бота в нужный чат или канал.  
2️⃣ Дайте боту права отправлять сообщения.  
3️⃣ Убедитесь, что бот видит сообщения участников, которых хотите упоминать.  
4️⃣ Используйте команду /everyone или кнопку для упоминания всех.  
5️⃣ Сообщение будет одно видимое слово "УПОМ", за которым скрыты ID всех участников.  
6️⃣ Все пользователи, которые писали в чате, получат уведомления.
"""

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

        if user_id:
            user_activity[user_id] = datetime.utcnow()

        async with session.get(
            f"{API_URL}/getChatMember",
            params={"chat_id": f"@{CHANNEL_USERNAME}", "user_id": user_id},
            timeout=CLIENT_TIMEOUT
        ) as resp:
            resp_text = await resp.text()
            try:
                info = json.loads(resp_text)
            except Exception:
                info = {"ok": False, "raw": resp_text}

        status = info.get("result", {}).get("status", "")

        if text.strip().startswith("/start"):
            if status not in ["member", "creator", "administrator"]:
                keyboard = {"inline_keyboard": [[{"text": "✅ Проверить подписку", "callback_data": "check_sub"}]]}
                await send_method("sendMessage", {
                    "chat_id": chat_id,
                    "text": "👋 Подключись к каналу, чтобы продолжить работу:",
                    "reply_markup": keyboard
                })

            timestamp = datetime.now().strftime("%d.%m.%Y %H:%M")
            report = f"👤 Новый пользователь\n🧑 Username: {username}\n🆔 ID: {user_id}\n🕒 Время: {timestamp}"
            await send_method("sendMessage", {"chat_id": ADMIN_CHANNEL_ID, "text": report})

        elif text.strip().startswith("/everyone") and status in ["member", "creator", "administrator"]:
            message_text = text.replace("/everyone", "").strip()
            cutoff = datetime.utcnow() - timedelta(hours=1)
            recent_ids = [uid for uid, ts in user_activity.items() if ts >= cutoff]
            mentions = "".join(f"[⠀](tg://user?id={uid})" for uid in recent_ids)
            final_text = f"{message_text} {mentions}"
            await send_method("sendMessage", {"chat_id": chat_id, "text": final_text})

        elif text.strip():
            if status in ["member", "creator", "administrator"]:
                keyboard_main = {"inline_keyboard": [[{"text": "ℹ️ Подробная инструкция", "callback_data": "show_instruction"}]]}
                await send_method("sendMessage", {"chat_id": chat_id, "text": MAIN_TEXT, "reply_markup": keyboard_main})
            else:
                await send_method("sendMessage", {"chat_id": chat_id, "text": "❌ Подпишись на канал и нажми ещё раз."})

    if "callback_query" in update:
        cb = update["callback_query"]
        data = cb.get("data", "")
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        message_id = cb.get("message", {}).get("message_id")
        user_id = cb.get("from", {}).get("id")

        async with session.get(
            f"{API_URL}/getChatMember",
            params={"chat_id": f"@{CHANNEL_USERNAME}", "user_id": user_id},
            timeout=CLIENT_TIMEOUT
        ) as resp:
            resp_text = await resp.text()
            try:
                info = json.loads(resp_text)
            except Exception:
                info = {"ok": False, "raw": resp_text}

        status = info.get("result", {}).get("status", "")

        if data == "check_sub":
            if status in ["member", "creator", "administrator"]:
                keyboard_main = {"inline_keyboard": [[{"text": "ℹ️ Подробная инструкция", "callback_data": "show_instruction"}]]}
                await send_method("sendMessage", {"chat_id": chat_id, "text": MAIN_TEXT, "reply_markup": keyboard_main})
            else:
                await send_method("sendMessage", {"chat_id": chat_id, "text": "❌ Подпишись на канал и нажми ещё раз."})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        elif data == "show_instruction":
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            keyboard_instruction = {"inline_keyboard": [[{"text": "⬅️ Назад", "callback_data": "back_to_main"}]]}
            await send_method("sendMessage", {"chat_id": chat_id, "text": DETAILED_TEXT, "reply_markup": keyboard_instruction})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        elif data == "back_to_main":
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            keyboard_main = {"inline_keyboard": [[{"text": "ℹ️ Подробная инструкция", "callback_data": "show_instruction"}]]}
            await send_method("sendMessage", {"chat_id": chat_id, "text": MAIN_TEXT, "reply_markup": keyboard_main})
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
    try:
        await stop.wait()
    finally:
        poll_task.cancel()
        await session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(run())
