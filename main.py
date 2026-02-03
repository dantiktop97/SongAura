import os
import asyncio
import time
import re
import json
import random
import logging
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
import requests
from io import BytesIO

# ========== НАСТРОЙКА ЛОГГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ==========
# Получаем значения из переменных окружения
API_ID = int(os.getenv('API_ID', '2040'))
API_HASH = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')
BOT_TOKEN = os.getenv('LOVEC', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Настройки из .env
CHANNEL_ID = int(os.getenv('CHANNEL', '-1004902536707'))
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')
AUTO_WITHDRAW = os.getenv('AUTO_WITHDRAW', 'False').lower() == 'true'
WITHDRAW_TAG = os.getenv('WITHDRAW_TAG', '')
MAX_CHECKS = int(os.getenv('MAX_CHECKS', '30'))
MAX_JOINS = int(os.getenv('MAX_JOINS', '20'))
DELAY_MS = int(os.getenv('DELAY_MS', '1000'))

# Проверка обязательных настроек
if not all([API_ID, API_HASH, BOT_TOKEN, ADMIN_ID]):
    logger.error("❌ Отсутствуют обязательные настройки в .env файле!")
    print("=" * 60)
    print("❌ ОШИБКА: Проверьте настройки в .env файле!")
    print("Нужно установить: API_ID, API_HASH, LOVEC (токен бота), ADMIN_ID")
    print("=" * 60)
    exit(1)

print("=" * 60)
print("🤖 LOVEС CHECK BOT v4.0")
print("=" * 60)
print(f"✅ API_ID: {API_ID}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ CHANNEL_ID: {CHANNEL_ID}")
print(f"✅ ANTI_CAPTCHA: {ANTI_CAPTCHA}")
print(f"✅ DELAY_MS: {DELAY_MS}ms")
print("=" * 60)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}      # {user_id: session_string}
active_clients = {}     # {user_id: TelegramClient}
user_data = {}          # Временные данные пользователей
checks_found = []       # Найденные чеки
checks_activated = 0    # Счетчик активированных чеков
start_time = time.time()

# Регулярки для поиска
CODE_PATTERNS = [
    r"t\.me/CryptoBot\?start=CQ[A-Za-z0-9]{10}",
    r"t\.me/send\?start=C-[A-Za-z0-9]{10}",
    r"t\.me/tonRocketBot\?start=t_[A-Za-z0-9]{15}",
    r"t\.me/CryptoTestnetBot\?start=c_[a-z0-9]{24}",
    r"t\.me/wallet\?start=mci_[A-Za-z0-9]{15}",
    r"t\.me/xrocket\?start=CQ[A-Za-z0-9]{10}",
    r"t\.me/xJetSwapBot\?start=CQ[A-Za-z0-9]{10}"
]

CODE_REGEX = re.compile('|'.join(CODE_PATTERNS), re.IGNORECASE)
URL_REGEX = re.compile(r"https://t\.me/\+(\w{12,})")
PUBLIC_REGEX = re.compile(r"https://t\.me/(\w{4,})")

# Боты для мониторинга
MONITOR_CHATS = [
    1622808649,    # CryptoBot
    1559501630,    # @send bot
    1985737506,    # @tonRocketBot
    5014831088,    # @CryptoTestnetBot
    6014729293,    # @wallet
    5794061503     # @xrocket
]

# Спецсимволы для очистки
SPECIAL_CHARS = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
TRANSLATION = str.maketrans('', '', SPECIAL_CHARS)

# ========== СИСТЕМА КОНФИГУРАЦИИ ==========
class Config:
    def __init__(self):
        self.settings = {
            'auto_start': True,
            'notifications': True,
            'auto_subscribe': True,
            'solve_captcha': ANTI_CAPTCHA,
            'safety_enabled': True,
            'delay_ms': DELAY_MS,
            'max_checks': MAX_CHECKS,
            'max_joins': MAX_JOINS
        }
    
    def get(self, key, default=None):
        return self.settings.get(key, default)
    
    def set(self, key, value):
        self.settings[key] = value
        return True
    
    def toggle(self, key):
        if key in self.settings:
            self.settings[key] = not self.settings[key]
            return self.settings[key]
        return False

config = Config()

# ========== ОСНОВНОЙ БОТ ==========
bot = TelegramClient('lovec_bot', API_ID, API_HASH)

# ========== СИСТЕМА БЕЗОПАСНОСТИ ==========
class SafetySystem:
    def __init__(self):
        self.action_history = []
    
    async def safe_action(self, action_type="check"):
        if not config.get('safety_enabled', True):
            return True
        
        now = time.time()
        self.action_history = [t for t in self.action_history if now - t < 60]
        
        # Проверяем лимиты
        if action_type == "check" and len(self.action_history) >= config.get('max_checks', 30):
            delay = random.uniform(30, 60)
            logger.warning(f"⚠️ Лимит чеков. Жду {delay:.1f} сек")
            await asyncio.sleep(delay)
            self.action_history.clear()
        
        delay_ms = config.get('delay_ms', 1000)
        delay = random.uniform(delay_ms * 0.8, delay_ms * 1.2) / 1000
        await asyncio.sleep(delay)
        
        self.action_history.append(now)
        return True

safety = SafetySystem()

# ========== МЕНЮ И КНОПКИ ==========
def create_main_menu():
    return [
        [Button.inline("🔐 Войти в аккаунт", b"login")],
        [Button.inline("🎯 Статус ловли", b"status")],
        [Button.inline("⚙️ Настройки", b"settings"), Button.inline("📊 Статистика", b"stats")],
        [Button.inline("🔄 Обновить", b"refresh")]
    ]

def create_auth_menu():
    return [
        [Button.request_phone("📱 Поделиться номером")],
        [Button.inline("✏️ Ввести вручную", b"manual")],
        [Button.inline("🔙 Назад", b"back")]
    ]

def create_settings_menu():
    return [
        [
            Button.inline(f"{'✅' if config.get('auto_start') else '❌'} Автозапуск", b"toggle_auto"),
            Button.inline(f"{'✅' if config.get('notifications') else '❌'} Уведомления", b"toggle_notify")
        ],
        [
            Button.inline(f"{'✅' if config.get('auto_subscribe') else '❌'} Подписки", b"toggle_subs"),
            Button.inline(f"{'✅' if config.get('solve_captcha') else '❌'} Капчи", b"toggle_captcha")
        ],
        [
            Button.inline(f"{'✅' if config.get('safety_enabled') else '❌'} Безопасность", b"toggle_safety"),
            Button.inline("⚡ Скорость", b"speed")
        ],
        [Button.inline("💾 Сохранить", b"save"), Button.inline("🗑️ Сбросить", b"reset")],
        [Button.inline("🔙 Назад", b"back")]
    ]

def create_numpad():
    return [
        [Button.inline("1", b"1"), Button.inline("2", b"2"), Button.inline("3", b"3")],
        [Button.inline("4", b"4"), Button.inline("5", b"5"), Button.inline("6", b"6")],
        [Button.inline("7", b"7"), Button.inline("8", b"8"), Button.inline("9", b"9")],
        [Button.inline("0", b"0"), Button.inline("⌫", b"del"), Button.inline("✅", b"submit")]
    ]

def create_speed_menu():
    return [
        [Button.inline("🐢 Медленно (2000мс)", b"speed_2000")],
        [Button.inline("⚡ Средне (1000мс)", b"speed_1000")],
        [Button.inline("🚀 Быстро (500мс)", b"speed_500")],
        [Button.inline("🔙 Назад", b"settings")]
    ]

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Обработчик команды /start"""
    if event.sender_id != ADMIN_ID:
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **LOVEC CHECK BOT v4.0**\n\n"
        f"👑 Админ: `{ADMIN_ID}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
        f"💰 Чеков: {checks_activated}\n"
        f"🔗 Сессий: {len(user_sessions)}\n"
        f"🎣 Активных: {len(active_clients)}\n\n"
        f"⚡ **Версия:** 4.0 (Упрощенная)\n"
        f"🌐 **Хостинг:** songaura.onrender.com",
        buttons=create_main_menu()
    )

@bot.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    """Обработчик команды /help"""
    if event.sender_id != ADMIN_ID:
        return
    
    help_text = """
🤖 **LOVEC CHECK BOT - СПРАВКА**

**Основные команды:**
/start - Главное меню
/status - Статус системы
/stop - Остановить бота

**Функции:**
• Автоловля чеков из 6+ ботов
• Автоподписка на каналы
• Решение капч (если включено)
• Безопасность с лимитами
• Сохранение сессий

**Настройки:**
• Задержка: {delay}мс
• Лимит чеков: {checks}/мин
• Лимит подписок: {joins}/час
    """.format(
        delay=config.get('delay_ms'),
        checks=config.get('max_checks'),
        joins=config.get('max_joins')
    )
    
    await event.reply(help_text)

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Обработчик команды /status"""
    if event.sender_id != ADMIN_ID:
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    status_text = f"""
📊 **СТАТУС СИСТЕМЫ**

⏳ Работает: {hours}ч {minutes}м
💰 Чеков: {checks_activated}
📈 Найдено: {len(checks_found)}
🔗 Сессий: {len(user_sessions)}
🎣 Активных: {len(active_clients)}

⚙️ **Настройки:**
• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}
• Задержка: {config.get('delay_ms')}мс
• Автозапуск: {'✅' if config.get('auto_start') else '❌'}
    """
    
    await event.reply(status_text)

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Обработчик всех кнопок"""
    user_id = event.sender_id
    data = event.data.decode('utf-8') if event.data else ""
    
    if user_id != ADMIN_ID:
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    logger.info(f"Кнопка: {data} от пользователя {user_id}")
    
    try:
        # Главное меню
        if data == "login":
            await event.edit(
                "🔐 **ВХОД В АККАУНТ**\n\n"
                "Выберите способ входа:\n\n"
                "1. 📱 Поделиться номером (рекомендуется)\n"
                "2. ✏️ Ввести номер вручную\n\n"
                "✅ После входа бот начнет работу автоматически!",
                buttons=create_auth_menu()
            )
        
        elif data == "manual":
            await event.edit(
                "✏️ **ВВОД НОМЕРА**\n\n"
                "Отправьте номер телефона в формате:\n\n"
                "📌 **Пример:**\n"
                "+380681234567\n"
                "+79123456789\n\n"
                "✏️ Просто отправьте номер сообщением",
                buttons=[[Button.inline("🔙 Назад", b"login")]]
            )
            user_data[user_id] = {'state': 'wait_phone'}
        
        elif data == "status":
            if user_id in active_clients:
                status = "✅ АКТИВНА"
                action_btn = [Button.inline("🛑 Остановить", b"stop_catch")]
            elif user_id in user_sessions:
                status = "⏸️ ГОТОВА"
                action_btn = [Button.inline("🚀 Запустить", b"start_catch")]
            else:
                status = "❌ НЕТ СЕССИИ"
                action_btn = [Button.inline("🔐 Войти", b"login")]
            
            await event.edit(
                f"🎯 **СТАТУС ЛОВЛИ**\n\n"
                f"🔐 Сессия: {'✅ ЕСТЬ' if user_id in user_sessions else '❌ НЕТ'}\n"
                f"🎣 Ловля: {status}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"🛡️ Безопасность: {'✅ ВКЛ' if config.get('safety_enabled') else '❌ ВЫКЛ'}\n\n"
                f"⚙️ Автозапуск: {'✅ ВКЛ' if config.get('auto_start') else '❌ ВЫКЛ'}",
                buttons=[action_btn, [Button.inline("🔙 Назад", b"back")]]
            )
        
        elif data == "start_catch":
            if user_id not in user_sessions:
                await event.answer("❌ Сначала войдите в аккаунт!", alert=True)
                return
            
            if user_id in active_clients:
                await event.answer("✅ Уже запущено!", alert=True)
                return
            
            await event.edit("🎯 Запускаю ловлю...")
            asyncio.create_task(start_catching(user_id))
            await event.answer("✅ Ловля запущена!", alert=True)
            await asyncio.sleep(1)
            await event.delete()
        
        elif data == "stop_catch":
            if user_id in active_clients:
                try:
                    await active_clients[user_id].disconnect()
                    del active_clients[user_id]
                    await event.edit("🛑 Ловля остановлена!")
                    await event.answer("✅ Остановлено!", alert=True)
                except:
                    await event.answer("⚠️ Ошибка остановки", alert=True)
            else:
                await event.answer("ℹ️ Ловля не запущена", alert=True)
        
        elif data == "settings":
            await event.edit(
                "⚙️ **НАСТРОЙКИ**\n\n"
                f"✅ Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                f"📢 Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                f"📈 Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                f"🛡️ Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                f"⚡ Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n\n"
                "Изменить настройки:",
                buttons=create_settings_menu()
            )
        
        elif data.startswith("toggle_"):
            setting = data.replace("toggle_", "")
            if setting == "auto":
                new_val = config.toggle('auto_start')
                msg = f"Автозапуск: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "notify":
                new_val = config.toggle('notifications')
                msg = f"Уведомления: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "subs":
                new_val = config.toggle('auto_subscribe')
                msg = f"Подписки: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "captcha":
                new_val = config.toggle('solve_captcha')
                msg = f"Капчи: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "safety":
                new_val = config.toggle('safety_enabled')
                msg = f"Безопасность: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            else:
                msg = "❌ Неизвестная настройка"
            
            await event.answer(msg, alert=True)
            await callback_handler(event)  # Обновляем меню
        
        elif data == "speed":
            await event.edit(
                f"⚡ **СКОРОСТЬ**\n\n"
                f"Текущая задержка: {config.get('delay_ms')}мс\n"
                f"Чеков/минуту: {config.get('max_checks')}\n"
                f"Подписок/час: {config.get('max_joins')}\n\n"
                "Выберите скорость:",
                buttons=create_speed_menu()
            )
        
        elif data.startswith("speed_"):
            try:
                delay = int(data.split("_")[1])
                config.set('delay_ms', delay)
                await event.answer(f"✅ Задержка: {delay}мс", alert=True)
                await event.edit(
                    "⚙️ **НАСТРОЙКИ**\n\n"
                    f"✅ Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"📢 Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"📈 Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"🛡️ Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"⚡ Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n\n"
                    "Изменить настройки:",
                    buttons=create_settings_menu()
                )
            except:
                await event.answer("❌ Ошибка установки скорости", alert=True)
        
        elif data == "save":
            try:
                with open('config.json', 'w') as f:
                    json.dump(config.settings, f)
                await event.answer("✅ Настройки сохранены!", alert=True)
            except Exception as e:
                await event.answer(f"❌ Ошибка: {str(e)[:50]}", alert=True)
        
        elif data == "reset":
            config.settings = {
                'auto_start': True,
                'notifications': True,
                'auto_subscribe': True,
                'solve_captcha': ANTI_CAPTCHA,
                'safety_enabled': True,
                'delay_ms': DELAY_MS,
                'max_checks': MAX_CHECKS,
                'max_joins': MAX_JOINS
            }
            await event.answer("✅ Настройки сброшены!", alert=True)
            await callback_handler(event)
        
        elif data == "stats":
            uptime = time.time() - start_time
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            
            await event.edit(
                f"📊 **СТАТИСТИКА**\n\n"
                f"⏳ Работает: {hours}ч {minutes}м\n"
                f"💰 Чеков: {checks_activated}\n"
                f"📈 Найдено: {len(checks_found)}\n"
                f"🔗 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных: {len(active_clients)}\n\n"
                f"⚙️ **Настройки:**\n"
                f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
                f"• Задержка: {config.get('delay_ms')}мс",
                buttons=[[Button.inline("🔄 Обновить", b"stats"), Button.inline("🔙 Назад", b"back")]]
            )
        
        elif data == "refresh":
            await event.edit(
                f"🤖 **LOVEC CHECK BOT v4.0**\n\n"
                f"👑 Админ: `{ADMIN_ID}`\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"🔗 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных: {len(active_clients)}",
                buttons=create_main_menu()
            )
            await event.answer("✅ Обновлено!")
        
        elif data == "back":
            await event.edit(
                f"🤖 **LOVEC CHECK BOT v4.0**\n\n"
                f"👑 Админ: `{ADMIN_ID}`\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"🔗 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных: {len(active_clients)}",
                buttons=create_main_menu()
            )
        
        # Цифровая клавиатура для кода
        elif data in "0123456789":
            if user_id in user_data and user_data[user_id].get('state') == 'wait_code':
                code = user_data[user_id].get('code', '')
                if len(code) < 10:
                    user_data[user_id]['code'] = code + data
                    
                    new_code = user_data[user_id]['code']
                    dots = "•" * len(new_code)
                    
                    await event.edit(
                        f"📱 Номер: `{user_data[user_id].get('phone', '')}`\n\n"
                        f"🔢 Код из Telegram: `{dots}`\n"
                        f"📝 Введено: {len(new_code)} цифр\n\n"
                        "Нажмите ✅ когда код будет полный",
                        buttons=create_numpad()
                    )
        
        elif data == "del":
            if user_id in user_data and user_data[user_id].get('state') == 'wait_code':
                code = user_data[user_id].get('code', '')
                if code:
                    user_data[user_id]['code'] = code[:-1]
                    
                    new_code = user_data[user_id]['code']
                    dots = "•" * len(new_code) if new_code else "____"
                    
                    await event.edit(
                        f"📱 Номер: `{user_data[user_id].get('phone', '')}`\n\n"
                        f"🔢 Код из Telegram: `{dots}`\n"
                        f"📝 Введено: {len(new_code)} цифр\n\n"
                        "Нажмите ✅ когда код будет полный",
                        buttons=create_numpad()
                    )
        
        elif data == "submit":
            if user_id in user_data and user_data[user_id].get('state') == 'wait_code':
                code = user_data[user_id].get('code', '')
                if len(code) >= 5:
                    await event.answer("🔐 Проверяю код...")
                    await process_telegram_code(user_id, code, event)
                else:
                    await event.answer("❌ Минимум 5 цифр!", alert=True)
        
        await event.answer()
        
    except Exception as e:
        logger.error(f"Ошибка обработки кнопки: {e}")
        await event.answer("⚠️ Ошибка обработки", alert=True)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
@bot.on(events.NewMessage)
async def message_handler(event):
    """Обработчик текстовых сообщений"""
    if event.sender_id != ADMIN_ID:
        return
    
    text = event.text.strip()
    
    if text.startswith('/'):
        return
    
    # Обработка ввода номера
    if event.sender_id in user_data and user_data[event.sender_id].get('state') == 'wait_phone':
        if text.startswith('+') and len(text) > 5:
            phone = text.replace(' ', '')
            await start_telegram_auth(event.sender_id, phone, event)
        else:
            await event.reply("❌ Неверный формат номера. Пример: +380681234567")
    
    # Обработка пароля 2FA
    elif event.sender_id in user_data and user_data[event.sender_id].get('state') == 'wait_password':
        await process_2fa_password(event.sender_id, text, event)

@bot.on(events.NewMessage(func=lambda e: e.contact))
async def contact_handler(event):
    """Обработка контакта"""
    if event.sender_id != ADMIN_ID:
        return
    
    contact = event.contact
    if contact.user_id == event.sender_id:
        phone = contact.phone_number
        if not phone.startswith('+'):
            phone = '+' + phone
        
        await start_telegram_auth(event.sender_id, phone, event)
    else:
        await event.reply("❌ Это не ваш контакт!")

# ========== АВТОРИЗАЦИЯ ==========
async def start_telegram_auth(user_id, phone, event=None):
    """Начало авторизации"""
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        sent_code = await client.send_code_request(phone)
        
        user_data[user_id] = {
            'state': 'wait_code',
            'phone': phone,
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash,
            'code': ''
        }
        
        message = (
            f"✅ **Код отправлен!**\n\n"
            f"📱 Номер: `{phone}`\n"
            f"⏳ Код действует: {sent_code.timeout} сек\n\n"
            f"🔢 **Введите код из Telegram:**"
        )
        
        if event:
            await event.reply(message, buttons=create_numpad())
        else:
            await bot.send_message(user_id, message, buttons=create_numpad())
        
    except Exception as e:
        error = str(e)
        if "A wait of" in error:
            msg = "⏳ Слишком много запросов. Попробуйте позже."
        elif "PHONE_NUMBER_INVALID" in error:
            msg = "❌ Неверный номер телефона!"
        else:
            msg = f"❌ Ошибка: {error[:100]}"
        
        await bot.send_message(user_id, msg)
        
        if user_id in user_data:
            try:
                await user_data[user_id]['client'].disconnect()
            except:
                pass
            del user_data[user_id]

async def process_telegram_code(user_id, code, event=None):
    """Обработка кода"""
    try:
        phone = user_data[user_id]['phone']
        phone_code_hash = user_data[user_id]['phone_code_hash']
        client = user_data[user_id]['client']
        
        if event:
            try:
                await event.delete()
            except:
                pass
        
        await bot.send_message(user_id, "🔐 Проверяю код...")
        
        try:
            await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            if await client.is_user_authorized():
                session_string = client.session.save()
                user_sessions[user_id] = session_string
                
                me = await client.get_me()
                
                success_msg = (
                    f"✅ **ВХОД УСПЕШЕН!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n\n"
                )
                
                await bot.send_message(user_id, success_msg)
                
                if config.get('auto_start'):
                    await bot.send_message(user_id, "🎯 **Запускаю ловлю автоматически...**")
                    asyncio.create_task(start_catching(user_id))
                else:
                    await bot.send_message(
                        user_id,
                        "🎯 **Готов к работе!**\nНажмите 'Запустить' чтобы начать.",
                        buttons=[
                            [Button.inline("🚀 Запустить ловлю", b"start_catch")],
                            [Button.inline("🔙 В меню", b"back")]
                        ]
                    )
                
                await client.disconnect()
                del user_data[user_id]
                
            else:
                await bot.send_message(user_id, "❌ Не удалось авторизоваться")
                await client.disconnect()
                
        except Exception as e:
            error = str(e)
            
            if "SESSION_PASSWORD_NEEDED" in error:
                await bot.send_message(user_id, "🔐 **Требуется пароль 2FA**\n\nВведите пароль:")
                user_data[user_id]['state'] = 'wait_password'
                
            elif "PHONE_CODE_INVALID" in error:
                await bot.send_message(user_id, "❌ Неверный код!")
                user_data[user_id]['code'] = ''
                await bot.send_message(
                    user_id,
                    f"📱 Номер: `{phone}`\n\n🔢 **Введите код снова:**",
                    buttons=create_numpad()
                )
                
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error[:100]}")
                await client.disconnect()
                del user_data[user_id]
                
    except Exception as e:
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")

async def process_2fa_password(user_id, password, event):
    """Обработка пароля 2FA"""
    try:
        client = user_data[user_id]['client']
        
        await client.sign_in(password=password)
        
        session_string = client.session.save()
        user_sessions[user_id] = session_string
        
        me = await client.get_me()
        
        success_msg = f"✅ **ВХОД С 2FA УСПЕШЕН!**\n\n👤 {me.first_name}\n📱 {me.phone}\n\n"
        
        if config.get('auto_start'):
            success_msg += "🎯 **Запускаю ловлю автоматически...**"
            await event.reply(success_msg)
            asyncio.create_task(start_catching(user_id))
        else:
            success_msg += "🎯 **Готов к работе!**"
            await event.reply(
                success_msg,
                buttons=[
                    [Button.inline("🚀 Запустить ловлю", b"start_catch")],
                    [Button.inline("🔙 В меню", b"back")]
                ]
            )
        
        await client.disconnect()
        del user_data[user_id]
        
    except Exception as e:
        await event.reply(f"❌ Ошибка пароля: {e}")
        if user_id in user_data:
            try:
                await user_data[user_id]['client'].disconnect()
            except:
                pass
            del user_data[user_id]

# ========== ЛОВЛЯ ЧЕКОВ ==========
async def start_catching(user_id):
    """Запуск ловли"""
    if user_id not in user_sessions:
        logger.error(f"Нет сессии для {user_id}")
        return
    
    try:
        client = TelegramClient(StringSession(user_sessions[user_id]), API_ID, API_HASH)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        logger.info(f"Ловля запущена для {me.first_name}")
        
        # Уведомление о запуске
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"🎯 **ЛОВЛЯ ЗАПУЩЕНА!**\n\n"
                    f"👤 {me.first_name}\n"
                    f"📱 {me.phone}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
        # Обработчик сообщений
        @client.on(events.NewMessage(chats=MONITOR_CHATS))
        async def check_handler(event):
            await safety.safe_action("check")
            
            try:
                text = event.text or ''
                cleaned = text.translate(TRANSLATION)
                
                # Поиск чеков
                for pattern in CODE_PATTERNS:
                    matches = re.findall(pattern, cleaned, re.IGNORECASE)
                    for match in matches:
                        # Извлекаем код
                        if '?start=' in match:
                            code = match.split('?start=')[1]
                            if code not in checks_found:
                                logger.info(f"Найден чек: {code[:10]}...")
                                checks_found.append(code)
                                
                                # Получаем имя бота
                                bot_name = match.split('t.me/')[1].split('?')[0]
                                
                                # Активируем чек
                                await safety.safe_action("check")
                                await client.send_message(bot_name, f'/start {code}')
                                
                                global checks_activated
                                checks_activated += 1
                                
                                # Уведомление
                                if config.get('notifications'):
                                    try:
                                        await bot.send_message(
                                            CHANNEL_ID,
                                            f"💰 **ЧЕК АКТИВИРОВАН!**\n\n"
                                            f"🎯 Код: {code[:10]}...\n"
                                            f"🤖 Бот: @{bot_name}\n"
                                            f"👤 От: {me.first_name}\n"
                                            f"📊 Всего: {checks_activated}"
                                        )
                                    except:
                                        pass
                
                # Автоподписка
                if config.get('auto_subscribe') and event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                url = button.url
                                if not url:
                                    continue
                                
                                await safety.safe_action("join")
                                
                                # Приватные каналы
                                private = URL_REGEX.search(url)
                                if private:
                                    await client(ImportChatInviteRequest(private.group(1)))
                                
                                # Публичные каналы
                                public = PUBLIC_REGEX.search(url)
                                if public:
                                    await client(JoinChannelRequest(public.group(1)))
                                
                            except Exception as e:
                                if "FLOOD_WAIT" not in str(e):
                                    logger.warning(f"Ошибка подписки: {e}")
                                    
            except Exception as e:
                logger.error(f"Ошибка обработки: {e}")
        
        # Ожидание
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"🛑 **ЛОВЛЯ ОСТАНОВЛЕНА**\n\n"
                    f"👤 {me.first_name}\n"
                    f"💰 Чеков: {checks_activated}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
    except Exception as e:
        logger.error(f"Ошибка ловли: {e}")
        if user_id in active_clients:
            del active_clients[user_id]

# ========== ЗАПУСК ==========
async def main():
    """Основная функция"""
    print("🚀 Запуск бота...")
    
    try:
        await bot.start(bot_token=BOT_TOKEN)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        print("=" * 60)
        print("✅ Бот готов к работе!")
        print("🎯 Отправьте /start для начала")
        print("=" * 60)
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEC CHECK BOT v4.0 ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: {ADMIN_ID}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"Отправьте /start для начала работы."
        )
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        print("\n🛑 Завершение работы...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Остановлено пользователем")
    except Exception as e:
        print(f"\n❌ Критическая ошибка: {e}")
