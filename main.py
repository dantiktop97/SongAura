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
print("🤖 LOVEС CHECK BOT - С ПОДДЕРЖКОЙ 2FA")
print("=" * 60)

if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
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

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **LOVEC BOT v2.0**\n\n"
        f"🔐 **Поддержка 2FA (двухфакторная аутентификация)**\n"
        f"👑 Админ: `{ADMIN_ID}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🔹 **Для аккаунтов с 2FA:**\n"
        f"1. Введите номер\n"
        f"2. Введите код из Telegram\n"
        f"3. Введите пароль 2FA\n"
        f"4. Наслаждайтесь ловлей!\n\n"
        f"🎯 **Команды:**\n"
        f"• /login - Войти в аккаунт (с 2FA)\n"
        f"• /catch - Начать ловлю\n"
        f"• /stop - Остановить\n"
        f"• /status - Статус\n"
        f"• /stats - Статистика\n\n"
        f"⚠️ **Внимание:** Используйте в ЛС!",
        buttons=[
            [Button.inline("🔐 ВОЙТИ С 2FA", b"login_with_2fa")],
            [Button.inline("📊 СТАТУС", b"check_status")]
        ]
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    """Вход с поддержкой 2FA"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    if user_id in user_sessions:
        await event.reply(
            "✅ Сессия уже сохранена!\n\n"
            "🎯 Используйте /catch чтобы начать ловлю.",
            buttons=[
                [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"start_catching")]
            ]
        )
        return
    
    await event.reply(
        "🔐 **ВХОД С 2FA ПОДДЕРЖКОЙ**\n\n"
        "📱 **Шаг 1: Введите номер телефона**\n\n"
        "📌 Формат: с кодом страны\n"
        "• Пример: +380681234567 (Украина)\n"
        "• Пример: +79123456789 (Россия)\n\n"
        "✏️ Просто отправьте номер сообщением\n"
        "Или напишите `cancel` для отмены",
        buttons=[
            [Button.inline("📱 ВВЕСТИ НОМЕР", b"enter_phone")],
            [Button.inline("❌ ОТМЕНА", b"cancel_action")]
        ]
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
    
    if data == "login_with_2fa":
        await event.answer("🔐 Запускаю вход с 2FA...")
        await login_handler(events.NewMessage.Event(peer=event.peer_id, text='/login'))
        await event.delete()
    
    elif data == "check_status":
        await event.answer("📊 Проверяю статус...")
        await status_handler(events.NewMessage.Event(peer=event.peer_id, text='/status'))
        await event.delete()
    
    elif data == "enter_phone":
        await event.edit(
            "📱 **Введите номер телефона:**\n\n"
            "Просто отправьте номер сообщением в формате:\n"
            "`+код_страны номер`\n\n"
            "Пример: `+380681234567`\n"
            "Или напишите `cancel` для отмены"
        )
        user_data[user_id] = {'state': 'waiting_phone'}
    
    elif data == "cancel_action":
        if user_id in user_data:
            del user_data[user_id]
        await event.edit("❌ Отменено")
    
    elif data == "start_catching":
        await event.answer("🎯 Запускаю ловлю...")
        await catch_handler(events.NewMessage.Event(peer=event.peer_id, text='/catch'))
        await event.delete()

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
    
    # Отмена
    if text.lower() == 'cancel':
        if user_id in user_data:
            if 'client' in user_data[user_id]:
                try:
                    await user_data[user_id]['client'].disconnect()
                except:
                    pass
            del user_data[user_id]
        await event.reply("❌ Отменено")
        return
    
    # Шаг 1: Ввод номера телефона
    if user_id in user_data and user_data[user_id].get('state') == 'waiting_phone':
        if not text.startswith('+'):
            await event.reply("❌ Номер должен начинаться с '+'. Пример: +380681234567")
            return
        
        phone = text.replace(' ', '')
        
        await event.reply(f"📱 Проверяю номер: `{phone}`...")
        
        try:
            # Создаем клиента
            client = TelegramClient(StringSession(), api_id, api_hash)
            
            # Настраиваем для лучшей работы
            client.session.set_dc(2, '149.154.167.40', 443)
            
            await client.connect()
            
            # Запрашиваем код
            try:
                sent_code = await client.send_code_request(phone)
                
                # Сохраняем данные
                user_data[user_id] = {
                    'state': 'waiting_code',
                    'phone': phone,
                    'client': client,
                    'phone_code_hash': sent_code.phone_code_hash,
                    'timestamp': time.time()
                }
                
                await event.reply(
                    f"✅ **Код отправлен!**\n\n"
                    f"📱 Номер: `{phone}`\n"
                    f"⏳ Код действует: {sent_code.timeout} сек\n\n"
                    f"📝 **Шаг 2: Введите код из Telegram**\n\n"
                    f"✏️ Просто отправьте код цифрами\n"
                    f"Или напишите `cancel` для отмены"
                )
                
            except Exception as e:
                error_msg = str(e)
                await event.reply(f"❌ Ошибка: {error_msg[:100]}")
                await client.disconnect()
                if user_id in user_data:
                    del user_data[user_id]
                
        except Exception as e:
            await event.reply(f"❌ Ошибка подключения: {str(e)[:100]}")
            if user_id in user_data:
                del user_data[user_id]
    
    # Шаг 2: Ввод кода
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
            
            # Пытаемся войти (может запросить пароль 2FA)
            try:
                await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=phone_code_hash
                )
                
                # Успешно вошли (без 2FA)
                await handle_successful_login(user_id, client, event)
                
            except Exception as e:
                error_msg = str(e)
                
                if "SESSION_PASSWORD_NEEDED" in error_msg or "Two-steps verification" in error_msg:
                    # Нужен пароль 2FA
                    await event.reply(
                        f"🔐 **Требуется пароль 2FA**\n\n"
                        f"📱 Номер: `{phone}`\n\n"
                        f"📝 **Шаг 3: Введите пароль двухфакторной аутентификации**\n\n"
                        f"✏️ Просто отправьте пароль\n"
                        f"Или напишите `cancel` для отмены"
                    )
                    
                    # Сохраняем клиента для ввода пароля
                    user_data[user_id]['state'] = 'waiting_password'
                    
                elif "PHONE_CODE_INVALID" in error_msg:
                    await event.reply("❌ Неверный код! Попробуйте снова: /login")
                    await client.disconnect()
                    if user_id in user_data:
                        del user_data[user_id]
                        
                elif "PHONE_CODE_EXPIRED" in error_msg:
                    await event.reply("⏳ Код истек. Используйте /login")
                    await client.disconnect()
                    if user_id in user_data:
                        del user_data[user_id]
                        
                else:
                    await event.reply(f"❌ Ошибка: {error_msg[:100]}")
                    await client.disconnect()
                    if user_id in user_data:
                        del user_data[user_id]
                        
        except Exception as e:
            await event.reply(f"❌ Критическая ошибка: {str(e)[:100]}")
            if user_id in user_data:
                if 'client' in user_data[user_id]:
                    try:
                        await user_data[user_id]['client'].disconnect()
                    except:
                        pass
                del user_data[user_id]
    
    # Шаг 3: Ввод пароля 2FA
    elif user_id in user_data and user_data[user_id].get('state') == 'waiting_password':
        password = text
        
        await event.reply("🔐 Проверяю пароль 2FA...")
        
        try:
            client = user_data[user_id]['client']
            phone = user_data[user_id]['phone']
            
            # Входим с паролем
            await client.sign_in(password=password)
            
            # Успешно вошли с 2FA
            await handle_successful_login(user_id, client, event)
            
        except Exception as e:
            error_msg = str(e)
            
            if "PASSWORD_HASH_INVALID" in error_msg:
                await event.reply("❌ Неверный пароль! Попробуйте снова или напишите `cancel`")
                # Оставляем в состоянии waiting_password для повторной попытки
                
            else:
                await event.reply(f"❌ Ошибка: {error_msg[:100]}")
                await client.disconnect()
                if user_id in user_data:
                    del user_data[user_id]

async def handle_successful_login(user_id, client, event):
    """Обработка успешного входа (с 2FA или без)"""
    try:
        # Проверяем авторизацию
        if await client.is_user_authorized():
            # Сохраняем сессию
            session_string = client.session.save()
            user_sessions[user_id] = session_string
            
            # Получаем информацию
            me = await client.get_me()
            
            # Сохраняем сессию в файл для надежности
            with open(f'session_{user_id}.txt', 'w') as f:
                f.write(session_string)
            
            success_msg = (
                f"✅ **ВХОД ВЫПОЛНЕН!**\n\n"
                f"👤 Имя: {me.first_name}\n"
                f"📱 Телефон: {me.phone}\n"
                f"🆔 ID: `{me.id}`\n"
                f"🔗 @{me.username if me.username else 'нет'}\n\n"
                f"🔐 **2FA:** {'✅ ВКЛЮЧЕНА' if user_data[user_id].get('state') == 'waiting_password' else '❌ ОТКЛЮЧЕНА'}\n\n"
                f"💾 Сессия сохранена!\n"
                f"🎯 Теперь используйте /catch для ловли чеков"
            )
            
            await event.reply(success_msg, parse_mode='HTML')
            
            # Отправляем в канал
            try:
                await bot.send_message(
                    channel,
                    f"✅ **НОВЫЙ ВХОД (2FA)**\n\n"
                    f"👤 {me.first_name}\n"
                    f"📱 {me.phone}\n"
                    f"🔐 2FA: {'✅' if user_data[user_id].get('state') == 'waiting_password' else '❌'}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
            
            # Очищаем временные данные
            if user_id in user_data:
                del user_data[user_id]
            
            await client.disconnect()
            
            # Автоматически предлагаем начать ловлю
            await asyncio.sleep(2)
            await event.reply(
                "🎯 **Хотите начать ловлю чеков?**\n\n"
                "Нажмите кнопку ниже или напишите /catch",
                buttons=[
                    [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"start_catching")],
                    [Button.inline("⏰ ПОЗЖЕ", b"later_catch")]
                ]
            )
            
        else:
            await event.reply("❌ Не удалось авторизоваться")
            await client.disconnect()
            if user_id in user_data:
                del user_data[user_id]
                
    except Exception as e:
        await event.reply(f"❌ Ошибка сохранения: {str(e)[:100]}")
        await client.disconnect()
        if user_id in user_data:
            del user_data[user_id]

# ========== ДОПОЛНИТЕЛЬНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/catch'))
async def catch_handler(event):
    """Начать ловлю"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    if user_id not in user_sessions:
        await event.reply(
            "❌ Сначала войдите в аккаунт!\n\n"
            "Используйте команду /login для входа.",
            buttons=[
                [Button.inline("🔐 ВОЙТИ", b"login_with_2fa")]
            ]
        )
        return
    
    if user_id in active_clients:
        await event.reply("✅ Ловля уже запущена!")
        return
    
    await event.reply("🎯 Запускаю ловлю чеков...")
    
    # Запускаем ловлю
    asyncio.create_task(start_catching(user_id))

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
    
    # Пробуем загрузить сессию из файла если нет в памяти
    if not has_session:
        try:
            if os.path.exists(f'session_{user_id}.txt'):
                with open(f'session_{user_id}.txt', 'r') as f:
                    session_str = f.read().strip()
                    user_sessions[user_id] = session_str
                    has_session = True
        except:
            pass
    
    status = (
        f"📊 **СТАТУС**\n\n"
        f"🔐 Сессия: {'✅ СОХРАНЕНА' if has_session else '❌ ОТСУТСТВУЕТ'}\n"
        f"🎣 Ловля: {'✅ АКТИВНА' if is_active else '❌ ОСТАНОВЛЕНА'}\n"
        f"📈 Чеков: {checks_count}\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
    )
    
    if has_session and not is_active:
        status += "🎯 Используйте /catch чтобы начать ловлю"
    elif not has_session:
        status += "🔐 Используйте /login для входа"
    
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

# ========== ФУНКЦИЯ ЛОВЛИ ЧЕКОВ ==========
async def start_catching(user_id):
    """Запуск ловли чеков"""
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
            f"🎯 **ЛОВЛЯ ЗАПУЩЕНА!**\n\n"
            f"👤 Аккаунт: {me.first_name}\n"
            f"📱 Телефон: {me.phone}\n"
            f"🔐 2FA: {'✅' if me.id else '❌'}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🔍 Мониторинг 6 ботов...\n"
            f"🛑 /stop - остановить"
        )
        
        await bot.send_message(
            channel,
            f"🎯 **ЛОВЛЯ ЗАПУЩЕНА**\n\n"
            f"👤 {me.first_name}\n"
            f"📱 {me.phone}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
        # ========== ОБРАБОТЧИКИ ЧЕКОВ ==========
        
        @client.on(events.NewMessage(chats=crypto_black_list))
        async def check_handler(event):
            try:
                text = event.text or ''
                found = code_regex.findall(text)
                
                if found:
                    for bot_name, code in found:
                        if code not in checks:
                            print(f"🎯 Чек: {code}")
                            await client.send_message(bot_name, f'/start {code}')
                            checks.append(code)
                            
                            global checks_count
                            checks_count += 1
                            
                            # Уведомление каждые 5 чеков
                            if checks_count % 5 == 0:
                                await bot.send_message(
                                    channel,
                                    f"💰 **ЧЕКОВ: {checks_count}**\n\n"
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
                print(f"⚠️ Ошибка: {e}")
        
        # Автоподписка
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать"))
        async def subscription_handler(event):
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
        
        print(f"✅ Ловля для {me.first_name}")
        
        # Бесконечный цикл
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        
        await bot.send_message(
            user_id,
            f"🛑 **Ловля остановлена**\n\n"
            f"📊 Чеков: {checks_count}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
    except Exception as e:
        error_msg = f"❌ Ошибка ловли: {str(e)[:200]}"
        print(error_msg)
        
        await bot.send_message(user_id, error_msg)
        
        if user_id in active_clients:
            del active_clients[user_id]

# ========== ЗАПУСК БОТА ==========
start_time = time.time()

async def main():
    """Основная функция"""
    print("🚀 ЗАПУСКАЮ LOVEС BOT С ПОДДЕРЖКОЙ 2FA...")
    
    try:
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEC BOT ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: `{ADMIN_ID}`\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🔐 **ПОДДЕРЖКА 2FA**\n"
            f"✅ Работает с двухфакторной аутентификацией!\n\n"
            f"📋 **Как использовать:**\n"
            f"1. Напишите /login\n"
            f"2. Введите номер (+380...)\n"
            f"3. Введите код из Telegram\n"
            f"4. Введите пароль 2FA\n"
            f"5. Напишите /catch\n\n"
            f"🎯 Всё просто! Поддерживаются аккаунты с паролем!"
        )
        
        print("=" * 60)
        print("✅ БОТ ГОТОВ К РАБОТЕ С 2FA!")
        print("=" * 60)
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
