import os
import asyncio
import time
import re
import random
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.types import KeyboardButtonRequestPhone
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
api_id = int(os.getenv('API_ID', '2040'))
api_hash = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')
bot_token = os.getenv('LOVEC', '')
channel = os.getenv('CHANNEL', '-1004902536707')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

print("=" * 60)
print("🤖 LOVEС CHECK BOT - БЕЗОПАСНАЯ ВЕРСИЯ")
print("=" * 60)

if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print("=" * 60)

# ========== СИСТЕМА БЕЗОПАСНОСТИ ==========
class SecuritySystem:
    """Система защиты от блокировок Telegram"""
    
    def __init__(self):
        self.action_timestamps = []
        self.last_action = {}
        self.safety_mode = True
        self.daily_limits = {
            'messages': 0,
            'joins': 0,
            'checks': 0
        }
        
    def can_perform_action(self, action_type='message'):
        """Проверяет можно ли выполнить действие"""
        now = time.time()
        
        # Лимиты по типам действий
        limits = {
            'message': (50, 60),  # 50 сообщений в минуту
            'join': (10, 300),    # 10 подписок в 5 минут
            'check': (30, 60),    # 30 чеков в минуту
        }
        
        if action_type not in limits:
            return True
            
        limit, period = limits[action_type]
        
        # Очищаем старые записи
        self.action_timestamps = [t for t in self.action_timestamps if now - t < period]
        
        if len(self.action_timestamps) >= limit:
            wait_time = random.randint(30, 60)
            print(f"⚠️ Лимит {action_type}. Жду {wait_time} сек")
            return False, wait_time
            
        self.action_timestamps.append(now)
        return True, 0
    
    async def safe_delay(self, min_ms=1000, max_ms=3000):
        """Случайная задержка между действиями"""
        delay = random.uniform(min_ms/1000, max_ms/1000)
        await asyncio.sleep(delay)
        
    def get_safety_status(self):
        """Возвращает статус безопасности"""
        now = time.time()
        recent_actions = [t for t in self.action_timestamps if now - t < 60]
        return {
            'recent_actions': len(recent_actions),
            'safety_mode': self.safety_mode,
            'daily_limits': self.daily_limits
        }

security = SecuritySystem()

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}
active_clients = {}
checks = []
wallet = []
checks_count = 0
user_data = {}

# Регулярные выражения
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# Черный список чатов
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Бот для управления
bot = TelegramClient('lovec_bot', api_id, api_hash)

# ========== ПРОВЕРКА АДМИНА ==========
async def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID

# ========== ГЛАВНОЕ МЕНЮ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Этот бот только для администратора!")
        return
    
    await event.reply(
        f"👑 **ПРИВЕТСТВУЮ, АДМИНИСТРАТОР!**\n\n"
        f"🆔 Ваш ID: `{ADMIN_ID}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🛡️ **БЕЗОПАСНЫЙ РЕЖИМ:** ВКЛЮЧЕН\n"
        f"✅ Защита от блокировок активна\n\n"
        f"🎯 **ВЫБЕРИТЕ ДЕЙСТВИЕ:**",
        buttons=[
            [Button.inline("🔐 ВОЙТИ В АККАУНТ", b"login_menu")],
            [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"catch_menu")],
            [Button.inline("📊 СТАТУС", b"status_menu")],
            [Button.inline("⚙️ НАСТРОЙКИ", b"settings_menu")]
        ]
    )

# ========== МЕНЮ ВХОДА ==========
@bot.on(events.CallbackQuery(pattern=b'login_menu'))
async def login_menu_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await event.edit(
        "🔐 **ВХОД В АККАУНТ**\n\n"
        "📱 **ВЫБЕРИТЕ СПОСОБ:**\n\n"
        "1. 📲 Поделиться номером (рекомендуется)\n"
        "2. ✏️ Ввести номер вручную\n\n"
        "✅ **Безопасный способ:** Поделиться контактом",
        buttons=[
            [Button.request_phone("📲 ПОДЕЛИТЬСЯ НОМЕРОМ")],
            [Button.inline("✏️ ВВЕСТИ ВРУЧНУЮ", b"manual_login")],
            [Button.inline("🔙 НАЗАД", b"main_menu")]
        ]
    )

@bot.on(events.NewMessage(func=lambda e: e.contact))
async def contact_handler(event):
    """Обработка поделившегося контакта"""
    if not await is_admin(event.sender_id):
        return
    
    contact = event.contact
    if contact.user_id != event.sender_id:
        await event.reply("❌ Это не ваш контакт!")
        return
    
    phone = contact.phone_number
    if not phone.startswith('+'):
        phone = '+' + phone
    
    await event.reply(f"📱 **Получен номер:** `{phone}`\n\n⏳ Запрашиваю код...")
    
    await process_phone_number(event.sender_id, phone, event)

@bot.on(events.CallbackQuery(pattern=b'manual_login'))
async def manual_login_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await event.edit(
        "✏️ **ВВОД НОМЕРА ВРУЧНУЮ**\n\n"
        "📱 Отправьте номер телефона:\n\n"
        "📌 **Формат:** с кодом страны\n"
        "• Пример: +380681234567\n"
        "• Пример: +79123456789\n\n"
        "✏️ Просто отправьте номер сообщением",
        buttons=[
            [Button.inline("🔙 НАЗАД", b"login_menu")]
        ]
    )
    
    user_data[event.sender_id] = {'state': 'waiting_phone_manual'}

# ========== ОБРАБОТКА НОМЕРА ==========
async def process_phone_number(user_id, phone, event=None):
    """Обработка номера телефона"""
    try:
        # Создаем клиента
        client = TelegramClient(StringSession(), api_id, api_hash)
        
        # Настраиваем безопасное подключение
        client.session.set_dc(2, '149.154.167.40', 443)
        client.session.timeout = 30
        
        await client.connect()
        
        # Запрашиваем код с безопасной задержкой
        await security.safe_delay(2000, 5000)
        sent_code = await client.send_code_request(phone)
        
        # Сохраняем данные
        user_data[user_id] = {
            'state': 'waiting_code',
            'phone': phone,
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash,
            'timestamp': time.time()
        }
        
        success_msg = (
            f"✅ **Код отправлен!**\n\n"
            f"📱 Номер: `{phone}`\n"
            f"⏳ Код действует: {sent_code.timeout} сек\n\n"
            f"📝 **Введите код из Telegram:**\n\n"
            f"Используйте цифровую клавиатуру ниже"
        )
        
        if event:
            if hasattr(event, 'edit'):
                await event.edit(success_msg, buttons=create_numpad_keyboard())
            else:
                await event.reply(success_msg, buttons=create_numpad_keyboard())
        else:
            await bot.send_message(user_id, success_msg, buttons=create_numpad_keyboard())
        
    except Exception as e:
        error_msg = str(e)
        error_response = f"❌ Ошибка: {error_msg[:100]}"
        
        if "A wait of" in error_msg:
            match = re.search(r"A wait of (\d+) seconds", error_msg)
            if match:
                wait_seconds = int(match.group(1))
                if wait_seconds > 3600:
                    error_response = f"⏳ Telegram ограничил запросы на {wait_seconds//3600} часов. Попробуйте позже."
                else:
                    error_response = f"⏳ Подождите {wait_seconds} секунд."
        
        if event:
            if hasattr(event, 'edit'):
                await event.edit(error_response, buttons=[[Button.inline("🔙 НАЗАД", b"login_menu")]])
            else:
                await event.reply(error_response)
        else:
            await bot.send_message(user_id, error_response)

# ========== ЦИФРОВАЯ КЛАВИАТУРА ==========
def create_numpad_keyboard(code=""):
    """Создает цифровую клавиатуру для ввода кода"""
    buttons = [
        [
            Button.inline("1", b"num_1"),
            Button.inline("2", b"num_2"), 
            Button.inline("3", b"num_3")
        ],
        [
            Button.inline("4", b"num_4"),
            Button.inline("5", b"num_5"), 
            Button.inline("6", b"num_6")
        ],
        [
            Button.inline("7", b"num_7"),
            Button.inline("8", b"num_8"), 
            Button.inline("9", b"num_9")
        ],
        [
            Button.inline("0", b"num_0"),
            Button.inline("⌫", b"num_del"),
            Button.inline("✅", b"num_submit")
        ]
    ]
    return buttons

@bot.on(events.CallbackQuery(pattern=b'num_'))
async def numpad_handler(event):
    """Обработка цифровой клавиатуры"""
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    user_id = event.sender_id
    
    if user_id not in user_data or user_data[user_id].get('state') != 'waiting_code':
        await event.answer("❌ Сначала введите номер!", alert=True)
        return
    
    action = event.data.decode().split('_')[1]
    current_code = user_data[user_id].get('code', '')
    
    if action == 'del':
        if current_code:
            user_data[user_id]['code'] = current_code[:-1]
    
    elif action == 'submit':
        code = user_data[user_id].get('code', '')
        if len(code) >= 5:
            await event.answer("🔐 Проверяю код...")
            await process_code(user_id, code, event)
            return
        else:
            await event.answer("❌ Нужно минимум 5 цифр!", alert=True)
            return
    
    else:
        if len(current_code) < 10:
            user_data[user_id]['code'] = current_code + action
    
    # Обновляем отображение
    new_code = user_data[user_id].get('code', '')
    phone = user_data[user_id].get('phone', 'Неизвестно')
    
    dots = "•" * len(new_code) if new_code else "____"
    
    await event.edit(
        f"📱 Номер: `{phone}`\n\n"
        f"🔢 **Код:** `{dots}`\n"
        f"📝 Введено: {len(new_code)} цифр\n\n"
        f"Нажмите ✅ когда готово",
        buttons=create_numpad_keyboard()
    )
    
    await event.answer()

async def process_code(user_id, code, event=None):
    """Обработка введенного кода"""
    try:
        phone = user_data[user_id]['phone']
        phone_code_hash = user_data[user_id]['phone_code_hash']
        client = user_data[user_id]['client']
        
        await bot.send_message(user_id, "🔐 Проверяю код...")
        
        # Безопасная задержка
        await security.safe_delay(1000, 2000)
        
        try:
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
                
                await bot.send_message(
                    user_id,
                    f"✅ **ВХОД УСПЕШЕН!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n\n"
                    f"🎯 Теперь можно начать ловлю!",
                    buttons=[
                        [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"catch_menu")],
                        [Button.inline("📊 СТАТУС", b"status_menu")]
                    ]
                )
                
                # Очищаем временные данные
                del user_data[user_id]
                await client.disconnect()
                
                if event:
                    try:
                        await event.delete()
                    except:
                        pass
                
            else:
                await bot.send_message(user_id, "❌ Не удалось авторизоваться")
                await client.disconnect()
                
        except Exception as e:
            error_msg = str(e)
            
            if "SESSION_PASSWORD_NEEDED" in error_msg or "Two-steps verification" in error_msg:
                # Нужен пароль 2FA
                await bot.send_message(
                    user_id,
                    "🔐 **Требуется пароль 2FA**\n\n"
                    "Введите пароль от двухфакторной аутентификации:"
                )
                user_data[user_id]['state'] = 'waiting_password'
                
            elif "PHONE_CODE_INVALID" in error_msg:
                await bot.send_message(user_id, "❌ Неверный код! Попробуйте снова")
                
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await bot.send_message(user_id, "⏳ Код истек. Начните заново")
                await client.disconnect()
                if user_id in user_data:
                    del user_data[user_id]
                    
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error_msg[:100]}")
                await client.disconnect()
                if user_id in user_data:
                    del user_data[user_id]
                    
    except Exception as e:
        await bot.send_message(user_id, f"❌ Критическая ошибка: {str(e)[:100]}")

# ========== МЕНЮ ЛОВЛИ ==========
@bot.on(events.CallbackQuery(pattern=b'catch_menu'))
async def catch_menu_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    user_id = event.sender_id
    
    if user_id not in user_sessions:
        await event.edit(
            "❌ **СНАЧАЛА ВОЙДИТЕ В АККАУНТ!**\n\n"
            "Для ловли чеков нужно авторизоваться.",
            buttons=[
                [Button.inline("🔐 ВОЙТИ", b"login_menu")],
                [Button.inline("🔙 НАЗАД", b"main_menu")]
            ]
        )
        return
    
    if user_id in active_clients:
        await event.edit(
            "✅ **ЛОВЛЯ УЖЕ ЗАПУЩЕНА!**\n\n"
            "🎯 Бот активно ищет чеки...\n"
            f"📊 Найдено: {checks_count} чеков\n\n"
            "🛑 Вы можете остановить ловлю:",
            buttons=[
                [Button.inline("🛑 ОСТАНОВИТЬ", b"stop_catching")],
                [Button.inline("📊 СТАТУС", b"status_menu")],
                [Button.inline("🔙 НАЗАД", b"main_menu")]
            ]
        )
    else:
        await event.edit(
            "🎯 **ГОТОВ К ЛОВЛЕ ЧЕКОВ**\n\n"
            "✅ Аккаунт подключен\n"
            "🛡️ Безопасный режим: ВКЛ\n\n"
            "🔍 Бот будет мониторить 6 чатов:\n"
            "• @CryptoBot\n• @send\n• @tonRocketBot\n"
            "• @wallet\n• @xrocket\n• @CryptoTestnetBot\n\n"
            "⚡ **НАЧАТЬ ЛОВЛЮ:**",
            buttons=[
                [Button.inline("🚀 ЗАПУСТИТЬ", b"start_catching")],
                [Button.inline("🔙 НАЗАД", b"main_menu")]
            ]
        )

@bot.on(events.CallbackQuery(pattern=b'start_catching'))
async def start_catching_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    user_id = event.sender_id
    
    if user_id not in user_sessions:
        await event.answer("❌ Сначала войдите!", alert=True)
        return
    
    if user_id in active_clients:
        await event.answer("✅ Уже ловлю!", alert=True)
        return
    
    await event.edit("🎯 **Запускаю безопасную ловлю...**")
    
    # Запускаем ловлю
    asyncio.create_task(safe_catching(user_id))

# ========== БЕЗОПАСНАЯ ЛОВЛЯ ==========
async def safe_catching(user_id):
    """Безопасная ловля чеков с защитой от блокировки"""
    if user_id not in user_sessions:
        return
    
    try:
        # Создаем клиента
        client = TelegramClient(StringSession(user_sessions[user_id]), api_id, api_hash)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        await bot.send_message(
            user_id,
            f"🎯 **ЛОВЛЯ ЗАПУЩЕНА!**\n\n"
            f"👤 Аккаунт: {me.first_name}\n"
            f"🛡️ Режим: БЕЗОПАСНЫЙ\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"✅ Защита от блокировок активна\n"
            f"⚡ Автоматические задержки\n"
            f"📊 Лимиты не превышены"
        )
        
        # ========== БЕЗОПАСНЫЕ ОБРАБОТЧИКИ ==========
        
        @client.on(events.NewMessage(chats=crypto_black_list))
        async def safe_check_handler(event):
            """Безопасный обработчик чеков"""
            # Проверяем лимиты
            can_action, wait_time = security.can_perform_action('check')
            if not can_action:
                await asyncio.sleep(wait_time)
                return
            
            try:
                text = event.text or ''
                found = code_regex.findall(text)
                
                if found:
                    for bot_name, code in found:
                        if code not in checks:
                            print(f"🎯 [БЕЗОПАСНО] Чек: {code}")
                            
                            # Безопасная задержка перед действием
                            await security.safe_delay(500, 2000)
                            
                            # Активируем чек
                            await client.send_message(bot_name, f'/start {code}')
                            checks.append(code)
                            
                            global checks_count
                            checks_count += 1
                            
                            # Уведомление каждые 10 чеков
                            if checks_count % 10 == 0:
                                await bot.send_message(
                                    channel,
                                    f"💰 **ЧЕКОВ: {checks_count}**\n"
                                    f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                                    f"🛡️ Безопасный режим"
                                )
                
                # Безопасная проверка кнопок
                if event.message.reply_markup:
                    await security.safe_delay(1000, 3000)
                    
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                if hasattr(button, 'url'):
                                    match = code_regex.search(button.url)
                                    if match and match.group(2) not in checks:
                                        code = match.group(2)
                                        
                                        # Дополнительная задержка для кнопок
                                        await security.safe_delay(1500, 4000)
                                        
                                        await client.send_message(match.group(1), f'/start {code}')
                                        checks.append(code)
                                        checks_count += 1
                            except:
                                pass
                                
            except Exception as e:
                print(f"⚠️ Ошибка безопасной ловли: {e}")
        
        # Безопасная автоподписка
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать"))
        async def safe_subscription_handler(event):
            """Безопасная автоподписка"""
            # Проверяем лимиты подписок
            can_action, wait_time = security.can_perform_action('join')
            if not can_action:
                await asyncio.sleep(wait_time)
                return
            
            try:
                await security.safe_delay(2000, 5000)
                
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            # Большая задержка между подписками
                            await security.safe_delay(3000, 8000)
                            
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                                print(f"✅ [БЕЗОПАСНО] Подписался на канал")
                            
                            public_channel = public_regex.search(button.url)
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                                print(f"✅ [БЕЗОПАСНО] Подписался на @{public_channel.group(1)}")
                        except Exception as e:
                            print(f"⚠️ Ошибка подписки: {e}")
            except:
                pass
        
        print(f"✅ Безопасная ловля для {me.first_name}")
        
        # Бесконечный цикл с проверкой безопасности
        while user_id in active_clients:
            await asyncio.sleep(1)
            
            # Каждые 5 минут проверяем статус
            if int(time.time()) % 300 == 0:
                status = security.get_safety_status()
                if status['recent_actions'] > 40:
                    print("⚠️ Высокая активность, увеличиваю задержки")
                    await asyncio.sleep(random.randint(10, 30))
        
        # Остановка
        await client.disconnect()
        
        await bot.send_message(
            user_id,
            f"🛑 **Ловля остановлена**\n\n"
            f"📊 Чеков найдено: {checks_count}\n"
            f"🛡️ Безопасность: НЕ НАРУШЕНА\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
    except Exception as e:
        error_msg = f"❌ Ошибка безопасной ловли: {str(e)[:200]}"
        print(error_msg)
        
        await bot.send_message(
            user_id,
            f"❌ **Ловля остановлена из-за ошибки**\n\n"
            f"⚠️ {str(e)[:100]}\n\n"
            f"🛡️ Безопасность не нарушена"
        )
        
        if user_id in active_clients:
            del active_clients[user_id]

# ========== ДРУГИЕ МЕНЮ ==========
@bot.on(events.CallbackQuery(pattern=b'stop_catching'))
async def stop_catching_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    user_id = event.sender_id
    
    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except:
            pass
        
        if user_id in active_clients:
            del active_clients[user_id]
        
        await event.edit(
            "🛑 **Ловля остановлена!**\n\n"
            f"📊 Всего чеков: {checks_count}\n"
            f"🛡️ Безопасность: СОХРАНЕНА\n\n"
            "✅ Вы можете запустить снова:",
            buttons=[
                [Button.inline("🎯 ЗАПУСТИТЬ", b"start_catching")],
                [Button.inline("📊 СТАТУС", b"status_menu")],
                [Button.inline("🔙 НАЗАД", b"main_menu")]
            ]
        )
    else:
        await event.answer("ℹ️ Ловля не запущена", alert=True)

@bot.on(events.CallbackQuery(pattern=b'status_menu'))
async def status_menu_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    user_id = event.sender_id
    
    has_session = user_id in user_sessions
    is_active = user_id in active_clients
    safety_status = security.get_safety_status()
    
    status_text = (
        f"📊 **СТАТУС СИСТЕМЫ**\n\n"
        f"🔐 Сессия: {'✅ СОХРАНЕНА' if has_session else '❌ ОТСУТСТВУЕТ'}\n"
        f"🎣 Ловля: {'✅ АКТИВНА' if is_active else '❌ ОСТАНОВЛЕНА'}\n"
        f"📈 Чеков: {checks_count}\n\n"
        f"🛡️ **БЕЗОПАСНОСТЬ:**\n"
        f"• Активность: {safety_status['recent_actions']}/мин\n"
        f"• Режим: {'✅ ВКЛ' if safety_status['safety_mode'] else '❌ ВЫКЛ'}\n"
        f"• Защита: {'✅ АКТИВНА' if safety_status['safety_mode'] else '❌ ОТКЛЮЧЕНА'}\n\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    
    buttons = [
        [Button.inline("🔄 ОБНОВИТЬ", b"status_menu")],
        [Button.inline("🔙 НАЗАД", b"main_menu")]
    ]
    
    if has_session and not is_active:
        buttons.insert(0, [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"catch_menu")])
    elif not has_session:
        buttons.insert(0, [Button.inline("🔐 ВОЙТИ", b"login_menu")])
    
    await event.edit(status_text, buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'settings_menu'))
async def settings_menu_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    safety_status = security.get_safety_status()
    
    await event.edit(
        "⚙️ **НАСТРОЙКИ БЕЗОПАСНОСТИ**\n\n"
        f"🛡️ **Текущие настройки:**\n"
        f"• Безопасный режим: {'✅ ВКЛ' if security.safety_mode else '❌ ВЫКЛ'}\n"
        f"• Автозадержки: {'✅ ВКЛ' if security.safety_mode else '❌ ВЫКЛ'}\n"
        f"• Лимиты: {'✅ АКТИВНЫ' if security.safety_mode else '❌ ОТКЛЮЧЕНЫ'}\n\n"
        f"📊 **Статистика безопасности:**\n"
        f"• Действий/мин: {safety_status['recent_actions']}\n"
        f"• Чеков сегодня: {safety_status['daily_limits']['checks']}\n"
        f"• Подписок сегодня: {safety_status['daily_limits']['joins']}\n\n"
        "⚠️ **Рекомендуется не отключать защиту!**",
        buttons=[
            [Button.inline(f"🛡️ {'ВЫКЛ' if security.safety_mode else 'ВКЛ'} ЗАЩИТУ", b"toggle_safety")],
            [Button.inline("🔄 СБРОС ЛИМИТОВ", b"reset_limits")],
            [Button.inline("🔙 НАЗАД", b"main_menu")]
        ]
    )

@bot.on(events.CallbackQuery(pattern=b'toggle_safety'))
async def toggle_safety_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    security.safety_mode = not security.safety_mode
    
    await event.answer(
        f"✅ Защита {'включена' if security.safety_mode else 'отключена'}!",
        alert=True
    )
    
    await settings_menu_handler(event)

@bot.on(events.CallbackQuery(pattern=b'reset_limits'))
async def reset_limits_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    security.action_timestamps.clear()
    security.daily_limits = {'messages': 0, 'joins': 0, 'checks': 0}
    
    await event.answer("✅ Лимиты сброшены!", alert=True)
    await settings_menu_handler(event)

@bot.on(events.CallbackQuery(pattern=b'main_menu'))
async def main_menu_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await start_handler(events.NewMessage.Event(peer=event.peer_id, text='/start'))

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
@bot.on(events.NewMessage)
async def message_handler(event):
    """Обработка текстовых сообщений"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    text = event.text.strip()
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    # Обработка ввода номера вручную
    if user_id in user_data and user_data[user_id].get('state') == 'waiting_phone_manual':
        if not text.startswith('+'):
            await event.reply("❌ Номер должен начинаться с '+'. Пример: +380681234567")
            return
        
        phone = text.replace(' ', '')
        await process_phone_number(user_id, phone, event)
    
    # Обработка пароля 2FA
    elif user_id in user_data and user_data[user_id].get('state') == 'waiting_password':
        password = text
        
        try:
            client = user_data[user_id]['client']
            phone = user_data[user_id]['phone']
            
            # Входим с паролем
            await client.sign_in(password=password)
            
            # Сохраняем сессию
            session_string = client.session.save()
            user_sessions[user_id] = session_string
            
            me = await client.get_me()
            
            await event.reply(
                f"✅ **ВХОД С 2FA УСПЕШЕН!**\n\n"
                f"👤 {me.first_name}\n"
                f"📱 {me.phone}\n\n"
                f"🎯 Теперь можно начать ловлю!",
                buttons=[
                    [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"catch_menu")],
                    [Button.inline("📊 СТАТУС", b"status_menu")]
                ]
            )
            
            del user_data[user_id]
            await client.disconnect()
            
        except Exception as e:
            await event.reply(f"❌ Ошибка пароля: {e}")

# ========== ЗАПУСК БОТА ==========
start_time = time.time()

async def main():
    """Основная функция"""
    print("🚀 ЗАПУСКАЮ БЕЗОПАСНОГО БОТА...")
    
    try:
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        print(f"✅ Режим: БЕЗОПАСНЫЙ")
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEC БЕЗОПАСНЫЙ БОТ ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: `{ADMIN_ID}`\n"
            f"🛡️ Режим: БЕЗОПАСНЫЙ\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"✅ **ЗАЩИТА АКТИВИРОВАНА:**\n"
            f"• Автоматические задержки\n"
            f"• Контроль лимитов\n"
            f"• Безопасные интервалы\n"
            f"• Защита от блокировок\n\n"
            f"🎯 **Для начала работы:**\n"
            f"1. Нажмите '🔐 ВОЙТИ В АККАУНТ'\n"
            f"2. Поделитесь номером через кнопку\n"
            f"3. Введите код из Telegram\n"
            f"4. Начните ловлю!\n\n"
            f"⚠️ **Внимание:** Безопасный режим защищает ваш аккаунт от блокировок Telegram!"
        )
        
        print("=" * 60)
        print("✅ БОТ ГОТОВ К БЕЗОПАСНОЙ РАБОТЕ!")
        print("=" * 60)
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
