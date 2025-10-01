from telethon import TelegramClient
import os

API_ID = 27258770
API_HASH = "8eda3f168522804bead42bfe705bdaeb"

def safe_filename(phone):
    return phone.replace("+", "").replace(" ", "").strip()

def main():
    phone = input("📱 Введите номер телефона (например +491234567890): ").strip()
    session_name = f"sessions/{safe_filename(phone)}"

    client = TelegramClient(
        session_name,
        API_ID,
        API_HASH,
        device_model="iPhone 13 Pro",
        system_version="iOS 18.1.1",
        app_version="9.6.0"
    )

    async def auth():
        await client.start(phone=phone)
        print(f"✅ Авторизация успешна. Сессия сохранена: {session_name}.session")
        me = await client.get_me()
        print(f"👤 Аккаунт: {me.first_name} ({me.id})")
        await client.disconnect()

    client.loop.run_until_complete(auth())

if __name__ == "__main__":
    if not os.path.exists("sessions"):
        os.makedirs("sessions")
    main()
