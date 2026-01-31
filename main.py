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
from concurrent.futures import ThreadPoolExecutor
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
api_id = int(os.getenv('API_ID', '27258770'))
api_hash = os.getenv('API_HASH', '')
bot_token = os.getenv('BOT_TOKEN', '')
channel = os.getenv('CHANNEL', '-1004902536707')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'

print("=" * 60)
print("🤖 LOVEС CHECK BOT - ПРОДВИНУТАЯ ВЕРСИЯ")
print("=" * 60)

# Проверка
if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    print("💡 Нужны: API_ID, API_HASH, BOT_TOKEN, ADMIN_ID")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ BOT_TOKEN: установлен")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ CHANNEL: {channel}")
print(f"✅ ANTI_CAPTCHA: {ANTI_CAPTCHA}")
print("=" * 60)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
executor = ThreadPoolExecutor(max_workers=3)
user_data = {}
session_strings = {}
checks = []
wallet = []
checks_count = 0
captches = []
active_catchers = {}

# Регулярные выражения
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# Черный список чатов для мониторинга
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Бот для управления
bot = TelegramClient('lovec_bot', api_id, api_hash)

# ========== УЛУЧШЕННАЯ СИСТЕМА ЛОГИНА ==========
class LoginSystem:
    """Улучшенная система логина"""
    
    def __init__(self):
        self.login_attempts = {}
        self.last_request_time = {}
    
    async def can_request_code(self, user_id, phone):
        """Проверяет можно ли запросить код"""
        now = time.time()
        
        # Очищаем старые записи
        if user_id in self.last_request_time:
            if now - self.last_request_time[user_id] < 300:  # 5 минут
                return False, "⏳ Подождите 5 минут между запросами кода"
        
        self.last_request_time[user_id] = now
        return True, "OK"
    
    async def request_code_safe(self, client, phone):
        """Безопасный запрос кода с обработкой ошибок"""
        try:
            print(f"📞 Запрашиваю код для {phone}...")
            
            # Устанавливаем таймауты
            client.session.set_dc(2, '149.154.167.40', 443)
            
            # Пробуем получить код
            result = await client.send_code_request(
                phone,
                force_sms=False  # Не форсируем SMS
            )
            
            print(f"✅ Код запрошен успешно!")
            print(f"📱 Phone code hash: {result.phone_code_hash}")
            
            return {
                'success': True,
                'phone_code_hash': result.phone_code_hash,
                'timeout': result.timeout
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Ошибка запроса кода: {error_msg}")
            
            if "A wait of" in error_msg:
                # Парсим время ожидания
                wait_match = re.search(r"A wait of (\d+) seconds", error_msg)
                if wait_match:
                    wait_seconds = int(wait_match.group(1))
                    if wait_seconds > 3600:
                        return {
                            'success': False,
                            'error': f"⏳ Telegram ограничил запросы на {wait_seconds//3600} часов. Попробуйте позже."
                        }
                    else:
                        return {
                            'success': False,
                            'error': f"⏳ Подождите {wait_seconds} секунд перед повторной попыткой."
                        }
            
            elif "PHONE_NUMBER_INVALID" in error_msg:
                return {'success': False, 'error': "❌ Неверный номер телефона"}
            
            elif "PHONE_NUMBER_BANNED" in error_msg:
                return {'success': False, 'error': "🚫 Номер заблокирован в Telegram"}
            
            elif "PHONE_NUMBER_FLOOD" in error_msg:
                return {'success': False, 'error': "⚠️ Слишком много запросов с этого номера"}
            
            else:
                return {'success': False, 'error': f"❌ Ошибка: {error_msg[:100]}"}

login_system = LoginSystem()

# ========== ФУНКЦИИ OCR ==========
def ocr_space_sync(file: bytes):
    """Синхронное распознавание текста"""
    try:
        import requests
        payload = {
            'isOverlayRequired': False,
            'apikey': OCR_API_KEY,
            'language': 'eng',
            'OCREngine': 2
        }
        response = requests.post(
            'https://api.ocr.space/parse/image',
            data=payload,
            files={'filename': ('captcha.png', file, 'image/png')},
            timeout=10
        )
        result = response.json()
        if result.get('ParsedResults'):
            return result['ParsedResults'][0].get('ParsedText', '').replace(" ", "")
        return ""
    except:
        return ""

async def ocr_space(file: bytes):
    """Асинхронное распознавание текста"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, ocr_space_sync, file)

# ========== ИНЛАЙН КЛАВИАТУРА ==========
def create_code_keyboard(code=""):
    """Создает клавиатуру для ввода кода"""
    buttons = [
        [Button.inline("1", b"code_1"), Button.inline("2", b"code_2"), Button.inline("3", b"code_3")],
        [Button.inline("4", b"code_4"), Button.inline("5", b"code_5"), Button.inline("6", b"code_6")],
        [Button.inline("7", b"code_7"), Button.inline("8", b"code_8"), Button.inline("9", b"code_9")],
        [Button.inline("0", b"code_0"), Button.inline("⌫", b"code_del"), Button.inline("✅ Отправить", b"code_enter")]
    ]
    return buttons

# ========== ПРОВЕРКА АДМИНА ==========
async def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID

# ========== КОМАНДЫ БОТА ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Начало работы"""
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **Lovec Check Bot v2.0**\n\n"
        f"👑 Админ: <code>{ADMIN_ID}</code>\n"
        f"📢 Канал: <code>{channel}</code>\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🔹 **Основные команды:**\n"
        f"`/login` - Войти в аккаунт\n"
        f"`/logout` - Выйти из аккаунта\n"
        f"`/status` - Статус сессии\n"
        f"`/start_catch` - Начать ловлю чеков\n"
        f"`/stop_catch` - Остановить ловлю\n"
        f"`/stats` - Статистика\n\n"
        f"⚠️ **Внимание:** Используйте в ЛС!",
        parse_mode='HTML'
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    """Запуск процесса входа"""
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен!")
        return
    
    user_id = event.sender_id
    
    # Проверяем существующую сессию
    if user_id in session_strings:
        await event.reply("✅ Сессия уже сохранена! Используйте `/start_catch`")
        return
    
    await event.reply(
        "📱 **Введите номер телефона:**\n\n"
        "📌 **Формат:** `+79123456789` (с плюсом и кодом страны)\n"
        "📌 **Пример:** `+79161234567`\n\n"
        "Или отправьте `cancel` для отмены"
    )
    user_data[user_id] = {'state': 'waiting_phone'}

@bot.on(events.NewMessage(pattern='/logout'))
async def logout_handler(event):
    """Выход из аккаунта"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    if user_id in session_strings:
        del session_strings[user_id]
        if user_id in user_data:
            del user_data[user_id]
        if user_id in active_catchers:
            try:
                await active_catchers[user_id].disconnect()
            except:
                pass
            del active_catchers[user_id]
        
        await event.reply("✅ Сессия удалена!")
    else:
        await event.reply("ℹ️ Нет активной сессии")

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Статус сессии"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    if user_id in session_strings:
        try:
            # Создаем временного клиента для проверки
            client = TelegramClient(StringSession(session_strings[user_id]), api_id, api_hash)
            await client.connect()
            
            if await client.is_user_authorized():
                me = await client.get_me()
                await event.reply(
                    f"✅ **Сессия активна!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: <code>{me.id}</code>\n"
                    f"🔗 @{me.username if me.username else 'нет'}\n\n"
                    f"🎯 Ловля: {'✅ ВКЛ' if user_id in active_catchers else '❌ ВЫКЛ'}",
                    parse_mode='HTML'
                )
            else:
                await event.reply("❌ Сессия не авторизована")
            
            await client.disconnect()
        except Exception as e:
            await event.reply(f"❌ Ошибка проверки: {e}")
    else:
        await event.reply("❌ Сессия не создана. Используйте `/login`")

@bot.on(events.NewMessage(pattern='/start_catch'))
async def start_catch_handler(event):
    """Начать ловлю чеков"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id not in session_strings:
        await event.reply("❌ Сначала авторизуйтесь: `/login`")
        return
    
    if user_id in active_catchers:
        await event.reply("✅ Ловля уже запущена!")
        return
    
    await event.reply("🎯 **Запускаю ловлю чеков...**")
    
    # Запускаем ловлю в фоне
    asyncio.create_task(start_catching(user_id))

@bot.on(events.NewMessage(pattern='/stop_catch'))
async def stop_catch_handler(event):
    """Остановить ловлю"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id in active_catchers:
        # Помечаем для остановки
        user_data[user_id] = {'stop': True}
        await event.reply("🛑 Останавливаю ловлю...")
    else:
        await event.reply("ℹ️ Ловля не запущена")

@bot.on(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    """Статистика"""
    if not await is_admin(event.sender_id):
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    await event.reply(
        f"📊 **Статистика бота:**\n\n"
        f"⏰ Аптайм: {hours}ч {minutes}м\n"
        f"🎯 Активировано чеков: {checks_count}\n"
        f"📈 Уникальных чеков: {len(checks)}\n"
        f"💰 Чеки в wallet: {len(wallet)}\n"
        f"🔗 Активных сессий: {len(session_strings)}\n"
        f"🎣 Активных ловцов: {len(active_catchers)}\n\n"
        f"🔄 Перезагрузить: /start",
        parse_mode='HTML'
    )

# ========== ОБРАБОТЧИК СООБЩЕНИЙ ==========
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
    
    # Проверяем состояние пользователя
    if user_id in user_data and 'state' in user_data[user_id]:
        state = user_data[user_id]['state']
        
        if text.lower() == 'cancel':
            if user_id in user_data:
                del user_data[user_id]
            await event.reply("❌ Отменено")
            return
        
        if state == 'waiting_phone':
            phone = text
            
            # Проверяем формат номера
            if not phone.startswith('+'):
                await event.reply("❌ Номер должен начинаться с '+' (например: +79123456789)")
                return
            
            if len(phone) < 10:
                await event.reply("❌ Слишком короткий номер")
                return
            
            # Проверяем можно ли запросить код
            can_request, message = await login_system.can_request_code(user_id, phone)
            if not can_request:
                await event.reply(message)
                return
            
            await event.reply(f"📱 Проверяю номер: `{phone}`...")
            
            # Создаем клиента
            client = TelegramClient(StringSession(), api_id, api_hash)
            
            try:
                await client.connect()
                print(f"✅ Клиент подключен для {phone}")
                
                # Запрашиваем код
                result = await login_system.request_code_safe(client, phone)
                
                if result['success']:
                    # Сохраняем данные
                    user_data[user_id] = {
                        'state': 'waiting_code',
                        'phone': phone,
                        'client': client,
                        'phone_code_hash': result['phone_code_hash'],
                        'code': '',
                        'timestamp': time.time()
                    }
                    
                    await event.reply(
                        f"✅ **Код отправлен!**\n\n"
                        f"📱 Номер: `{phone}`\n"
                        f"⏳ Время ожидания: {result.get('timeout', 120)} сек\n\n"
                        f"📝 **Введите код из Telegram:**\n\n"
                        f"Используйте кнопки ниже или напишите код вручную\n"
                        f"Для отмены напишите `cancel`",
                        buttons=create_code_keyboard()
                    )
                    
                    # Сохраняем временного клиента
                    user_data[user_id]['temp_client'] = client
                    
                else:
                    await event.reply(f"❌ {result['error']}")
                    await client.disconnect()
                    if user_id in user_data:
                        del user_data[user_id]
                    
            except Exception as e:
                await event.reply(f"❌ Ошибка подключения: {e}")
                if 'client' in locals():
                    try:
                        await client.disconnect()
                    except:
                        pass
        
        elif state == 'waiting_code' and len(text) >= 5:
            # Пользователь ввел код текстом
            await process_code_input(user_id, text, event)

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Обработка инлайн кнопок"""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    data = event.data.decode()
    
    # Обработка кнопок кода
    if data.startswith('code_'):
        if user_id not in user_data or user_data[user_id].get('state') != 'waiting_code':
            await event.answer("❌ Сначала введите /login")
            return
        
        action = data.split('_')[1]
        
        if action == 'del':
            # Удалить последнюю цифру
            if user_data[user_id]['code']:
                user_data[user_id]['code'] = user_data[user_id]['code'][:-1]
        
        elif action == 'enter':
            # Отправить код
            code = user_data[user_id]['code']
            if len(code) >= 5:  # Минимальная длина кода
                await event.answer("⌛ Отправляю код...")
                await process_code_input(user_id, code, event)
            else:
                await event.answer("❌ Код слишком короткий! Нужно минимум 5 цифр", alert=True)
            return
        
        else:
            # Добавить цифру
            if len(user_data[user_id]['code']) < 10:  # Максимум 10 цифр
                user_data[user_id]['code'] += action
        
        # Обновляем сообщение
        code_display = user_data[user_id]['code'] or "____"
        phone = user_data[user_id].get('phone', '')
        
        await event.edit(
            f"📱 Номер: `{phone}`\n\n"
            f"📝 **Код:** `{code_display}`\n\n"
            f"Используйте кнопки для ввода (минимум 5 цифр)\n"
            f"Нажмите ✅ Отправить когда код будет готов",
            buttons=create_code_keyboard()
        )
        
        await event.answer()

async def process_code_input(user_id, code, event=None):
    """Обработка введенного кода"""
    try:
        if user_id not in user_data:
            await bot.send_message(user_id, "❌ Сессия истекла. Начните заново: /login")
            return
        
        phone = user_data[user_id]['phone']
        phone_code_hash = user_data[user_id]['phone_code_hash']
        client = user_data[user_id].get('temp_client')
        
        if not client:
            await bot.send_message(user_id, "❌ Клиент не найден. Начните заново: /login")
            return
        
        await bot.send_message(user_id, "🔑 Проверяю код...")
        
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
                session_strings[user_id] = session_string
                
                # Получаем информацию о пользователе
                me = await client.get_me()
                
                await bot.send_message(
                    user_id,
                    f"✅ **Успешная авторизация!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: <code>{me.id}</code>\n"
                    f"🔗 @{me.username if me.username else 'нет'}\n\n"
                    f"🎯 Теперь используйте `/start_catch` для ловли чеков\n"
                    f"💾 Сессия сохранена автоматически",
                    parse_mode='HTML'
                )
                
                # Отправляем в канал
                try:
                    await bot.send_message(
                        channel,
                        f"✅ **Новая сессия создана!**\n\n"
                        f"👤 Пользователь: {me.first_name}\n"
                        f"📱 Телефон: {me.phone}\n"
                        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                    )
                except:
                    pass
                
                # Очищаем данные
                if user_id in user_data:
                    del user_data[user_id]
                
                # Отключаем временного клиента
                await client.disconnect()
                
                if event:
                    try:
                        await event.answer("✅ Успешно!", alert=True)
                        await event.delete()
                    except:
                        pass
                
            else:
                await bot.send_message(user_id, "❌ Не удалось авторизоваться. Попробуйте снова: /login")
                await client.disconnect()
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Ошибка входа: {error_msg}")
            
            if "PHONE_CODE_INVALID" in error_msg:
                await bot.send_message(user_id, "❌ Неверный код. Попробуйте снова или напишите `cancel`")
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                await bot.send_message(user_id, "🔐 Нужен пароль 2FA. Введите пароль:")
                user_data[user_id]['state'] = 'waiting_password'
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await bot.send_message(user_id, "⏳ Код истек. Начните заново: /login")
                if user_id in user_data:
                    del user_data[user_id]
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error_msg[:100]}")
            
            try:
                await client.disconnect()
            except:
                pass
            
    except Exception as e:
        await bot.send_message(user_id, f"❌ Критическая ошибка: {e}")

# ========== ФУНКЦИЯ ЛОВЛИ ЧЕКОВ ==========
async def start_catching(user_id):
    """Запуск ловли чеков"""
    if user_id not in session_strings:
        return
    
    try:
        # Создаем клиента из сохраненной сессии
        client = TelegramClient(StringSession(session_strings[user_id]), api_id, api_hash)
        await client.start()
        
        me = await client.get_me()
        
        # Отправляем уведомление
        await bot.send_message(
            channel,
            f"🎯 **Начата ловля чеков!**\n\n"
            f"👤 Пользователь: {me.first_name}\n"
            f"📱 Телефон: {me.phone}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"✅ Мониторинг {len(crypto_black_list)} ботов"
        )
        
        # Сохраняем клиента
        active_catchers[user_id] = client
        
        # ========== ОПТИМИЗИРОВАННАЯ ЛОВЛЯ ==========
        
        @client.on(events.NewMessage(chats=crypto_black_list))
        async def handle_check_message(event):
            """Обработчик чеков"""
            global checks_count
            
            try:
                text = event.text or ''
                
                # Ищем чеки
                found_codes = code_regex.findall(text)
                
                if found_codes:
                    for bot_name, code in found_codes:
                        if code not in checks:
                            print(f"🎯 Найден чек: {code} для {bot_name}")
                            
                            # Активируем чек
                            await client.send_message(bot_name, f'/start {code}')
                            checks.append(code)
                            
                            # Счетчик
                            checks_count += 1
                
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
                print(f"⚠️ Ошибка обработки: {e}")
        
        # Обработчик для подписок на каналы
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать этот чек"))
        async def handle_subscription(event):
            """Автоподписка на каналы"""
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            # Подписка на приватные каналы
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                            
                            # Подписка на публичные каналы
                            public_channel = public_regex.search(button.url)
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                                
                        except:
                            pass
            except:
                pass
        
        # Обработчик успешных активаций
        async def success_filter(event):
            for word in ['Вы получили', 'Вы обналичили чек на сумму:', '✅ Вы получили:', '💰 Вы получили']:
                if word in event.text:
                    return True
            return False
        
        @client.on(events.NewMessage(chats=crypto_black_list, func=success_filter))
        async def handle_success(event):
            """Обработка успешных активаций"""
            try:
                summ = event.text.split('\n')[0]
                summ = summ.replace('Вы получили ', '').replace('✅ Вы получили: ', '').replace('💰 Вы получили ', '').replace('Вы обналичили чек на сумму: ', '')
                
                await bot.send_message(
                    channel,
                    f"💰 **Чек активирован!**\n\n"
                    f"🎯 Сумма: {summ}\n"
                    f"👤 От: {me.first_name}\n"
                    f"📊 Всего: {checks_count}\n"
                    f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
        # Обработчик капч
        if ANTI_CAPTCHA and OCR_API_KEY:
            @client.on(events.NewMessage(chats=[1559501630], func=lambda e: e.photo))
            async def handle_captcha(event):
                """Обработка капч"""
                try:
                    photo = await event.download_media(bytes)
                    recognized_text = await ocr_space(photo)
                    
                    if recognized_text and recognized_text not in captches:
                        await client.send_message('CryptoBot', recognized_text)
                        captches.append(recognized_text)
                except:
                    pass
        
        print(f"✅ Ловля запущена для {me.first_name}")
        
        # Ждем остановки
        while user_id in active_catchers:
            if user_id in user_data and user_data.get(user_id, {}).get('stop'):
                break
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        if user_id in active_catchers:
            del active_catchers[user_id]
        
        await bot.send_message(
            channel,
            f"🛑 **Ловля остановлена!**\n\n"
            f"👤 Пользователь: {me.first_name}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Всего чеков: {checks_count}"
        )
        
    except Exception as e:
        await bot.send_message(
            channel,
            f"❌ **Ошибка ловли!**\n\n"
            f"👤 Пользователь ID: {user_id}\n"
            f"⚠️ Ошибка: {str(e)[:200]}"
        )
        print(f"❌ Ошибка start_catching: {e}")

# ========== ЗАПУСК ==========
start_time = time.time()

async def main():
    """Основная функция"""
    print("🔄 Запускаю Lovec Check Bot...")
    
    try:
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ ID: {ADMIN_ID}")
        print(f"✅ Канал: {channel}")
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **Lovec Check Bot запущен!**\n\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"🔗 Бот: @{me.username}\n"
            f"🆔 ID: {me.id}\n\n"
            f"📋 Команды:\n"
            f"/start - Показать меню\n"
            f"/login - Войти в аккаунт\n"
            f"/start_catch - Начать ловлю\n\n"
            f"🌐 Хостинг: songaura.onrender.com"
        )
        
        print("=" * 60)
        print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
        print("=" * 60)
        print("📋 Инструкция:")
        print("1. Напишите боту /start")
        print("2. Используйте /login для входа")
        print("3. Введите номер (+79123456789)")
        print("4. Введите код через кнопки")
        print("5. Используйте /start_catch для ловли чеков")
        print("=" * 60)
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
