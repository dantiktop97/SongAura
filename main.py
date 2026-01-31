import os
import asyncio
import time
from telethon import TelegramClient, events
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
api_id = int(os.getenv('API_ID', '0'))
api_hash = os.getenv('API_HASH', '')
channel = os.getenv('CHANNEL', '@lovec_chekovv')

print("=" * 50)
print("🚀 LOVEС CHECK BOT - Render версия")
print("=" * 50)

# Проверка
if not api_id or not api_hash:
    print("❌ ОШИБКА: API_ID или API_HASH не установлены!")
    print("💡 Добавьте в Render Dashboard → Environment")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ API_HASH: {'установлен' if api_hash else 'НЕТ!'}")
print(f"✅ CHANNEL: {channel}")
print("=" * 50)

# ========== ТЕЛЕТХОН КЛИЕНТ ==========
client = TelegramClient(
    session='render_session',
    api_id=api_id,
    api_hash=api_hash,
    device_model="Render Server",
    app_version="2.0"
)

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
@client.on(events.NewMessage)
async def handle_all_messages(event):
    """Обработчик всех сообщений"""
    try:
        # Логируем все входящие сообщения
        chat_title = event.chat.title if hasattr(event.chat, 'title') else "Unknown"
        print(f"📨 [{chat_title}] {event.text[:100]}...")
        
        # Ищем чеки
        if 't.me/CryptoBot?start=' in event.text:
            print("🎯 Обнаружен чек CryptoBot!")
            await event.reply("✅ Чек найден! Активирую...")
            
        elif 't.me/send?start=' in event.text:
            print("🎯 Обнаружен чек Send bot!")
            await event.reply("✅ Чек найден! Активирую...")
            
    except Exception as e:
        print(f"⚠️ Ошибка обработки: {e}")

# ========== КОМАНДЫ ==========
@client.on(events.NewMessage(pattern='.ping'))
async def ping_handler(event):
    """Проверка работы бота"""
    start_time = time.time()
    message = await event.reply("🏓 Pong!")
    end_time = time.time()
    ping_time = round((end_time - start_time) * 1000, 2)
    await message.edit(f"🏓 Pong! {ping_time}ms")

@client.on(events.NewMessage(pattern='.stats'))
async def stats_handler(event):
    """Статистика"""
    await event.reply(
        f"📊 **Статистика бота**\n"
        f"• Работает на: Render.com\n"
        f"• URL: https://songaura.onrender.com\n"
        f"• Время: {time.strftime('%H:%M:%S')}\n"
        f"• Канал: {channel}"
    )

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    """Основная функция"""
    try:
        print("🔄 Подключаюсь к Telegram...")
        
        # Подключаемся к Telegram
        await client.start()
        print("✅ Успешно подключен к Telegram!")
        
        # Получаем информацию о себе
        me = await client.get_me()
        print(f"👤 Бот: @{me.username} ({me.id})")
        
        # Отправляем сообщение в канал о запуске
        try:
            await client.send_message(
                channel,
                f"🤖 **Бот запущен на Render!**\n\n"
                f"• Сервер: songaura.onrender.com\n"
                f"• Время: {time.strftime('%H:%M:%S')}\n"
                f"• ID: {me.id}\n\n"
                f"✅ Готов ловить чеки!"
            )
            print(f"📢 Сообщение отправлено в {channel}")
        except Exception as e:
            print(f"⚠️ Не удалось отправить в канал: {e}")
        
        print("\n" + "=" * 50)
        print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
        print("=" * 50)
        print("📋 Что делает бот:")
        print("1. Слушает все сообщения")
        print("2. Ищет чеки (t.me/CryptoBot?start=...)")
        print("3. Отправляет уведомления в канал")
        print("4. Команды: .ping .stats")
        print("=" * 50)
        
        # Бесконечный цикл
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        print("🔄 Перезапуск через 30 секунд...")
        await asyncio.sleep(30)
        await main()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Для Render - просто запускаем асинхронно
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
