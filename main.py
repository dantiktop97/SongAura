import os
import asyncio
import json
from datetime import datetime
from aiohttp import web, ClientSession, ClientTimeout

BOT_TOKEN = os.getenv("AVTO")  # токен бота
CHANNEL_USERNAME = "vzref2"     # канал для проверки подписки
ADMIN_CHANNEL_ID = -1003079638308  # админ-канал

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
POLL_INTERVAL = 1.0
LONG_POLL_TIMEOUT = 30
CLIENT_TIMEOUT = ClientTimeout(total=LONG_POLL_TIMEOUT + 20)

session: ClientSession | None = None

# Основной пояснительный текст
MAIN_TEXT = """
📌 Как бот работает:

1️⃣ Бот отслеживает всех пользователей, которые писали в чате.  
2️⃣ Чтобы упомянуть всех, бот создаёт одно сообщение с видимым словом "УПОМ".  
3️⃣ Все, кто писал в чате, получают уведомление о сообщении.  
4️⃣ Используйте команду /everyone или кнопку для упоминания всех участников.
"""

# Подробная инструкция
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
            print(f"{method} request payload: {payload}")
            print(f"{method} response: {data}")
            return data
    except Exception as e:
        print(f"{method} exception: {repr(e)}")
        return {"ok": False, "error": str(e)}

async def handle_update(update: dict):
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "")
        user = msg.get("from", {})
        user_id = user.get("id")
        username = f"@{user.get('username')}" if user.get("username") else user.get("first_name","").strip()

        if text and text.strip().startswith("/start"):
            # Кнопка проверки подписки
            keyboard = {
                "inline_keyboard": [
                    [{"text": "✅ Проверить подписку", "callback_data": "check_sub"}]
                ]
            }
            await send_method("sendMessage", {
                "chat_id": chat_id,
                "text": "👋 Добро пожаловать! Подпишитесь на канал и нажмите кнопку ниже:",
                "reply_markup": keyboard
            })

            # Отправка данных в админ-канал
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
        chat_id = cb.get("message", {}).get("chat", {}).get("id")
        message_id = cb.get("message", {}).get("message_id")
        user_id = from_user.get("id")

        # Проверка подписки
        if data == "check_sub":
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
            if status in ["member", "creator", "administrator"]:
                # Подписан → сразу основной текст с кнопкой
                keyboard_main = {
                    "inline_keyboard": [
                        [{"text": "ℹ️ Подробная инструкция", "callback_data": "show_instruction"}]
                    ]
                }
                await send_method("sendMessage", {"chat_id": chat_id, "text": MAIN_TEXT, "reply_markup": keyboard_main})
            else:
                # Не подписан → сообщение с просьбой подписаться
                await send_method("sendMessage", {"chat_id": chat_id, "text": "❌ Подпишись на канал и нажми ещё раз."})

            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        # Показ подробной инструкции
        elif data == "show_instruction":
            # Удаляем предыдущее сообщение
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            keyboard_instruction = {
                "inline_keyboard": [
                    [{"text": "⬅️ Назад", "callback_data": "back_to_main"}]
                ]
            }
            await send_method("sendMessage", {"chat_id": chat_id, "text": DETAILED_TEXT, "reply_markup": keyboard_instruction})
            await send_method("answerCallbackQuery", {"callback_query_id": cb.get("id", "")})

        # Назад к основному тексту
        elif data == "back_to_main":
            await send_method("deleteMessage", {"chat_id": chat_id, "message_id": message_id})
            keyboard_main = {
                "inline_keyboard": [
                    [{"text": "ℹ️ Подробная инструкция", "callback_data": "show_instruction"}]
                ]
            }
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
    try:
        await stop.wait()
    finally:
        poll_task.cancel()
        await session.close()
        await runner.cleanup()

if __name__ == "__main__":
    asyncio.run(run())
