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
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
api_id = int(os.getenv('API_ID', '27258770'))
api_hash = os.getenv('API_HASH', '')
bot_token = os.getenv('LOVEC', '')  # Используем LOVEC вместо BOT_TOKEN
channel = os.getenv('CHANNEL', '-1004902536707')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'

print("=" * 60)
print("🤖 LOVEС CHECK BOT - УНИВЕРСАЛЬНАЯ ВЕРСИЯ")
print("=" * 60)

# Проверка
if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    print("💡 Нужны: API_ID, API_HASH, LOVEC (бот-токен), ADMIN_ID")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ LOVEC токен: {'установлен' if bot_token else 'НЕТ!'}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ CHANNEL: {channel}")
print("=" * 60)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_data = {}  # Временные данные пользователей
user_sessions = {}  # Сохраненные сессии {user_id: session_string}
active_clients = {}  # Активные клиенты для ловли
checks = []  # Найденные чеки
wallet = []  # Чеки для @wallet
checks_count = 0  # Счетчик активированных чеков
captches = []  # Распознанные капчи

# Регулярные выражения для поиска чеков
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# Список чатов для мониторинга (ID ботов)
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Спецсимволы для очистки текста
replace_chars = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
translation = str.maketrans('', '', replace_chars)

# Бот для управления
bot = TelegramClient('lovec_bot', api_id, api_hash)

# ========== УНИВЕРСАЛЬНАЯ ЦИФРОВАЯ КЛАВИАТУРА ==========
def create_smart_keyboard(code="", show_delete=True):
    """Создает умную клавиатуру для ввода кода"""
    buttons = []
    
    # Первый ряд: 1 2 3
    buttons.append([
        Button.inline("1", b"k_1"),
        Button.inline("2", b"k_2"), 
        Button.inline("3", b"k_3")
    ])
    
    # Второй ряд: 4 5 6
    buttons.append([
        Button.inline("4", b"k_4"),
        Button.inline("5", b"k_5"), 
        Button.inline("6", b"k_6")
    ])
    
    # Третий ряд: 7 8 9
    buttons.append([
        Button.inline("7", b"k_7"),
        Button.inline("8", b"k_8"), 
        Button.inline("9", b"k_9")
    ])
    
    # Четвертый ряд: специальные кнопки
    fourth_row = [
        Button.inline("0", b"k_0"),
        Button.inline("✅ Отправить", b"k_done")
    ]
    
    if show_delete and code:
        fourth_row.insert(0, Button.inline("⌫ Удалить", b"k_del"))
    
    buttons.append(fourth_row)
    
    return buttons

# ========== ПРОВЕРКА АДМИНА ==========
async def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Команда /start - главное меню"""
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен! Этот бот только для админа.")
        return
    
    await event.reply(
        f"🤖 **LOVEC CHECK BOT**\n\n"
        f"📍 **Универсальная версия**\n"
        f"👑 Админ ID: `{ADMIN_ID}`\n"
        f"📢 Канал: `{channel}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🎯 **ОСНОВНЫЕ КОМАНДЫ:**\n"
        f"• /login - Войти в аккаунт (любой номер)\n"
        f"• /phone - Ввести номер телефона\n"
        f"• /status - Статус сессии\n"
        f"• /catch - Начать ловлю чеков\n"
        f"• /stop - Остановить ловлю\n"
        f"• /stats - Статистика\n"
        f"• /clear - Очистить данные\n\n"
        f"🌐 **Хостинг:** songaura.onrender.com",
        parse_mode='HTML',
        buttons=[
            [Button.inline("📱 Войти в аккаунт", b"main_login")],
            [Button.inline("🎯 Начать ловлю", b"main_catch")],
            [Button.inline("📊 Статистика", b"main_stats")]
        ]
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    """Команда /login - начать процесс входа"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    # Проверяем есть ли уже сессия
    if user_id in user_sessions:
        await event.reply(
            "✅ Сессия уже сохранена!\n\n"
            "🎯 Используйте /catch чтобы начать ловлю чеков\n"
            "🗑️ Используйте /clear чтобы удалить сессию",
            buttons=[
                [Button.inline("🎯 Начать ловлю", b"main_catch")],
                [Button.inline("🗑️ Удалить сессию", b"clear_session")]
            ]
        )
        return
    
    await event.reply(
        "🔑 **ВХОД В АККАУНТ**\n\n"
        "📱 **Введите номер телефона:**\n\n"
        "📌 **Формат:** с кодом страны\n"
        "• Пример: `+79123456789` (Россия)\n"
        "• Пример: `+380681234567` (Украина)\n"
        "• Пример: `+12345678900` (США/Канада)\n\n"
        "🌍 **Поддерживаются все страны!**\n\n"
        "✏️ Отправьте номер сообщением или нажмите кнопку:",
        buttons=[
            [Button.inline("📱 Ввести номер", b"enter_phone")],
            [Button.inline("❌ Отмена", b"cancel_action")]
        ]
    )

@bot.on(events.NewMessage(pattern='/phone'))
async def phone_handler(event):
    """Команда для ввода номера напрямую"""
    if not await is_admin(event.sender_id):
        return
    
    await event.reply(
        "📱 **Введите номер телефона:**\n\n"
        "Просто отправьте номер в формате:\n"
        "`+код_страны номер`\n\n"
        "Примеры:\n"
        "• `+79161234567`\n"
        "• `+380681234567`\n"
        "• `+12345678900`\n\n"
        "Или напишите `cancel` для отмены"
    )
    
    user_data[event.sender_id] = {'state': 'waiting_phone'}

@bot.on(events.NewMessage(pattern='/catch'))
async def catch_handler(event):
    """Команда /catch - начать ловлю чеков"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id not in user_sessions:
        await event.reply(
            "❌ **Сначала войдите в аккаунт!**\n\n"
            "Используйте команду /login чтобы создать сессию.",
            buttons=[
                [Button.inline("📱 Войти в аккаунт", b"main_login")]
            ]
        )
        return
    
    if user_id in active_clients:
        await event.reply("✅ Ловля уже запущена!")
        return
    
    await event.reply(
        "🎯 **ЗАПУСК ЛОВЛИ ЧЕКОВ**\n\n"
        "⏳ Подключаюсь к аккаунту...\n"
        "🔍 Начинаю мониторинг 6 ботов...",
        buttons=[
            [Button.inline("🔄 Обновить статус", b"refresh_status")]
        ]
    )
    
    # Запускаем ловлю в фоне
    asyncio.create_task(start_check_catching(user_id))

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_handler(event):
    """Команда /stop - остановить ловлю"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except:
            pass
        
        if user_id in active_clients:
            del active_clients[user_id]
        
        await event.reply("🛑 Ловля чеков остановлена!")
        
        # Отправляем в канал
        try:
            await bot.send_message(
                channel,
                f"🛑 **Ловля остановлена**\n\n"
                f"👤 Админ: `{ADMIN_ID}`\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"📊 Всего чеков: {checks_count}"
            )
        except:
            pass
    else:
        await event.reply("ℹ️ Ловля не запущена")

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Команда /status - показать статус"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    has_session = user_id in user_sessions
    is_active = user_id in active_clients
    
    status_text = (
        f"📊 **СТАТУС СИСТЕМЫ**\n\n"
        f"🔐 Сессия: {'✅ СОХРАНЕНА' if has_session else '❌ ОТСУТСТВУЕТ'}\n"
        f"🎣 Ловля: {'✅ АКТИВНА' if is_active else '❌ ОСТАНОВЛЕНА'}\n"
        f"📈 Чеков найдено: {checks_count}\n"
        f"💰 В wallet: {len(wallet)}\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n\n"
    )
    
    if has_session:
        status_text += "🎯 Используйте /catch для запуска"
    else:
        status_text += "📱 Используйте /login для входа"
    
    await event.reply(
        status_text,
        buttons=[
            [Button.inline("🔄 Обновить", b"refresh_status")],
            [Button.inline("📱 Войти", b"main_login")] if not has_session else [],
            [Button.inline("🎯 Ловить", b"main_catch")] if has_session and not is_active else []
        ]
    )

@bot.on(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    """Команда /stats - статистика"""
    if not await is_admin(event.sender_id):
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    await event.reply(
        f"📈 **СТАТИСТИКА БОТА**\n\n"
        f"⏳ Работает: {hours}ч {minutes}м\n"
        f"🎯 Активировано чеков: {checks_count}\n"
        f"📊 Уникальных кодов: {len(checks)}\n"
        f"💰 Для @wallet: {len(wallet)}\n"
        f"🔗 Активных сессий: {len(user_sessions)}\n"
        f"🎣 Активных ловцов: {len(active_clients)}\n\n"
        f"🌐 URL: songaura.onrender.com\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}",
        buttons=[
            [Button.inline("🔄 Обновить", b"refresh_stats")],
            [Button.inline("🎯 Начать ловлю", b"main_catch")],
            [Button.inline("📊 Детальная статистика", b"detailed_stats")]
        ]
    )

@bot.on(events.NewMessage(pattern='/clear'))
async def clear_handler(event):
    """Команда /clear - очистить данные"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    # Останавливаем ловлю если запущена
    if user_id in active_clients:
        try:
            await active_clients[user_id].disconnect()
        except:
            pass
        del active_clients[user_id]
    
    # Удаляем сессию
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    # Очищаем временные данные
    if user_id in user_data:
        del user_data[user_id]
    
    await event.reply(
        "🧹 **Данные очищены!**\n\n"
        "✅ Сессия удалена\n"
        "✅ Ловля остановлена\n"
        "✅ Временные данные очищены\n\n"
        "📱 Используйте /login для нового входа",
        buttons=[
            [Button.inline("📱 Войти заново", b"main_login")]
        ]
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
    
    # Обработка ввода номера телефона
    if user_id in user_data and user_data[user_id].get('state') == 'waiting_phone':
        if text.lower() == 'cancel':
            if user_id in user_data:
                del user_data[user_id]
            await event.reply("❌ Отменено")
            return
        
        # Проверяем формат номера
        if not re.match(r'^\+\d{10,15}$', text.replace(' ', '')):
            await event.reply(
                "❌ **Неверный формат номера!**\n\n"
                "📌 Должен быть:\n"
                "• Начинаться с '+'\n"
                "• Содержать код страны\n"
                "• 10-15 цифр\n\n"
                "Пример: `+79161234567`\n"
                "Попробуйте еще раз или напишите `cancel`:"
            )
            return
        
        phone = text.replace(' ', '')
        await process_phone_input(user_id, phone, event)

async def process_phone_input(user_id, phone, event):
    """Обработка введенного номера телефона"""
    try:
        await event.reply(f"📱 **Проверяю номер:** `{phone}`\n\n⏳ Запрашиваю код...")
        
        # Создаем временного клиента
        client = TelegramClient(StringSession(), api_id, api_hash)
        
        # Настраиваем для лучшей совместимости
        client.session.set_dc(2, '149.154.167.40', 443)
        
        await client.connect()
        
        # Запрашиваем код (универсальный метод)
        try:
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
            
            await event.reply(
                f"✅ **Код отправлен!**\n\n"
                f"📱 Номер: `{phone}`\n"
                f"🌍 Страна: {get_country_from_phone(phone)}\n"
                f"⏳ Код действует: {sent_code.timeout} сек\n\n"
                f"📝 **Введите код:**\n\n"
                f"Используйте клавиатуру ниже или напишите код цифрами\n"
                f"Нажмите ✅ Отправить когда код будет готов",
                buttons=create_smart_keyboard()
            )
            
        except Exception as e:
            error_msg = str(e)
            await event.reply(f"❌ **Ошибка:** {error_msg[:150]}")
            await client.disconnect()
            if user_id in user_data:
                del user_data[user_id]
            
    except Exception as e:
        await event.reply(f"❌ **Критическая ошибка:** {str(e)[:100]}")

def get_country_from_phone(phone):
    """Определяет страну по коду телефона"""
    country_codes = {
        '1': '🇺🇸 США/Канада',
        '7': '🇷🇺 Россия/Казахстан',
        '380': '🇺🇦 Украина',
        '375': '🇧🇾 Беларусь',
        '370': '🇱🇹 Литва',
        '371': '🇱🇻 Латвия',
        '372': '🇪🇪 Эстония',
        '90': '🇹🇷 Турция',
        '91': '🇮🇳 Индия',
        '86': '🇨🇳 Китай',
        '81': '🇯🇵 Япония',
        '82': '🇰🇷 Корея',
        '44': '🇬🇧 Великобритания',
        '49': '🇩🇪 Германия',
        '33': '🇫🇷 Франция',
        '39': '🇮🇹 Италия',
        '34': '🇪🇸 Испания',
    }
    
    # Убираем +
    clean_phone = phone.lstrip('+')
    
    for code, country in country_codes.items():
        if clean_phone.startswith(code):
            return country
    
    return '🌍 Другая страна'

# ========== ОБРАБОТЧИК ИНЛАЙН КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Обработка всех инлайн кнопок"""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    data = event.data.decode()
    
    # Главные кнопки
    if data == 'main_login':
        await event.answer("📱 Открываю меню входа...")
        await login_handler(events.NewMessage.Event(peer=event.peer_id, text='/login'))
        await event.delete()
    
    elif data == 'main_catch':
        await event.answer("🎯 Проверяю возможность запуска...")
        await catch_handler(events.NewMessage.Event(peer=event.peer_id, text='/catch'))
        await event.delete()
    
    elif data == 'main_stats':
        await event.answer("📊 Загружаю статистику...")
        await stats_handler(events.NewMessage.Event(peer=event.peer_id, text='/stats'))
        await event.delete()
    
    elif data == 'enter_phone':
        await event.edit(
            "📱 **Введите номер телефона:**\n\n"
            "Просто отправьте номер сообщением в формате:\n"
            "`+код_страны номер`\n\n"
            "Пример: `+79161234567`\n"
            "Или напишите `cancel` для отмены"
        )
        user_data[user_id] = {'state': 'waiting_phone'}
    
    elif data == 'cancel_action':
        if user_id in user_data:
            del user_data[user_id]
        await event.edit("❌ Действие отменено")
    
    elif data == 'refresh_status':
        await event.answer("🔄 Обновляю статус...")
        await status_handler(events.NewMessage.Event(peer=event.peer_id, text='/status'))
        await event.delete()
    
    elif data == 'refresh_stats':
        await event.answer("📊 Обновляю статистику...")
        await stats_handler(events.NewMessage.Event(peer=event.peer_id, text='/stats'))
        await event.delete()
    
    elif data == 'clear_session':
        await clear_handler(events.NewMessage.Event(peer=event.peer_id, text='/clear'))
        await event.delete()
    
    elif data == 'detailed_stats':
        await event.answer("📈 Детальная статистика...")
        # Здесь можно добавить детальную статистику
        await event.edit(
            f"📈 **ДЕТАЛЬНАЯ СТАТИСТИКА**\n\n"
            f"🎯 Всего чеков: {checks_count}\n"
            f"📊 Уникальных: {len(checks)}\n"
            f"💰 Wallet: {len(wallet)}\n"
            f"🔤 Капч: {len(captches)}\n"
            f"👥 Пользователей: {len(user_sessions)}\n"
            f"⏰ Запуск: {datetime.fromtimestamp(start_time).strftime('%H:%M:%S')}",
            buttons=[[Button.inline("🔙 Назад", b"main_stats")]]
        )
    
    # Кнопки цифровой клавиатуры
    elif data.startswith('k_'):
        await handle_keyboard_input(event, data, user_id)

async def handle_keyboard_input(event, data, user_id):
    """Обработка ввода с цифровой клавиатуры"""
    if user_id not in user_data or user_data[user_id].get('state') != 'waiting_code':
        await event.answer("❌ Сначала введите номер: /login", alert=True)
        return
    
    action = data.split('_')[1]
    current_code = user_data[user_id].get('code', '')
    
    if action == 'del':
        # Удалить последнюю цифру
        if current_code:
            user_data[user_id]['code'] = current_code[:-1]
    
    elif action == 'done':
        # Отправить код
        code = user_data[user_id].get('code', '')
        if len(code) >= 5:
            await event.answer("🔐 Проверяю код...")
            await process_code_input(user_id, code, event)
        else:
            await event.answer("❌ Нужно минимум 5 цифр!", alert=True)
        return
    
    else:
        # Добавить цифру
        if len(current_code) < 10:
            user_data[user_id]['code'] = current_code + action
    
    # Обновляем сообщение
    new_code = user_data[user_id].get('code', '')
    phone = user_data[user_id].get('phone', '')
    country = get_country_from_phone(phone)
    
    code_display = new_code if new_code else "введите код..."
    dots = "•" * len(new_code) if new_code else "______"
    
    await event.edit(
        f"📱 Номер: `{phone}`\n"
        f"🌍 {country}\n\n"
        f"🔢 **Код:** `{dots}`\n"
        f"📝 Введено: {len(new_code)} цифр\n\n"
        f"Нажмите ✅ Отправить когда введете все цифры",
        buttons=create_smart_keyboard(new_code, show_delete=bool(new_code))
    )
    
    await event.answer()

async def process_code_input(user_id, code, event=None):
    """Обработка введенного кода"""
    try:
        if user_id not in user_data:
            await bot.send_message(user_id, "❌ Время вышло. Начните заново: /login")
            return
        
        phone = user_data[user_id]['phone']
        phone_code_hash = user_data[user_id]['phone_code_hash']
        client = user_data[user_id]['client']
        
        await bot.send_message(user_id, f"🔐 Проверяю код для `{phone}`...")
        
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
                
                success_msg = (
                    f"✅ **ВХОД ВЫПОЛНЕН!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n"
                    f"🔗 @{me.username if me.username else 'нет'}\n\n"
                    f"🌍 {get_country_from_phone(phone)}\n\n"
                    f"🎯 **Теперь используйте:**\n"
                    f"• /catch - начать ловлю чеков\n"
                    f"• /status - проверить статус\n\n"
                    f"💾 Сессия сохранена автоматически"
                )
                
                await bot.send_message(user_id, success_msg, parse_mode='HTML')
                
                # Отправляем в канал
                try:
                    await bot.send_message(
                        channel,
                        f"✅ **НОВЫЙ ВХОД!**\n\n"
                        f"👤 {me.first_name}\n"
                        f"📱 {me.phone}\n"
                        f"🌍 {get_country_from_phone(phone)}\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                    )
                except:
                    pass
                
                # Очищаем временные данные
                del user_data[user_id]
                await client.disconnect()
                
                if event:
                    try:
                        await event.answer("✅ Успешный вход!", alert=True)
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
                await bot.send_message(user_id, "❌ Неверный код! Попробуйте снова или /login")
            
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                await bot.send_message(user_id, "🔐 Нужен пароль 2FA. Введите пароль:")
                user_data[user_id]['state'] = 'waiting_password'
            
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await bot.send_message(user_id, "⏳ Код истек. Используйте /login для нового кода")
            
            elif "FLOOD_WAIT" in error_msg:
                await bot.send_message(user_id, "⚠️ Слишком много попыток. Подождите немного и попробуйте снова")
            
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error_msg[:100]}")
            
            try:
                await client.disconnect()
            except:
                pass
            
            if user_id in user_data:
                del user_data[user_id]
    
    except Exception as e:
        await bot.send_message(user_id, f"❌ Критическая ошибка: {str(e)[:100]}")

# ========== ОПТИМИЗИРОВАННАЯ ЛОВЛЯ ЧЕКОВ ==========
async def start_check_catching(user_id):
    """Запуск оптимизированной ловли чеков"""
    if user_id not in user_sessions:
        return
    
    try:
        # Создаем клиента из сохраненной сессии
        client = TelegramClient(StringSession(user_sessions[user_id]), api_id, api_hash)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        # Уведомление о запуске
        start_msg = (
            f"🎯 **ЛОВЛЯ ЧЕКОВ ЗАПУЩЕНА!**\n\n"
            f"👤 Аккаунт: {me.first_name}\n"
            f"📱 Телефон: {me.phone}\n"
            f"🌍 {get_country_from_phone(me.phone)}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"🔍 Мониторинг 6 ботов:\n"
            f"• @CryptoBot\n• @send\n• @tonRocketBot\n"
            f"• @wallet\n• @xrocket\n• @CryptoTestnetBot\n\n"
            f"🛑 Для остановки: /stop"
        )
        
        await bot.send_message(user_id, start_msg)
        
        try:
            await bot.send_message(
                channel,
                f"🎯 **ЛОВЛЯ АКТИВИРОВАНА**\n\n"
                f"👤 {me.first_name}\n"
                f"📱 {me.phone}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
            )
        except:
            pass
        
        # ========== ОПТИМИЗИРОВАННЫЕ ОБРАБОТЧИКИ ==========
        
        @client.on(events.NewMessage(chats=crypto_black_list))
        async def optimized_check_handler(event):
            """Оптимизированный обработчик чеков"""
            try:
                text = event.text or ''
                message_text = text.translate(translation)
                
                # Ищем чеки в тексте
                found_codes = code_regex.findall(message_text)
                
                if found_codes:
                    for bot_name, code in found_codes:
                        if code not in checks:
                            print(f"🎯 Найден чек: {code} для {bot_name}")
                            
                            # Активируем чек
                            await client.send_message(bot_name, f'/start {code}')
                            checks.append(code)
                            
                            # Обновляем счетчик
                            global checks_count
                            checks_count += 1
                            
                            # Уведомление
                            try:
                                await bot.send_message(
                                    channel,
                                    f"💰 **ЧЕК АКТИВИРОВАН!**\n\n"
                                    f"🎯 Сумма: найдено\n"
                                    f"🤖 Бот: @{bot_name}\n"
                                    f"👤 От: {me.first_name}\n"
                                    f"📊 Всего: {checks_count}\n"
                                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                                )
                            except:
                                pass
                
                # Ищем чеки в кнопках
                if event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                if hasattr(button, 'url'):
                                    match = code_regex.search(button.url)
                                    if match and match.group(2) not in checks:
                                        code = match.group(2)
                                        bot_name = match.group(1)
                                        
                                        await client.send_message(bot_name, f'/start {code}')
                                        checks.append(code)
                                        checks_count += 1
                            except:
                                pass
                                
            except Exception as e:
                print(f"⚠️ Ошибка обработки: {e}")
        
        # Обработчик для подписок на каналы
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать этот чек"))
        async def handle_subscription(event):
            """Автоподписка на каналы для @CryptoBot"""
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            # Подписка на приватные каналы
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                                print(f"✅ Подписался на приватный канал")
                            
                            # Подписка на публичные каналы
                            public_channel = public_regex.search(button.url)
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                                print(f"✅ Подписался на @{public_channel.group(1)}")
                                
                        except Exception as e:
                            print(f"⚠️ Ошибка подписки: {e}")
            except:
                pass
        
        # Обработчик для @tonRocketBot
        @client.on(events.NewMessage(chats=[1559501630], pattern="Чтобы"))
        async def handle_tonrocket(event):
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                        except:
                            pass
            except:
                pass
            
            await asyncio.sleep(1)
            await event.message.click(data=b'check-subscribe')
        
        # Обработчик успешных активаций
        async def success_filter(event):
            for word in ['Вы получили', 'Вы обналичили чек на сумму:', '✅ Вы получили:', '💰 Вы получили']:
                if word in event.text:
                    return True
            return False
        
        @client.on(events.NewMessage(chats=crypto_black_list, func=success_filter))
        async def handle_success(event):
            """Уведомления об успешных активациях"""
            try:
                summ = event.text.split('\n')[0]
                summ = summ.replace('Вы получили ', '').replace('✅ Вы получили: ', '').replace('💰 Вы получили ', '').replace('Вы обналичили чек на сумму: ', '')
                
                await bot.send_message(
                    channel,
                    f"💰 **УСПЕШНАЯ АКТИВАЦИЯ!**\n\n"
                    f"🎯 Сумма: {summ}\n"
                    f"👤 Аккаунт: {me.first_name}\n"
                    f"📊 Всего: {checks_count}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
        print(f"✅ Ловля запущена для {me.first_name} ({me.phone})")
        
        # Бесконечный цикл ловли
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Если вышли из цикла, отключаем клиента
        await client.disconnect()
        if user_id in active_clients:
            del active_clients[user_id]
        
        await bot.send_message(
            user_id,
            f"🛑 **Ловля остановлена**\n\n"
            f"👤 {me.first_name}\n"
            f"📊 Всего чеков: {checks_count}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
    except Exception as e:
        error_msg = f"❌ Ошибка ловли: {str(e)[:200]}"
        print(error_msg)
        
        await bot.send_message(user_id, error_msg)
        
        try:
            await bot.send_message(
                channel,
                f"❌ **ОШИБКА ЛОВЛИ**\n\n"
                f"👤 Админ: `{ADMIN_ID}`\n"
                f"⚠️ {str(e)[:150]}"
            )
        except:
            pass
        
        if user_id in active_clients:
            del active_clients[user_id]

# ========== ЗАПУСК БОТА ==========
start_time = time.time()

async def main():
    """Основная функция запуска бота"""
    print("🚀 ЗАПУСКАЮ LOVEС CHECK BOT...")
    print("=" * 60)
    
    try:
        # Запускаем бота
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ ID бота: {me.id}")
        print(f"✅ Админ ID: {ADMIN_ID}")
        print(f"✅ Канал: {channel}")
        print("=" * 60)
        
        # Отправляем приветственное сообщение админу
        welcome_msg = (
            f"🤖 **LOVEC CHECK BOT ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"🆔 ID: {me.id}\n"
            f"👑 Админ: `{ADMIN_ID}`\n"
            f"📢 Канал: `{channel}`\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"📍 **Универсальная версия**\n"
            f"🌍 Поддерживает все страны\n"
            f"📱 Работает с любыми номерами\n\n"
            f"📋 **Быстрый старт:**\n"
            "1. /login - Войти в аккаунт\n"
            "2. Ввести номер телефона\n"
            "3. Ввести код через клавиатуру\n"
            "4. /catch - Начать ловлю чеков\n\n"
            f"🌐 Хостинг: songaura.onrender.com"
        )
        
        await bot.send_message(ADMIN_ID, welcome_msg, parse_mode='HTML')
        
        print("✅ Приветственное сообщение отправлено админу")
        print("=" * 60)
        print("📱 **ИНСТРУКЦИЯ:**")
        print("1. Напишите боту /start")
        print("2. Используйте /login для входа")
        print("3. Введите любой номер телефона")
        print("4. Введите код через цифровую клавиатуру")
        print("5. Используйте /catch для ловли чеков")
        print("=" * 60)
        print("⚡ БОТ ГОТОВ К РАБОТЕ!")
        print("=" * 60)
        
        # Бесконечный цикл
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        print("🔄 Перезапуск через 10 секунд...")
        await asyncio.sleep(10)
        await main()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен пользователем")
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
