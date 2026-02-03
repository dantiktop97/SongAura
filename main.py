import os
import asyncio
import time
import re
import random
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from concurrent.futures import ThreadPoolExecutor
import requests
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
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'
AVTO_VIVOD = os.getenv('AVTO_VIVOD', 'False').lower() == 'true'
AVTO_VIVOD_TAG = os.getenv('AVTO_VIVOD_TAG', '')

print("=" * 60)
print("🤖 LOVEС CHECK BOT - ПРОФЕССИОНАЛЬНАЯ ВЕРСИЯ")
print("=" * 60)

if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ ANTI_CAPTCHA: {ANTI_CAPTCHA}")
print(f"✅ AVTO_VIVOD: {AVTO_VIVOD}")
print("=" * 60)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
executor = ThreadPoolExecutor(max_workers=5)
user_sessions = {}
active_clients = {}
user_data = {}
checks = []
wallet = []
channels = []
captches = []
checks_count = 0
start_time = time.time()

# Регулярные выражения
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

replace_chars = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
translation = str.maketrans('', '', replace_chars)

# Черный список чатов для мониторинга
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Бот для управления
bot = TelegramClient('lovec_bot', api_id, api_hash)

# ========== ФУНКЦИИ OCR ==========
def ocr_space_sync(file: bytes, overlay=False, language='eng', scale=True, OCREngine=2):
    payload = {
        'isOverlayRequired': overlay,
        'apikey': OCR_API_KEY,
        'language': language,
        'scale': scale,
        'OCREngine': OCREngine
    }
    response = requests.post(
        'https://api.ocr.space/parse/image',
        data=payload,
        files={'filename': ('image.png', file, 'image/png')}
    )
    result = response.json()
    return result.get('ParsedResults')[0].get('ParsedText', '').replace(" ", "")

async def ocr_space(file: bytes, overlay=False, language='eng'):
    loop = asyncio.get_running_loop()
    recognized_text = await loop.run_in_executor(
        executor, ocr_space_sync, file, overlay, language
    )
    return recognized_text

# ========== АВТОВЫВОД ==========
async def pay_out():
    """Автоматический вывод средств"""
    await asyncio.sleep(86400)  # 24 часа
    
    try:
        # Здесь client должен быть определен в контексте
        if 'client' not in globals():
            return
            
        await client.send_message('CryptoBot', message='/wallet')
        await asyncio.sleep(1)
        
        messages = await client.get_messages('CryptoBot', limit=1)
        if messages:
            message = messages[0].message
            lines = message.split('\n\n')
            
            for line in lines:
                if ':' in line:
                    if 'Доступно' in line:
                        data = line.split('\n')[2].split('Доступно: ')[1].split(' (')[0].split(' ')
                        summ = data[0]
                        curency = data[1]
                    else:
                        data = line.split(': ')[1].split(' (')[0].split(' ')
                        summ = data[0]
                        curency = data[1]
                    
                    try:
                        if summ == '0':
                            continue
                            
                        result = (await client.inline_query('send', f'{summ} {curency}'))[0]
                        if 'Создать чек' in result.title:
                            await result.click(AVTO_VIVOD_TAG)
                            print(f"✅ Выведено {summ} {curency} на {AVTO_VIVOD_TAG}")
                            
                    except Exception as e:
                        print(f"❌ Ошибка вывода: {e}")
    except Exception as e:
        print(f"❌ Ошибка в pay_out: {e}")

# ========== ИНЛАЙН КНОПКИ ==========
def create_main_menu():
    """Создает главное меню"""
    return [
        [Button.inline("🔐 ВОЙТИ В АККАУНТ", b"login")],
        [Button.inline("🎯 НАЧАТЬ ЛОВЛЮ", b"start_catch")],
        [Button.inline("🛑 ОСТАНОВИТЬ", b"stop_catch")],
        [Button.inline("📊 СТАТИСТИКА", b"stats")]
    ]

def create_login_menu():
    """Создает меню входа"""
    return [
        [Button.request_phone("📱 ПОДЕЛИТЬСЯ НОМЕРОМ")],
        [Button.inline("✏️ ВВЕСТИ ВРУЧНУЮ", b"manual_login")],
        [Button.inline("🔙 НАЗАД", b"main_menu")]
    ]

def create_numpad_keyboard():
    """Создает цифровую клавиатуру"""
    return [
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
            Button.inline("✅", b"num_enter")
        ]
    ]

# ========== ПРОВЕРКА АДМИНА ==========
async def is_admin(user_id):
    return user_id == ADMIN_ID

# ========== КОМАНДЫ БОТА ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Этот бот только для администратора!")
        return
    
    await event.reply(
        f"🤖 **LOVEC CHECK BOT**\n\n"
        f"👑 Админ ID: `{ADMIN_ID}`\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"📊 Чеков: {checks_count}\n\n"
        f"🎯 **ВЫБЕРИТЕ ДЕЙСТВИЕ:**",
        buttons=create_main_menu()
    )

# ========== ОБРАБОТЧИКИ КНОПОК ==========
@bot.on(events.CallbackQuery(data=b'main_menu'))
async def main_menu_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await event.edit(
        f"🤖 **LOVEC CHECK BOT**\n\n"
        f"👑 Админ ID: `{ADMIN_ID}`\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"📊 Чеков: {checks_count}\n\n"
        f"🎯 **ВЫБЕРИТЕ ДЕЙСТВИЕ:**",
        buttons=create_main_menu()
    )

@bot.on(events.CallbackQuery(data=b'login'))
async def login_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await event.edit(
        "🔐 **ВХОД В АККАУНТ**\n\n"
        "📱 **ВЫБЕРИТЕ СПОСОБ ВХОДА:**\n\n"
        "1. 📲 Поделиться номером (рекомендуется)\n"
        "2. ✏️ Ввести номер вручную\n\n"
        "✅ После входа бот начнет ловить чеки автоматически!",
        buttons=create_login_menu()
    )

@bot.on(events.CallbackQuery(data=b'manual_login'))
async def manual_login_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await event.edit(
        "✏️ **ВВОД НОМЕРА ВРУЧНУЮ**\n\n"
        "📱 Отправьте номер телефона в формате:\n\n"
        "📌 **Примеры:**\n"
        "• +380681234567 (Украина)\n"
        "• +79123456789 (Россия)\n"
        "• +12345678900 (США/Канада)\n\n"
        "✏️ Просто отправьте номер сообщением",
        buttons=[[Button.inline("🔙 НАЗАД", b"login")]]
    )
    
    user_data[event.sender_id] = {'state': 'waiting_phone'}

@bot.on(events.CallbackQuery(data=b'start_catch'))
async def start_catch_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    user_id = event.sender_id
    
    if user_id not in user_sessions:
        await event.answer("❌ Сначала войдите в аккаунт!", alert=True)
        return
    
    if user_id in active_clients:
        await event.answer("✅ Ловля уже запущена!", alert=True)
        return
    
    await event.answer("🎯 Запускаю ловлю...")
    await event.edit("🎯 **Запускаю ловлю чеков...**")
    
    # Запускаем ловлю
    asyncio.create_task(start_catching(user_id))

@bot.on(events.CallbackQuery(data=b'stop_catch'))
async def stop_catch_handler(event):
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
        
        await event.answer("🛑 Ловля остановлена!")
        await event.edit(
            "🛑 **Ловля остановлена!**\n\n"
            f"📊 Всего чеков: {checks_count}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}",
            buttons=create_main_menu()
        )
    else:
        await event.answer("ℹ️ Ловля не запущена", alert=True)

@bot.on(events.CallbackQuery(data=b'stats'))
async def stats_handler(event):
    if not await is_admin(event.sender_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    await event.edit(
        f"📊 **СТАТИСТИКА**\n\n"
        f"⏳ Работает: {hours}ч {minutes}м\n"
        f"🎯 Чеков: {checks_count}\n"
        f"📈 Уникальных: {len(checks)}\n"
        f"💰 В wallet: {len(wallet)}\n"
        f"🔤 Капч: {len(captches)}\n\n"
        f"🌐 songaura.onrender.com",
        buttons=[[Button.inline("🔙 НАЗАД", b"main_menu")]]
    )

# ========== ОБРАБОТКА КОНТАКТА ==========
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
    await process_phone_number(event.sender_id, phone)

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
    
    # Обработка ввода номера
    if user_id in user_data and user_data[user_id].get('state') == 'waiting_phone':
        if not text.startswith('+'):
            await event.reply("❌ Номер должен начинаться с '+'. Пример: +380681234567")
            return
        
        phone = text.replace(' ', '')
        await process_phone_number(user_id, phone)
    
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
                f"🎯 Начинаю ловлю чеков...",
                buttons=create_main_menu()
            )
            
            del user_data[user_id]
            await client.disconnect()
            
            # Автозапуск ловли
            asyncio.create_task(start_catching(user_id))
            
        except Exception as e:
            await event.reply(f"❌ Ошибка пароля: {e}")

async def process_phone_number(user_id, phone):
    """Обработка номера телефона"""
    try:
        # Создаем клиента
        client = TelegramClient(StringSession(), api_id, api_hash)
        
        # Настраиваем
        client.session.set_dc(2, '149.154.167.40', 443)
        
        await client.connect()
        
        # Запрашиваем код
        sent_code = await client.send_code_request(phone)
        
        # Сохраняем данные
        user_data[user_id] = {
            'state': 'waiting_code',
            'phone': phone,
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash,
            'code': '',
            'timestamp': time.time()
        }
        
        await bot.send_message(
            user_id,
            f"✅ **Код отправлен!**\n\n"
            f"📱 Номер: `{phone}`\n"
            f"⏳ Код действует: {sent_code.timeout} сек\n\n"
            f"📝 **Введите код из Telegram:**\n\n"
            f"Используйте цифровую клавиатуру ниже",
            buttons=create_numpad_keyboard()
        )
        
    except Exception as e:
        error_msg = str(e)
        await bot.send_message(user_id, f"❌ Ошибка: {error_msg[:100]}")
        if user_id in user_data:
            del user_data[user_id]

# ========== ОБРАБОТКА ЦИФРОВОЙ КЛАВИАТУРЫ ==========
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
    
    elif action == 'enter':
        code = user_data[user_id].get('code', '')
        if len(code) >= 5:
            await event.answer("🔐 Проверяю код...")
            await process_code_input(user_id, code, event)
            return
        else:
            await event.answer("❌ Нужно минимум 5 цифр!", alert=True)
            return
    
    else:
        if len(current_code) < 10:
            user_data[user_id]['code'] = current_code + action
    
    # Обновляем отображение
    new_code = user_data[user_id].get('code', '')
    phone = user_data[user_id].get('phone', '')
    
    dots = "•" * len(new_code) if new_code else "____"
    
    await event.edit(
        f"📱 Номер: `{phone}`\n\n"
        f"🔢 **Код:** `{dots}`\n"
        f"📝 Введено: {len(new_code)} цифр\n\n"
        f"Нажмите ✅ когда готово",
        buttons=create_numpad_keyboard()
    )
    
    await event.answer()

async def process_code_input(user_id, code, event):
    """Обработка введенного кода"""
    try:
        phone = user_data[user_id]['phone']
        phone_code_hash = user_data[user_id]['phone_code_hash']
        client = user_data[user_id]['client']
        
        await bot.send_message(user_id, "🔐 Проверяю код...")
        
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
                    f"🎯 **Начинаю ловлю чеков...**",
                    buttons=create_main_menu()
                )
                
                # Очищаем временные данные
                del user_data[user_id]
                await client.disconnect()
                
                if event:
                    try:
                        await event.delete()
                    except:
                        pass
                
                # Автозапуск ловли
                asyncio.create_task(start_catching(user_id))
                
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

# ========== ЛОВЛЯ ЧЕКОВ ==========
async def start_catching(user_id):
    """Запуск ловли чеков (как в примере)"""
    if user_id not in user_sessions:
        return
    
    try:
        # Создаем клиента из сохраненной сессии
        client = TelegramClient(StringSession(user_sessions[user_id]), api_id, api_hash)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        # Подписываемся на канал
        try:
            await client(JoinChannelRequest('lovec_checkov'))
        except:
            pass
        
        # Автовывод
        if AVTO_VIVOD and AVTO_VIVOD_TAG:
            try:
                message = await client.send_message(AVTO_VIVOD_TAG, message='1')
                await client.delete_messages(AVTO_VIVOD_TAG, message_ids=[message.id])
                asyncio.create_task(pay_out())
                print(f"✅ Автовывод подключен на {AVTO_VIVOD_TAG}")
            except Exception as e:
                print(f"⚠️ Автовывод: {e}")
        
        # Отправляем уведомление
        await bot.send_message(
            channel,
            f"🎯 **ЛОВЛЯ ЗАПУЩЕНА!**\n\n"
            f"👤 Пользователь: {me.first_name}\n"
            f"📱 Телефон: {me.phone}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
        )
        
        print(f"✅ Ловля запущена для {me.first_name}")
        
        # ========== ОБРАБОТЧИКИ КАК В ПРИМЕРЕ ==========
        
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать этот чек, так как вы не являетесь подписчиком канала"))
        async def handle_subscription_1(event):
            code = None
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            check = code_regex.search(button.url)
                            if check:
                                code = check.group(2)
                        except:
                            pass
                        
                        channel_match = url_regex.search(button.url)
                        public_channel = public_regex.search(button.url)
                        
                        if channel_match:
                            await client(ImportChatInviteRequest(channel_match.group(1)))
                        
                        if public_channel:
                            await client(JoinChannelRequest(public_channel.group(1)))
                        except:
                            pass
            except AttributeError:
                pass
            
            if code and code not in wallet:
                await client.send_message('wallet', message=f'/start {code}')
                wallet.append(code)
                print(f"✅ Активирован чек в wallet: {code}")
        
        @client.on(events.NewMessage(chats=[1559501630], pattern="Чтобы"))
        async def handle_subscription_2(event):
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                        except:
                            pass
            except AttributeError:
                pass
            
            await event.message.click(data=b'check-subscribe')
        
        @client.on(events.NewMessage(chats=[5014831088], pattern="Для активации чека"))
        async def handle_subscription_3(event):
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            channel_match = url_regex.search(button.url)
                            public_channel = public_regex.search(button.url)
                            
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                            
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                        except:
                            pass
            except AttributeError:
                pass
            
            await event.message.click(data=b'Check')
        
        @client.on(events.NewMessage(chats=[5794061503]))
        async def handle_subscription_4(event):
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            if hasattr(button, 'data'):
                                try:
                                    if button.data.decode().startswith(('showCheque_', 'activateCheque_')):
                                        await event.message.click(data=button.data)
                                except:
                                    pass
                            
                            channel_match = url_regex.search(button.url)
                            public_channel = public_regex.search(button.url)
                            
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                            
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                        except Exception as e:
                            print(f"⚠️ Ошибка обработки: {e}")
            except AttributeError:
                pass
        
        # Фильтр для успешных активаций
        async def filter_success(event):
            for word in ['Вы получили', 'Вы обналичили чек на сумму:', '✅ Вы получили:', '💰 Вы получили']:
                if word in event.message.text:
                    return True
            return False
        
        @client.on(events.MessageEdited(chats=crypto_black_list, func=filter_success))
        @client.on(events.NewMessage(chats=crypto_black_list, func=filter_success))
        async def handle_success(event):
            try:
                entity = await client.get_entity(event.message.peer_id.user_id)
                
                if hasattr(entity, 'usernames') and entity.usernames:
                    bot_username = entity.usernames[0].username
                elif hasattr(entity, 'username'):
                    bot_username = entity.username
                else:
                    bot_username = "Неизвестно"
            except:
                bot_username = "Неизвестно"
            
            # Извлекаем сумму
            summ = event.raw_text.split('\n')[0]
            summ = summ.replace('Вы получили ', '').replace('✅ Вы получили: ', '').replace('💰 Вы получили ', '').replace('Вы обналичили чек на сумму: ', '')
            
            # Обновляем счетчик
            global checks_count
            checks_count += 1
            
            # Отправляем уведомление
            try:
                await client.send_message(
                    channel, 
                    message=f'✅ Активирован чек на сумму <b>{summ}</b>\n🤖 Бот: <b>@{bot_username}</b>\n📊 Всего чеков: <b>{checks_count}</b>', 
                    parse_mode='HTML'
                )
                print(f"💰 Активирован чек на {summ} от @{bot_username}")
            except Exception as e:
                print(f"❌ Ошибка отправки уведомления: {e}")
        
        # Основной обработчик чеков
        @client.on(events.MessageEdited(outgoing=False, chats=crypto_black_list, blacklist_chats=True))
        @client.on(events.NewMessage(outgoing=False, chats=crypto_black_list, blacklist_chats=True))
        async def handle_checks(event):
            try:
                # Очищаем текст
                message_text = event.message.text.translate(translation)
                
                # Ищем коды чеков
                found_codes = code_regex.findall(message_text)
                
                if found_codes:
                    for bot_name, code in found_codes:
                        if code not in checks:
                            print(f"🎯 Найден чек: {code} для {bot_name}")
                            await client.send_message(bot_name, message=f'/start {code}')
                            checks.append(code)
                
                # Проверяем кнопки
                if event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                if hasattr(button, 'url'):
                                    match = code_regex.search(button.url)
                                    if match and match.group(2) not in checks:
                                        code = match.group(2)
                                        await client.send_message(match.group(1), message=f'/start {code}')
                                        checks.append(code)
                            except AttributeError:
                                pass
                                
            except Exception as e:
                print(f"⚠️ Ошибка обработки сообщения: {e}")
        
        # Обработчик капч
        if ANTI_CAPTCHA and OCR_API_KEY:
            @client.on(events.NewMessage(chats=[1559501630], func=lambda e: e.photo))
            async def handle_captcha(event):
                try:
                    print("🖼️ Обнаружена каптча...")
                    
                    # Скачиваем изображение
                    photo = await event.download_media(bytes)
                    
                    # Распознаем текст
                    recognized_text = await ocr_space(file=photo)
                    
                    if recognized_text and recognized_text not in captches:
                        print(f"🔤 Распознан текст: {recognized_text}")
                        
                        # Отправляем ответ
                        await client.send_message('CryptoBot', message=recognized_text)
                        await asyncio.sleep(1)
                        
                        # Проверяем результат
                        messages = await client.get_messages('CryptoBot', limit=1)
                        if messages and ('Incorrect answer.' in messages[0].message or 'Неверный ответ.' in messages[0].message):
                            print("❌ Каптча неверна")
                            await client.send_message(channel, message='<b>❌ Не удалось разгадать каптчу</b>', parse_mode='HTML')
                            captches.append(recognized_text)
                        else:
                            print("✅ Каптча решена успешно")
                            captches.append(recognized_text)
                    else:
                        print("⚠️ Не удалось распознать каптчу")
                        
                except Exception as e:
                    print(f"❌ Ошибка обработки каптчи: {e}")
        
        # Ждем пока не остановят
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        if user_id in active_clients:
            del active_clients[user_id]
        
        await bot.send_message(
            channel,
            f"🛑 **Ловля остановлена!**\n\n"
            f"👤 Пользователь: {me.first_name}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
            f"📊 Всего чеков: {checks_count}"
        )
        
    except Exception as e:
        print(f"❌ Ошибка ловли: {e}")
        if user_id in active_clients:
            del active_clients[user_id]

# ========== ЗАПУСК БОТА ==========
async def main():
    """Основная функция"""
    print("🚀 ЗАПУСКАЮ LOVEС CHECK BOT...")
    
    try:
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEC CHECK BOT ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: `{ADMIN_ID}`\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🎯 **КАК НАЧАТЬ:**\n"
            f"1. Нажмите '🔐 ВОЙТИ В АККАУНТ'\n"
            f"2. Поделитесь номером через кнопку\n"
            f"3. Введите код через клавиатуру\n"
            f"4. Наслаждайтесь ловлей чеков!\n\n"
            f"⚡ **АВТОМАТИЧЕСКИ:**\n"
            f"• Ловит чеки из 6 ботов\n"
            f"• Автоподписка на каналы\n"
            f"• Решает капчи (если включено)\n"
            f"• Уведомления в канал"
        )
        
        print("=" * 60)
        print("✅ БОТ ГОТОВ К РАБОТЕ!")
        print("=" * 60)
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
