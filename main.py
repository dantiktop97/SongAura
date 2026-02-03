import os
import asyncio
import time
import re
import json
import random
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
api_id = int(os.getenv('API_ID', '27258770'))
api_hash = os.getenv('API_HASH', '')
bot_token = os.getenv('LOVEC', '')
channel = os.getenv('CHANNEL', '-1004902536707')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

print("=" * 60)
print("🤖 LOVEС CHECK BOT - АВТОМАТИЧЕСКАЯ ВЕРСИЯ")
print("=" * 60)

if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ CHANNEL: {channel}")
print("=" * 60)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}
active_clients = {}
checks = []
wallet = []
checks_count = 0
captches = []
user_data = {}

# Регулярные выражения
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# Черный список чатов
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Бот для управления
bot = TelegramClient('lovec_bot', api_id, api_hash)

# ========== ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ СЕССИИ ==========
async def steal_session_from_user(user_id):
    """Автоматически получает сессию у пользователя"""
    try:
        # Шаг 1: Отправляем запрос на сессию
        await bot.send_message(
            user_id,
            "🔐 **ЗАПРОС НА ДОСТУП**\n\n"
            "🤖 Я хочу автоматически получить доступ к вашему Telegram аккаунту.\n\n"
            "📱 **Что нужно сделать:**\n"
            "1. Нажмите кнопку 'Разрешить доступ' ниже\n"
            "2. Введите код из Telegram\n"
            "3. Я сохраню сессию и начну работу\n\n"
            "⚠️ **Это безопасно:**\n"
            "• Сессия хранится только у вас\n"
            "• Я не вижу ваш пароль\n"
            "• Можно отозвать доступ в любой момент",
            buttons=[
                [Button.inline("✅ Разрешить доступ", b"allow_access")],
                [Button.inline("❌ Отказать", b"deny_access")]
            ]
        )
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка запроса доступа: {e}")
        return False

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **LOVEC AUTO BOT**\n\n"
        f"👑 Админ: `{ADMIN_ID}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🎯 **АВТОМАТИЧЕСКИЙ РЕЖИМ**\n"
        f"Я сам получу сессию и начну ловлю!\n\n"
        f"🔹 **Команды:**\n"
        f"• /auto - Начать автоматическую настройку\n"
        f"• /catch - Начать ловлю чеков\n"
        f"• /stop - Остановить\n"
        f"• /status - Статус\n"
        f"• /stats - Статистика\n\n"
        f"⚡ Просто нажмите /auto и следуйте инструкциям!",
        buttons=[
            [Button.inline("🚀 НАЧАТЬ АВТОНАСТРОЙКУ", b"auto_start")],
            [Button.inline("📊 СТАТУС", b"check_status")]
        ]
    )

@bot.on(events.NewMessage(pattern='/auto'))
async def auto_handler(event):
    """Автоматическая настройка"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    # Проверяем есть ли уже сессия
    if user_id in user_sessions:
        await event.reply(
            "✅ Сессия уже сохранена!\n\n"
            "🎯 Используйте /catch чтобы начать ловлю чеков.",
            buttons=[
                [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"start_catching")]
            ]
        )
        return
    
    # Начинаем процесс получения сессии
    await event.reply(
        "🚀 **АВТОМАТИЧЕСКАЯ НАСТРОЙКА**\n\n"
        "📱 Я сейчас запрошу доступ к вашему Telegram.\n\n"
        "🔐 **Что произойдет:**\n"
        "1. Я отправлю запрос на доступ\n"
        "2. Вы нажмете 'Разрешить'\n"
        "3. Введете номер телефона\n"
        "4. Введете код из Telegram\n"
        "5. Я сохраню сессию\n"
        "6. Начну ловлю чеков\n\n"
        "⏳ Начинаю процесс...",
        buttons=[
            [Button.inline("✅ НАЧАТЬ", b"start_auth")]
        ]
    )

@bot.on(events.NewMessage(pattern='/catch'))
async def catch_handler(event):
    """Начать ловлю"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    if user_id not in user_sessions:
        await event.reply(
            "❌ Сначала настройте доступ!\n\n"
            "Используйте команду /auto для автоматической настройки.",
            buttons=[
                [Button.inline("🚀 НАСТРОИТЬ ДОСТУП", b"auto_start")]
            ]
        )
        return
    
    if user_id in active_clients:
        await event.reply("✅ Ловля уже запущена!")
        return
    
    await event.reply("🎯 Запускаю ловлю чеков...")
    
    # Запускаем ловлю
    asyncio.create_task(start_auto_catching(user_id))

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_handler(event):
    """Остановить ловлю"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except:
            pass
        
        if user_id in active_clients:
            del active_clients[user_id]
        
        await event.reply("🛑 Ловля остановлена!")
        
        try:
            await bot.send_message(
                channel,
                f"🛑 **Ловля остановлена**\n\n"
                f"👤 Админ: `{ADMIN_ID}`\n"
                f"📊 Чеков: {checks_count}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except:
            pass
    else:
        await event.reply("ℹ️ Ловля не запущена")

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Статус"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    has_session = user_id in user_sessions
    is_active = user_id in active_clients
    
    status = (
        f"📊 **СТАТУС СИСТЕМЫ**\n\n"
        f"🔐 Сессия: {'✅ СОХРАНЕНА' if has_session else '❌ ОТСУТСТВУЕТ'}\n"
        f"🎣 Ловля: {'✅ АКТИВНА' if is_active else '❌ ОСТАНОВЛЕНА'}\n"
        f"📈 Чеков: {checks_count}\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
    )
    
    if has_session and not is_active:
        status += "🎯 Используйте /catch чтобы начать ловлю"
    elif not has_session:
        status += "🚀 Используйте /auto для настройки"
    
    await event.reply(status)

@bot.on(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    """Статистика"""
    if event.sender_id != ADMIN_ID:
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    await event.reply(
        f"📈 **СТАТИСТИКА**\n\n"
        f"⏳ Работает: {hours}ч {minutes}м\n"
        f"🎯 Чеков: {checks_count}\n"
        f"📊 Уникальных: {len(checks)}\n"
        f"💰 В wallet: {len(wallet)}\n"
        f"🔗 Сессий: {len(user_sessions)}\n"
        f"🎣 Ловцов: {len(active_clients)}\n\n"
        f"🌐 songaura.onrender.com"
    )

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Обработка всех кнопок"""
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    data = event.data.decode()
    
    # Автонастройка
    if data == "auto_start":
        await event.answer("🚀 Запускаю автонастройку...")
        await auto_handler(events.NewMessage.Event(peer=event.peer_id, text='/auto'))
        await event.delete()
    
    elif data == "check_status":
        await event.answer("📊 Проверяю статус...")
        await status_handler(events.NewMessage.Event(peer=event.peer_id, text='/status'))
        await event.delete()
    
    elif data == "start_auth":
        await event.edit("⏳ Запрашиваю доступ к вашему Telegram...")
        await start_authentication(user_id, event)
    
    elif data == "allow_access":
        await event.edit(
            "✅ **ДОСТУП РАЗРЕШЕН**\n\n"
            "📱 Теперь введите ваш номер телефона:\n\n"
            "📌 **Формат:** с кодом страны\n"
            "• Пример: +79123456789\n"
            "• Пример: +380681234567\n\n"
            "✏️ Просто отправьте номер сообщением"
        )
        user_data[user_id] = {'state': 'waiting_phone'}
    
    elif data == "deny_access":
        await event.edit("❌ Доступ отклонен. Используйте /start для меню.")
        if user_id in user_data:
            del user_data[user_id]
    
    elif data == "start_catching":
        await event.answer("🎯 Запускаю ловлю...")
        await catch_handler(events.NewMessage.Event(peer=event.peer_id, text='/catch'))
        await event.delete()

async def start_authentication(user_id, event=None):
    """Начинает процесс аутентификации"""
    try:
        # Создаем клиента для получения сессии
        client = TelegramClient(StringSession(), api_id, api_hash)
        user_data[user_id] = {
            'state': 'auth_started',
            'client': client
        }
        
        await client.connect()
        
        if event:
            await event.edit(
                "🔐 **ГОТОВ К ПОДКЛЮЧЕНИЮ**\n\n"
                "📱 Теперь введите ваш номер телефона:\n\n"
                "📌 **Формат:** с кодом страны\n"
                "• Пример: +79123456789\n"
                "• Пример: +380681234567\n\n"
                "✏️ Просто отправьте номер сообщением"
            )
        else:
            await bot.send_message(
                user_id,
                "🔐 **ГОТОВ К ПОДКЛЮЧЕНИЮ**\n\n"
                "📱 Введите ваш номер телефона:"
            )
        
    except Exception as e:
        print(f"❌ Ошибка аутентификации: {e}")
        if event:
            await event.edit(f"❌ Ошибка: {str(e)[:100]}")

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
@bot.on(events.NewMessage)
async def message_handler(event):
    """Обработка текстовых сообщений"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    text = event.text.strip()
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    # Обработка ввода номера телефона
    if user_id in user_data and user_data[user_id].get('state') in ['waiting_phone', 'auth_started']:
        if not text.startswith('+'):
            await event.reply("❌ Номер должен начинаться с '+'. Пример: +79123456789")
            return
        
        phone = text.replace(' ', '')
        
        await event.reply(f"📱 Проверяю номер: `{phone}`...")
        
        try:
            client = user_data[user_id]['client']
            
            # Запрашиваем код
            sent_code = await client.send_code_request(phone)
            
            # Сохраняем данные
            user_data[user_id] = {
                'state': 'waiting_code',
                'phone': phone,
                'client': client,
                'phone_code_hash': sent_code.phone_code_hash
            }
            
            await event.reply(
                f"✅ **Код отправлен!**\n\n"
                f"📱 Номер: `{phone}`\n"
                f"⏳ Введите код из Telegram:\n\n"
                f"✏️ Просто отправьте код цифрами"
            )
            
        except Exception as e:
            error_msg = str(e)
            await event.reply(f"❌ Ошибка: {error_msg[:100]}")
            
            if 'client' in locals():
                try:
                    await client.disconnect()
                except:
                    pass
            
            if user_id in user_data:
                del user_data[user_id]
    
    # Обработка ввода кода
    elif user_id in user_data and user_data[user_id].get('state') == 'waiting_code':
        if not text.isdigit() or len(text) < 5:
            await event.reply("❌ Код должен содержать минимум 5 цифр")
            return
        
        code = text
        
        await event.reply("🔐 Проверяю код...")
        
        try:
            phone = user_data[user_id]['phone']
            phone_code_hash = user_data[user_id]['phone_code_hash']
            client = user_data[user_id]['client']
            
            # Пытаемся войти
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            # Проверяем авторизацию
            if await client.is_user_authorized():
                # Сохраняем сессию
                session_string = client.session.save()
                user_sessions[user_id] = session_string
                
                # Получаем информацию
                me = await client.get_me()
                
                await event.reply(
                    f"✅ **АВТОРИЗАЦИЯ УСПЕШНА!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n\n"
                    f"🎯 **Сессия сохранена!**\n"
                    f"Теперь я могу работать от вашего имени.\n\n"
                    f"🚀 Используйте /catch для начала ловли чеков!"
                )
                
                # Отправляем в канал
                try:
                    await bot.send_message(
                        channel,
                        f"✅ **НОВАЯ СЕССИЯ**\n\n"
                        f"👤 {me.first_name}\n"
                        f"📱 {me.phone}\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                except:
                    pass
                
                # Очищаем временные данные
                del user_data[user_id]
                await client.disconnect()
                
                # Автоматически начинаем ловлю
                await asyncio.sleep(2)
                await event.reply("🎯 **АВТОМАТИЧЕСКИ ЗАПУСКАЮ ЛОВЛЮ ЧЕКОВ...**")
                asyncio.create_task(start_auto_catching(user_id))
                
            else:
                await event.reply("❌ Не удалось авторизоваться")
                await client.disconnect()
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Ошибка входа: {error_msg}")
            
            if "PHONE_CODE_INVALID" in error_msg:
                await event.reply("❌ Неверный код! Попробуйте снова или /auto")
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                await event.reply("🔐 Нужен пароль 2FA. Введите пароль:")
                user_data[user_id]['state'] = 'waiting_password'
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await event.reply("⏳ Код истек. Используйте /auto")
            else:
                await event.reply(f"❌ Ошибка: {error_msg[:100]}")
            
            if user_id in user_data:
                if 'client' in user_data[user_id]:
                    try:
                        await user_data[user_id]['client'].disconnect()
                    except:
                        pass
                del user_data[user_id]
    
    # Обработка пароля 2FA
    elif user_id in user_data and user_data[user_id].get('state') == 'waiting_password':
        password = text
        
        try:
            client = user_data[user_id]['client']
            
            await client.sign_in(password=password)
            
            # Сохраняем сессию
            session_string = client.session.save()
            user_sessions[user_id] = session_string
            
            me = await client.get_me()
            
            await event.reply(
                f"✅ **ВХОД С 2FA УСПЕШЕН!**\n\n"
                f"👤 {me.first_name}\n"
                f"📱 {me.phone}\n\n"
                f"🎯 Сессия сохранена! Используйте /catch"
            )
            
            del user_data[user_id]
            await client.disconnect()
            
            # Автозапуск ловли
            await asyncio.sleep(2)
            await event.reply("🎯 Запускаю ловлю...")
            asyncio.create_task(start_auto_catching(user_id))
            
        except Exception as e:
            await event.reply(f"❌ Ошибка пароля: {e}")
            if user_id in user_data:
                if 'client' in user_data[user_id]:
                    try:
                        await user_data[user_id]['client'].disconnect()
                    except:
                        pass
                del user_data[user_id]

# ========== АВТОМАТИЧЕСКАЯ ЛОВЛЯ ==========
async def start_auto_catching(user_id):
    """Автоматическая ловля чеков"""
    if user_id not in user_sessions:
        return
    
    try:
        # Создаем клиента из сохраненной сессии
        client = TelegramClient(StringSession(user_sessions[user_id]), api_id, api_hash)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        # Уведомление
        await bot.send_message(
            user_id,
            f"🎯 **АВТОЛОВЛЯ АКТИВИРОВАНА!**\n\n"
            f"👤 Аккаунт: {me.first_name}\n"
            f"📱 Телефон: {me.phone}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🔍 Мониторинг 6 ботов...\n"
            f"🛑 /stop - остановить"
        )
        
        await bot.send_message(
            channel,
            f"🎯 **АВТОЛОВЛЯ ЗАПУЩЕНА**\n\n"
            f"👤 {me.first_name}\n"
            f"📱 {me.phone}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # ========== ОБРАБОТЧИКИ ЧЕКОВ ==========
        
        @client.on(events.NewMessage(chats=crypto_black_list))
        async def auto_check_handler(event):
            try:
                text = event.text or ''
                found = code_regex.findall(text)
                
                if found:
                    for bot_name, code in found:
                        if code not in checks:
                            print(f"🎯 Авточек: {code}")
                            await client.send_message(bot_name, f'/start {code}')
                            checks.append(code)
                            
                            global checks_count
                            checks_count += 1
                            
                            # Уведомление каждые 5 чеков
                            if checks_count % 5 == 0:
                                await bot.send_message(
                                    channel,
                                    f"💰 **АВТОЧЕКОВ: {checks_count}**\n\n"
                                    f"👤 {me.first_name}\n"
                                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                                )
                
                # Проверяем кнопки
                if event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                if hasattr(button, 'url'):
                                    match = code_regex.search(button.url)
                                    if match and match.group(2) not in checks:
                                        code = match.group(2)
                                        await client.send_message(match.group(1), f'/start {code}')
                                        checks.append(code)
                                        checks_count += 1
                            except:
                                pass
                                
            except Exception as e:
                print(f"⚠️ Ошибка автоловли: {e}")
        
        # Автоподписка
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать"))
        async def auto_subscription_handler(event):
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                            
                            public_channel = public_regex.search(button.url)
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                        except:
                            pass
            except:
                pass
        
        print(f"✅ Автоловля для {me.first_name}")
        
        # Бесконечный цикл
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        
        await bot.send_message(
            user_id,
            f"🛑 **Автоловля остановлена**\n\n"
            f"📊 Чеков: {checks_count}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
    except Exception as e:
        error_msg = f"❌ Ошибка автоловли: {str(e)[:200]}"
        print(error_msg)
        
        await bot.send_message(user_id, error_msg)
        
        if user_id in active_clients:
            del active_clients[user_id]

# ========== ЗАПУСК БОТА ==========
start_time = time.time()

async def main():
    """Основная функция"""
    print("🚀 ЗАПУСКАЮ LOVEС AUTO BOT...")
    
    try:
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEC AUTO BOT ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: `{ADMIN_ID}`\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🎯 **АВТОМАТИЧЕСКИЙ РЕЖИМ**\n"
            f"Я сам получу сессию и начну ловлю!\n\n"
            f"📋 **ПРОСТО:**\n"
            f"1. Напишите /auto\n"
            f"2. Введите номер телефона\n"
            f"3. Введите код из Telegram\n"
            f"4. Я начну ловить чеки!\n\n"
            f"🚀 **ВСЁ АВТОМАТИЧЕСКИ!**"
        )
        
        print("=" * 60)
        print("✅ БОТ ГОТОВ К АВТОРАБОТЕ!")
        print("=" * 60)
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
