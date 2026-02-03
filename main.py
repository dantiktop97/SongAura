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
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ==========
# Основные
API_ID = int(os.getenv('API_ID', '2040'))
API_HASH = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')
BOT_TOKEN = os.getenv('LOVEC', '')  # Бот токен
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Настройки ловли
CHANNEL_ID = int(os.getenv('CHANNEL', '-1004902536707'))  # Канал для уведомлений
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')
AUTO_WITHDRAW = os.getenv('AUTO_WITHDRAW', 'False').lower() == 'true'
WITHDRAW_TAG = os.getenv('WITHDRAW_TAG', '')

# Настройки безопасности
MAX_CHECKS_PER_MINUTE = int(os.getenv('MAX_CHECKS', '30'))
MAX_JOINS_PER_HOUR = int(os.getenv('MAX_JOINS', '20'))
DELAY_BETWEEN_ACTIONS = int(os.getenv('DELAY_MS', '1000'))

print("=" * 60)
print("🤖 LOVEС CHECK BOT v3.0 - ПОЛНАЯ ВЕРСИЯ")
print("=" * 60)

if not API_ID or not API_HASH or not BOT_TOKEN or not ADMIN_ID:
    print("❌ ОШИБКА: Не все обязательные переменные установлены!")
    print("💡 Нужны: API_ID, API_HASH, LOVEC (бот токен), ADMIN_ID")
    exit(1)

print(f"✅ API_ID: {API_ID}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ ANTI_CAPTCHA: {ANTI_CAPTCHA}")
print(f"✅ AUTO_WITHDRAW: {AUTO_WITHDRAW}")
print(f"✅ CHANNEL_ID: {CHANNEL_ID}")
print("=" * 60)

# ========== СИСТЕМА КОНФИГУРАЦИИ ==========
class Config:
    """Класс для управления настройками"""
    
    def __init__(self):
        self.settings = {
            'active': False,
            'auto_start': True,
            'notifications': True,
            'auto_subscribe': True,
            'solve_captcha': ANTI_CAPTCHA,
            'delay_ms': DELAY_BETWEEN_ACTIONS,
            'max_checks': MAX_CHECKS_PER_MINUTE,
            'max_joins': MAX_JOINS_PER_HOUR,
            'safety_enabled': True
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

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}      # {user_id: session_string}
active_clients = {}     # {user_id: TelegramClient}
user_data = {}          # Временные данные пользователей
checks_found = []       # Найденные чеки
checks_activated = 0    # Счетчик активированных чеков
start_time = time.time()

# Регулярные выражения для поиска чеков
CODE_REGEX = re.compile(
    r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start="
    r"(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})",
    re.IGNORECASE
)

URL_REGEX = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
PUBLIC_REGEX = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# Список ботов для мониторинга
MONITOR_CHATS = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Спецсимволы для очистки текста
SPECIAL_CHARS = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
TRANSLATION = str.maketrans('', '', SPECIAL_CHARS)

# Бот для управления
bot = TelegramClient('lovec_bot', API_ID, API_HASH)

# ========== СИСТЕМА БЕЗОПАСНОСТИ ==========
class SafetySystem:
    """Система безопасности для защиты от блокировок"""
    
    def __init__(self):
        self.action_history = []
    
    async def safe_action(self, action_type="check"):
        """Безопасное выполнение действия с задержками"""
        if not config.get('safety_enabled', True):
            return True
        
        now = time.time()
        
        # Очищаем старые записи
        self.action_history = [
            (t, tp) for t, tp in self.action_history 
            if now - t < 300  # 5 минут
        ]
        
        # Проверяем лимиты
        recent_checks = sum(1 for t, tp in self.action_history if tp == "check")
        recent_joins = sum(1 for t, tp in self.action_history if tp == "join")
        
        # Лимит проверок
        if action_type == "check" and recent_checks >= config.get('max_checks', 30):
            delay = random.uniform(30, 60)
            logger.warning(f"⚠️ Лимит чеков. Жду {delay:.1f} сек")
            await asyncio.sleep(delay)
            self.action_history = []
        
        # Лимит подписок
        if action_type == "join" and recent_joins >= config.get('max_joins', 20):
            delay = random.uniform(60, 120)
            logger.warning(f"⚠️ Лимит подписок. Жду {delay:.1f} сек")
            await asyncio.sleep(delay)
            self.action_history = []
        
        # Случайная задержка
        delay_ms = config.get('delay_ms', 1000)
        delay = random.uniform(delay_ms/2, delay_ms*1.5) / 1000
        await asyncio.sleep(delay)
        
        # Записываем действие
        self.action_history.append((now, action_type))
        return True
    
    async def check_connection(self, client):
        """Проверяет соединение и переподключает при необходимости"""
        try:
            if not await client.is_user_authorized():
                logger.warning("⚠️ Сессия не авторизована, переподключаем...")
                return False
            
            # Проверяем связь
            await client.get_me()
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка соединения: {e}")
            try:
                await client.connect()
                if await client.is_user_authorized():
                    return True
            except:
                pass
            return False

safety = SafetySystem()

# ========== ФУНКЦИИ УПРАВЛЕНИЯ ==========
def create_main_menu():
    """Создает главное меню с кнопками"""
    return [
        [Button.inline("🔐 Войти в аккаунт", b"auth:login")],
        [Button.inline("🎯 Статус ловли", b"catch:status")],
        [
            Button.inline("⚙️ Настройки", b"settings:main"),
            Button.inline("📊 Статистика", b"stats:main")
        ],
        [Button.inline("🔄 Обновить", b"menu:refresh")]
    ]

def create_auth_menu():
    """Меню авторизации"""
    return [
        [Button.request_phone("📱 Поделиться номером")],
        [Button.inline("✏️ Ввести вручную", b"auth:manual")],
        [Button.inline("🔙 Назад", b"menu:main")]
    ]

def create_settings_menu():
    """Меню настроек"""
    return [
        [
            Button.inline(f"{'✅' if config.get('auto_start') else '❌'} Автозапуск", b"settings:toggle:auto_start"),
            Button.inline(f"{'✅' if config.get('notifications') else '❌'} Уведомления", b"settings:toggle:notifications")
        ],
        [
            Button.inline(f"{'✅' if config.get('auto_subscribe') else '❌'} Автоподписка", b"settings:toggle:auto_subscribe"),
            Button.inline(f"{'✅' if config.get('solve_captcha') else '❌'} Капчи", b"settings:toggle:solve_captcha")
        ],
        [
            Button.inline(f"{'✅' if config.get('safety_enabled') else '❌'} Безопасность", b"settings:toggle:safety_enabled"),
            Button.inline("⚡ Скорость", b"settings:speed")
        ],
        [
            Button.inline("💾 Сохранить", b"settings:save"),
            Button.inline("🗑️ Сбросить", b"settings:reset")
        ],
        [Button.inline("🔙 Назад", b"menu:main")]
    ]

def create_numpad():
    """Цифровая клавиатура"""
    return [
        [
            Button.inline("1", b"num:1"),
            Button.inline("2", b"num:2"), 
            Button.inline("3", b"num:3")
        ],
        [
            Button.inline("4", b"num:4"),
            Button.inline("5", b"num:5"), 
            Button.inline("6", b"num:6")
        ],
        [
            Button.inline("7", b"num:7"),
            Button.inline("8", b"num:8"), 
            Button.inline("9", b"num:9")
        ],
        [
            Button.inline("0", b"num:0"),
            Button.inline("⌫", b"num:delete"),
            Button.inline("✅ Готово", b"num:submit")
        ]
    ]

# ========== ФУНКЦИИ OCR ДЛЯ КАПЧИ ==========
async def solve_captcha(image_data):
    """Решает капчу через OCR API"""
    if not config.get('solve_captcha') or not OCR_API_KEY:
        return None
    
    try:
        # Используем бесплатный OCR API
        api_url = 'https://api.ocr.space/parse/image'
        
        response = requests.post(
            api_url,
            files={'file': ('captcha.jpg', image_data, 'image/jpeg')},
            data={
                'apikey': OCR_API_KEY,
                'language': 'eng',
                'isOverlayRequired': False,
                'isTable': False,
                'scale': True,
                'OCREngine': 2
            },
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('IsErroredOnProcessing'):
                logger.warning(f"OCR ошибка: {result.get('ErrorMessage', 'Unknown')}")
                return None
            
            # Извлекаем текст
            parsed_text = result.get('ParsedResults', [{}])[0].get('ParsedText', '')
            text = parsed_text.strip()
            
            # Очищаем текст (только цифры)
            digits = ''.join(filter(str.isdigit, text))
            
            if len(digits) >= 4:  # Минимум 4 цифры для кода
                logger.info(f"✅ Капча решена: {digits}")
                return digits
            
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка решения капчи: {e}")
        return None

# ========== ПРОВЕРКА АДМИНА ==========
async def is_admin(user_id):
    """Проверяет, является ли пользователь админом"""
    return user_id == ADMIN_ID

# ========== ОСНОВНЫЕ ОБРАБОТЧИКИ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Команда /start - главное меню"""
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **LOVEC CHECK BOT v3.0**\n\n"
        f"👑 Админ: `{ADMIN_ID}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
        f"💰 Чеков: {checks_activated}\n\n"
        f"⚡ **Версия:** 3.0 (Полная)\n"
        f"🌐 **Хостинг:** songaura.onrender.com",
        buttons=create_main_menu()
    )

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    """Команда /status - статус системы"""
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен!")
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    message = (
        f"📊 **СТАТУС СИСТЕМЫ**\n\n"
        f"⏳ Работает: {hours}ч {minutes}м\n"
        f"💰 Чеков: {checks_activated}\n"
        f"📈 Найдено: {len(checks_found)}\n"
        f"🔗 Сессий: {len(user_sessions)}\n"
        f"🎣 Активных: {len(active_clients)}\n"
        f"🛡️ Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
        f"⚡ Задержка: {config.get('delay_ms')}мс\n\n"
        f"👑 Админ: {ADMIN_ID}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )
    
    await event.reply(message, buttons=[[Button.inline("🔙 В меню", b"menu:main")]])

@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Команда /help - справка"""
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен!")
        return
    
    help_text = f"""
🤖 **LOVEC CHECK BOT v3.0 - СПРАВКА**

**Основные команды:**
/start - Главное меню
/status - Статус системы
/help - Эта справка

**Основные функции:**
• Автоматическая ловля чеков
• Поддержка 2FA
• Автоподписка на каналы
• Решение капч (OCR)
• Система безопасности с лимитами
• Настраиваемая скорость работы
• Уведомления в канал

**Поддерживаемые боты:**
• @CryptoBot
• @wallet
• @tonRocketBot
• @xrocket
• @CryptoTestnetBot
• @xJetSwapBot

**Безопасность:**
• Лимит проверок: {config.get('max_checks')}/мин
• Лимит подписок: {config.get('max_joins')}/час
• Задержка: {config.get('delay_ms')}мс

**Настройки:**
• Автозапуск: {'✅' if config.get('auto_start') else '❌'}
• Уведомления: {'✅' if config.get('notifications') else '❌'}
• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}
• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}
"""
    
    await event.reply(help_text, buttons=[[Button.inline("🔙 В меню", b"menu:main")]])

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.on(events.CallbackQuery)
async def button_handler(event):
    """Обработка ВСЕХ инлайн кнопок"""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    data = event.data.decode()
    parts = data.split(":")
    
    try:
        # Главное меню
        if parts[0] == "menu":
            if parts[1] == "main":
                await event.edit(
                    f"🤖 **LOVEC CHECK BOT v3.0**\n\n"
                    f"👑 Админ: `{ADMIN_ID}`\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                    f"💰 Чеков: {checks_activated}\n"
                    f"🔗 Сессий: {len(user_sessions)}\n"
                    f"🎣 Активных: {len(active_clients)}",
                    buttons=create_main_menu()
                )
            elif parts[1] == "refresh":
                await event.edit(
                    f"🤖 **LOVEC CHECK BOT v3.0**\n\n"
                    f"👑 Админ: `{ADMIN_ID}`\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                    f"💰 Чеков: {checks_activated}\n"
                    f"🔗 Сессий: {len(user_sessions)}\n"
                    f"🎣 Активных: {len(active_clients)}",
                    buttons=create_main_menu()
                )
                await event.answer("✅ Обновлено!")
        
        # Авторизация
        elif parts[0] == "auth":
            if parts[1] == "login":
                await event.edit(
                    "🔐 **ВХОД В АККАУНТ**\n\n"
                    "📱 **Выберите способ:**\n\n"
                    "1. 📲 Поделиться номером (рекомендуется)\n"
                    "2. ✏️ Ввести номер вручную\n\n"
                    "✅ После входа бот начнет работу автоматически!",
                    buttons=create_auth_menu()
                )
            
            elif parts[1] == "manual":
                await event.edit(
                    "✏️ **ВВОД НОМЕРА ВРУЧНУЮ**\n\n"
                    "📱 Отправьте номер телефона в формате:\n\n"
                    "📌 **Примеры:**\n"
                    "• +380681234567\n"
                    "• +79123456789\n"
                    "• +12345678900\n\n"
                    "✏️ Просто отправьте номер сообщением",
                    buttons=[[Button.inline("🔙 Назад", b"auth:login")]]
                )
                user_data[user_id] = {'state': 'waiting_phone'}
        
        # Ловля чеков
        elif parts[0] == "catch":
            if parts[1] == "status":
                if user_id in active_clients:
                    status = "✅ АКТИВНА"
                    action_btn = [Button.inline("🛑 Остановить", b"catch:stop")]
                else:
                    if user_id in user_sessions:
                        status = "⏸️ ГОТОВА"
                        action_btn = [Button.inline("🚀 Запустить", b"catch:start")]
                    else:
                        status = "❌ НЕТ СЕССИИ"
                        action_btn = [Button.inline("🔐 Войти", b"auth:login")]
                
                await event.edit(
                    f"🎯 **СТАТУС ЛОВЛИ**\n\n"
                    f"🔐 Сессия: {'✅ ЕСТЬ' if user_id in user_sessions else '❌ НЕТ'}\n"
                    f"🎣 Ловля: {status}\n"
                    f"💰 Чеков: {checks_activated}\n"
                    f"🛡️ Безопасность: {'✅ ВКЛ' if config.get('safety_enabled') else '❌ ВЫКЛ'}\n\n"
                    f"⚙️ Автозапуск: {'✅ ВКЛ' if config.get('auto_start') else '❌ ВЫКЛ'}",
                    buttons=[action_btn, [Button.inline("🔙 Назад", b"menu:main")]]
                )
            
            elif parts[1] == "start":
                if user_id not in user_sessions:
                    await event.answer("❌ Сначала войдите в аккаунт!", alert=True)
                    return
                
                if user_id in active_clients:
                    await event.answer("✅ Уже запущено!", alert=True)
                    return
                
                await event.edit("🎯 **Запускаю ловлю...**")
                asyncio.create_task(start_catching(user_id))
                await event.answer("✅ Ловля запущена!", alert=True)
                await asyncio.sleep(1)
                await event.delete()
            
            elif parts[1] == "stop":
                if user_id in active_clients:
                    try:
                        await active_clients[user_id].disconnect()
                        del active_clients[user_id]
                        await event.edit("🛑 **Ловля остановлена!**")
                        await event.answer("✅ Остановлено!", alert=True)
                    except:
                        await event.answer("⚠️ Ошибка остановки", alert=True)
                else:
                    await event.answer("ℹ️ Ловля не запущена", alert=True)
        
        # Настройки
        elif parts[0] == "settings":
            if parts[1] == "main":
                await event.edit(
                    "⚙️ **НАСТРОЙКИ БОТА**\n\n"
                    "✅ **Текущие настройки:**\n"
                    f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n\n"
                    "🛠️ **Изменить настройки:**",
                    buttons=create_settings_menu()
                )
            
            elif parts[1] == "toggle":
                setting = parts[2]
                new_value = config.toggle(setting)
                
                await event.answer(
                    f"✅ {setting}: {'ВКЛ' if new_value else 'ВЫКЛ'}",
                    alert=True
                )
                await event.edit(
                    "⚙️ **НАСТРОЙКИ БОТА**\n\n"
                    "✅ **Текущие настройки:**\n"
                    f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n\n"
                    "🛠️ **Изменить настройки:**",
                    buttons=create_settings_menu()
                )
            
            elif parts[1] == "speed":
                await event.edit(
                    "⚡ **НАСТРОЙКА СКОРОСТИ**\n\n"
                    f"📊 Текущая задержка: {config.get('delay_ms')} мс\n"
                    f"🎯 Чеков/минуту: {config.get('max_checks')}\n"
                    f"📈 Подписок/час: {config.get('max_joins')}\n\n"
                    "🔧 **Изменить задержку:**",
                    buttons=[
                        [Button.inline("🐢 Медленно (2000мс)", b"settings:delay:2000")],
                        [Button.inline("⚡ Средне (1000мс)", b"settings:delay:1000")],
                        [Button.inline("🚀 Быстро (500мс)", b"settings:delay:500")],
                        [Button.inline("🔙 Назад", b"settings:main")]
                    ]
                )
            
            elif parts[1] == "delay":
                delay = int(parts[2])
                config.set('delay_ms', delay)
                await event.answer(f"✅ Задержка: {delay}мс", alert=True)
                await event.edit(
                    "⚙️ **НАСТРОЙКИ БОТА**\n\n"
                    "✅ **Текущие настройки:**\n"
                    f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n\n"
                    "🛠️ **Изменить настройки:**",
                    buttons=create_settings_menu()
                )
            
            elif parts[1] == "save":
                # Сохраняем настройки в файл
                try:
                    with open('config.json', 'w') as f:
                        json.dump(config.settings, f)
                    await event.answer("✅ Настройки сохранены!", alert=True)
                except Exception as e:
                    await event.answer(f"❌ Ошибка сохранения: {e}", alert=True)
            
            elif parts[1] == "reset":
                config.settings = {
                    'active': False,
                    'auto_start': True,
                    'notifications': True,
                    'auto_subscribe': True,
                    'solve_captcha': ANTI_CAPTCHA,
                    'delay_ms': DELAY_BETWEEN_ACTIONS,
                    'max_checks': MAX_CHECKS_PER_MINUTE,
                    'max_joins': MAX_JOINS_PER_HOUR,
                    'safety_enabled': True
                }
                await event.answer("✅ Настройки сброшены!", alert=True)
                await event.edit(
                    "⚙️ **НАСТРОЙКИ БОТА**\n\n"
                    "✅ **Текущие настройки:**\n"
                    f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n\n"
                    "🛠️ **Изменить настройки:**",
                    buttons=create_settings_menu()
                )
        
        # Статистика
        elif parts[0] == "stats":
            uptime = time.time() - start_time
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            
            await event.edit(
                f"📊 **СТАТИСТИКА**\n\n"
                f"⏳ Работает: {hours}ч {minutes}м\n"
                f"💰 Чеков: {checks_activated}\n"
                f"📈 Найдено: {len(checks_found)}\n"
                f"🔗 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных ловцов: {len(active_clients)}\n\n"
                f"⚙️ **Настройки:**\n"
                f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
                f"• Задержка: {config.get('delay_ms')}мс\n"
                f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}",
                buttons=[[Button.inline("🔄 Обновить", b"stats:main"), Button.inline("🔙 Назад", b"menu:main")]]
            )
        
        # Цифровая клавиатура
        elif parts[0] == "num":
            if user_id not in user_data or user_data[user_id].get('state') != 'waiting_code':
                await event.answer("❌ Неверный контекст!", alert=True)
                return
            
            action = parts[1]
            current_code = user_data[user_id].get('code', '')
            
            if action == "delete":
                if current_code:
                    user_data[user_id]['code'] = current_code[:-1]
            
            elif action == "submit":
                code = user_data[user_id].get('code', '')
                if len(code) >= 5:
                    await event.answer("🔐 Проверяю код...")
                    await process_telegram_code(user_id, code, event)
                    return
                else:
                    await event.answer("❌ Минимум 5 цифр!", alert=True)
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
                f"🔢 **Код из Telegram:** `{dots}`\n"
                f"📝 Введено: {len(new_code)} цифр\n\n"
                f"Нажмите ✅ Готово когда код будет полный",
                buttons=create_numpad()
            )
        
        await event.answer()
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки: {e}")
        await event.answer("⚠️ Ошибка обработки", alert=True)

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
    if user_id in user_data and user_data[user_id].get('state') == 'waiting_phone':
        if not text.startswith('+'):
            await event.reply("❌ Номер должен начинаться с '+' (пример: +380681234567)")
            return
        
        phone = text.replace(' ', '')
        await start_telegram_auth(user_id, phone, event)
    
    # Обработка пароля 2FA
    elif user_id in user_data and user_data[user_id].get('state') == 'waiting_password':
        await process_2fa_password(user_id, text, event)

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
    
    await start_telegram_auth(event.sender_id, phone, event)

# ========== АВТОРИЗАЦИЯ В TELEGRAM ==========
async def start_telegram_auth(user_id, phone, event=None):
    """Начинает авторизацию в Telegram"""
    try:
        # Создаем клиента
        client = TelegramClient(StringSession(), API_ID, API_HASH)
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
        
        message = (
            f"✅ **Код отправлен!**\n\n"
            f"📱 Номер: `{phone}`\n"
            f"⏳ Код действует: {sent_code.timeout} сек\n\n"
            f"🔢 **Введите код из Telegram:**\n\n"
            f"Используйте цифровую клавиатуру ниже"
        )
        
        if event and hasattr(event, 'reply'):
            await event.reply(message, buttons=create_numpad())
        else:
            await bot.send_message(user_id, message, buttons=create_numpad())
        
    except Exception as e:
        error_msg = str(e)
        if "A wait of" in error_msg:
            await bot.send_message(user_id, "⏳ Telegram ограничил запросы. Попробуйте позже.")
        elif "PHONE_NUMBER_INVALID" in error_msg:
            await bot.send_message(user_id, "❌ Неверный номер телефона!")
        else:
            await bot.send_message(user_id, f"❌ Ошибка: {error_msg[:100]}")
        
        if user_id in user_data:
            if 'client' in user_data[user_id]:
                await user_data[user_id]['client'].disconnect()
            del user_data[user_id]

async def process_telegram_code(user_id, code, event=None):
    """Обработка кода из Telegram"""
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
                    f"✅ **ВХОД УСПЕШЕН!**\n\n"
                    f"👤 Имя: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n\n"
                )
                
                await bot.send_message(user_id, success_msg)
                
                if config.get('auto_start'):
                    success_msg2 = "🎯 **Запускаю ловлю автоматически...**"
                    await bot.send_message(user_id, success_msg2)
                    
                    # Автозапуск ловли
                    asyncio.create_task(start_catching(user_id))
                else:
                    success_msg2 = "🎯 **Готов к работе!**\nНажмите 'Запустить' чтобы начать."
                    await bot.send_message(
                        user_id,
                        success_msg2,
                        buttons=[
                            [Button.inline("🚀 Запустить ловлю", b"catch:start")],
                            [Button.inline("🔙 В меню", b"menu:main")]
                        ]
                    )
                
                # Очищаем временные данные
                if 'client' in user_data[user_id]:
                    await user_data[user_id]['client'].disconnect()
                del user_data[user_id]
                
            else:
                await bot.send_message(user_id, "❌ Не удалось авторизоваться")
                await client.disconnect()
                
        except Exception as e:
            error_msg = str(e)
            
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await bot.send_message(
                    user_id,
                    "🔐 **Требуется пароль 2FA**\n\n"
                    "Введите пароль от двухфакторной аутентификации:"
                )
                user_data[user_id]['state'] = 'waiting_password'
                
            elif "PHONE_CODE_INVALID" in error_msg:
                await bot.send_message(user_id, "❌ Неверный код! Попробуйте снова")
                user_data[user_id]['code'] = ''
                await bot.send_message(
                    user_id,
                    f"📱 Номер: `{phone}`\n\n"
                    f"🔢 **Введите код снова:**",
                    buttons=create_numpad()
                )
                
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await bot.send_message(user_id, "❌ Код устарел! Начните заново")
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

async def process_2fa_password(user_id, password, event):
    """Обработка пароля 2FA"""
    try:
        client = user_data[user_id]['client']
        
        await client.sign_in(password=password)
        
        # Сохраняем сессию
        session_string = client.session.save()
        user_sessions[user_id] = session_string
        
        me = await client.get_me()
        
        success_msg = (
            f"✅ **ВХОД С 2FA УСПЕШЕН!**\n\n"
            f"👤 {me.first_name}\n"
            f"📱 {me.phone}\n\n"
        )
        
        if config.get('auto_start'):
            success_msg += "🎯 **Запускаю ловлю автоматически...**"
            await event.reply(success_msg)
            
            # Автозапуск ловли
            asyncio.create_task(start_catching(user_id))
        else:
            success_msg += "🎯 **Готов к работе!**"
            await event.reply(
                success_msg,
                buttons=[
                    [Button.inline("🚀 Запустить ловлю", b"catch:start")],
                    [Button.inline("🔙 В меню", b"menu:main")]
                ]
            )
        
        await client.disconnect()
        del user_data[user_id]
        
    except Exception as e:
        await event.reply(f"❌ Ошибка пароля: {e}")
        if user_id in user_data:
            if 'client' in user_data[user_id]:
                await user_data[user_id]['client'].disconnect()
            del user_data[user_id]

# ========== ЛОВЛЯ ЧЕКОВ ==========
async def start_catching(user_id):
    """Запуск ловли чеков"""
    if user_id not in user_sessions:
        logger.error(f"❌ Нет сессии для пользователя {user_id}")
        return
    
    try:
        # Создаем клиента из сессии
        client = TelegramClient(StringSession(user_sessions[user_id]), API_ID, API_HASH)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        logger.info(f"✅ Ловля запущена для {me.first_name} ({me.phone})")
        
        # Уведомление о запуске
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"🎯 **ЛОВЛЯ ЗАПУЩЕНА!**\n\n"
                    f"👤 {me.first_name}\n"
                    f"📱 {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"💰 Чеков: {checks_activated}"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление: {e}")
        
        # Основной обработчик сообщений
        @client.on(events.NewMessage(chats=MONITOR_CHATS))
        async def check_handler(event):
            """Обработчик чеков"""
            await safety.safe_action("check")
            
            try:
                text = event.text or ''
                cleaned_text = text.translate(TRANSLATION)
                
                # Ищем чеки
                found_matches = CODE_REGEX.findall(cleaned_text)
                
                for bot_name, code in found_matches:
                    if code not in checks_found:
                        logger.info(f"🎯 Найден чек: {code[:10]}... для @{bot_name}")
                        checks_found.append(code)
                        
                        # Активируем чек
                        await safety.safe_action("check")
                        
                        try:
                            await client.send_message(bot_name, f'/start {code}')
                            logger.info(f"✅ Чек активирован: {code[:10]}...")
                            
                            global checks_activated
                            checks_activated += 1
                            
                            # Уведомление
                            if config.get('notifications'):
                                try:
                                    await bot.send_message(
                                        CHANNEL_ID,
                                        f"💰 **ЧЕК АКТИВИРОВАН!**\n\n"
                                        f"🎯 Код: `{code[:10]}...`\n"
                                        f"🤖 Бот: @{bot_name}\n"
                                        f"👤 От: {me.first_name}\n"
                                        f"📊 Всего: {checks_activated}\n"
                                        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                                    )
                                except:
                                    pass
                            
                            # Автовывод
                            if AUTO_WITHDRAW and WITHDRAW_TAG:
                                await asyncio.sleep(5)
                                await auto_withdraw(client, bot_name)
                                
                        except Exception as e:
                            logger.error(f"❌ Ошибка активации чека: {e}")
                
                # Обработка капч
                if config.get('solve_captcha') and "captcha" in text.lower():
                    if event.message.photo:
                        try:
                            photo = event.message.photo
                            image_data = await client.download_media(photo, bytes)
                            
                            if image_data:
                                captcha_code = await solve_captcha(image_data)
                                
                                if captcha_code:
                                    await asyncio.sleep(1)
                                    await event.reply(captcha_code)
                                    logger.info(f"✅ Капча решена: {captcha_code}")
                                    
                                    if config.get('notifications'):
                                        try:
                                            await bot.send_message(
                                                CHANNEL_ID,
                                                f"🛡️ **КАПЧА РЕШЕНА!**\n\n"
                                                f"🔢 Код: {captcha_code}\n"
                                                f"👤 Для: {me.first_name}\n"
                                                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                                            )
                                        except:
                                            pass
                        except Exception as e:
                            logger.warning(f"⚠️ Ошибка решения капчи: {e}")
                
                # Автоподписка на каналы
                if config.get('auto_subscribe') and event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                url = button.url
                                if not url:
                                    continue
                                
                                await safety.safe_action("join")
                                
                                # Приватные каналы
                                private_match = URL_REGEX.search(url)
                                if private_match:
                                    try:
                                        await client(ImportChatInviteRequest(private_match.group(1)))
                                        logger.info(f"✅ Подписался на приватный канал")
                                        await asyncio.sleep(2)
                                    except Exception as e:
                                        if "FLOOD_WAIT" in str(e):
                                            wait_time = int(str(e).split()[-2])
                                            logger.warning(f"⏳ Flood wait {wait_time} секунд")
                                            await asyncio.sleep(wait_time)
                                
                                # Публичные каналы
                                public_match = PUBLIC_REGEX.search(url)
                                if public_match:
                                    try:
                                        await client(JoinChannelRequest(public_match.group(1)))
                                        logger.info(f"✅ Подписался на @{public_match.group(1)}")
                                        await asyncio.sleep(2)
                                    except Exception as e:
                                        if "FLOOD_WAIT" in str(e):
                                            wait_time = int(str(e).split()[-2])
                                            logger.warning(f"⏳ Flood wait {wait_time} секунд")
                                            await asyncio.sleep(wait_time)
                                
                            except Exception as e:
                                if "FLOOD_WAIT" not in str(e):
                                    logger.warning(f"⚠️ Ошибка подписки: {e}")
                                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения: {e}")
        
        # Обработчик новых сообщений в личке (для тестовых ботов)
        @client.on(events.NewMessage())
        async def private_handler(event):
            """Обработчик личных сообщений"""
            try:
                chat = await event.get_chat()
                if chat.id in MONITOR_CHATS:
                    return  # Уже обрабатывается в основном обработчике
                    
                text = event.text or ''
                
                # Ищем чеки в личных сообщениях
                found_matches = CODE_REGEX.findall(text)
                
                for bot_name, code in found_matches:
                    if code not in checks_found:
                        logger.info(f"🎯 Найден чек в ЛС: {code[:10]}... для @{bot_name}")
                        checks_found.append(code)
                        
                        await safety.safe_action("check")
                        await client.send_message(bot_name, f'/start {code}')
                        
                        global checks_activated
                        checks_activated += 1
                        
                        logger.info(f"✅ Чек из ЛС активирован: {code[:10]}...")
                        
            except Exception as e:
                logger.warning(f"⚠️ Ошибка обработки ЛС: {e}")
        
        # Проверка соединения каждые 5 минут
        async def connection_checker():
            while user_id in active_clients:
                try:
                    if not await safety.check_connection(client):
                        logger.warning(f"⚠️ Потеряно соединение для {me.first_name}")
                        
                        # Пытаемся переподключиться
                        await client.connect()
                        if await client.is_user_authorized():
                            logger.info(f"✅ Соединение восстановлено для {me.first_name}")
                        else:
                            logger.error(f"❌ Не удалось восстановить соединение для {me.first_name}")
                            break
                    
                    await asyncio.sleep(300)  # 5 минут
                    
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки соединения: {e}")
                    await asyncio.sleep(60)
        
        # Запускаем проверку соединения
        asyncio.create_task(connection_checker())
        
        # Бесконечный цикл
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        logger.info(f"🛑 Ловля остановлена для {me.first_name}")
        
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
        logger.error(f"❌ Ошибка ловли: {e}")
        if user_id in active_clients:
            del active_clients[user_id]

async def auto_withdraw(client, bot_name):
    """Автоматический вывод средств"""
    if not AUTO_WITHDRAW or not WITHDRAW_TAG:
        return
    
    try:
        await asyncio.sleep(3)
        
        # Проверяем баланс
        await client.send_message(bot_name, '/balance')
        
        # Ждем ответ
        await asyncio.sleep(2)
        
        # Выводим средства
        await client.send_message(bot_name, f'/withdraw {WITHDRAW_TAG}')
        
        logger.info(f"💰 Автовывод на {WITHDRAW_TAG}")
        
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"💸 **АВТОВЫВОД**\n\n"
                    f"👤 Пользователь: {WITHDRAW_TAG}\n"
                    f"🤖 Бот: @{bot_name}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
                
    except Exception as e:
        logger.warning(f"⚠️ Ошибка автовывода: {e}")

# ========== ЗАГРУЗКА И СОХРАНЕНИЕ ДАННЫХ ==========
async def load_saved_data():
    """Загружает сохраненные данные при запуске"""
    try:
        with open('sessions.json', 'r') as f:
            data = json.load(f)
        
        # Загружаем сессии
        if 'sessions' in data:
            user_sessions.update(data['sessions'])
        
        # Загружаем чеки
        if 'checks_found' in data:
            checks_found.extend(data['checks_found'])
        
        # Загружаем счетчик
        if 'checks_activated' in data:
            global checks_activated
            checks_activated = data['checks_activated']
        
        # Загружаем настройки
        if 'config' in data:
            for key, value in data['config'].items():
                config.set(key, value)
        
        logger.info(f"✅ Загружено {len(user_sessions)} сессий")
        logger.info(f"✅ Чеков в памяти: {len(checks_found)}")
        logger.info(f"✅ Активировано: {checks_activated}")
        
    except FileNotFoundError:
        logger.info("ℹ️ Файл sessions.json не найден, начинаем с чистого листа")
    except Exception as e:
        logger.error(f"⚠️ Ошибка загрузки данных: {e}")

async def save_data():
    """Сохраняет данные в файл"""
    try:
        data = {
            'sessions': user_sessions,
            'checks_found': checks_found,
            'checks_activated': checks_activated,
            'config': config.settings,
            'timestamp': time.time()
        }
        
        with open('sessions.json', 'w') as f:
            json.dump(data, f)
        
        logger.info("💾 Данные сохранены в sessions.json")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")

# ========== ЗАПУСК БОТА ==========
async def main():
    """Основная функция"""
    print("🚀 ЗАПУСКАЮ LOVEС CHECK BOT v3.0...")
    
    try:
        # Загружаем сохраненные данные
        await load_saved_data()
        
        # Запускаем бота
        await bot.start(bot_token=BOT_TOKEN)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        print(f"✅ API ID: {API_ID}")
        print(f"✅ Канал уведомлений: {CHANNEL_ID}")
        print(f"✅ Авто-капча: {ANTI_CAPTCHA}")
        print(f"✅ Авто-вывод: {AUTO_WITHDRAW}")
        print("=" * 60)
        
        # Отправляем сообщение админу
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🤖 **LOVEC CHECK BOT v3.0 ЗАПУЩЕН!**\n\n"
                f"🔗 Бот: @{me.username}\n"
                f"👑 Админ: `{ADMIN_ID}`\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"🌐 Хостинг: songaura.onrender.com\n\n"
                f"⚡ **Версия:** 3.0 (Полная)\n"
                f"🔐 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных: {len(active_clients)}\n"
                f"💰 Чеков: {checks_activated}\n\n"
                f"🎯 **КАК НАЧАТЬ:**\n"
                f"1. Нажмите '🔐 ВОЙТИ В АККАУНТ'\n"
                f"2. Поделитесь номером через кнопку\n"
                f"3. Введите код через клавиатуру\n"
                f"4. Наслаждайтесь ловлей чеков!\n\n"
                f"⚡ **АВТОМАТИЧЕСКИ:**\n"
                f"• Ловит чеки из {len(MONITOR_CHATS)} ботов\n"
                f"• Автоподписка на каналы\n"
                f"• Решает капчи: {'✅ ДА' if ANTI_CAPTCHA else '❌ НЕТ'}\n"
                f"• Автовывод: {'✅ ДА' if AUTO_WITHDRAW else '❌ НЕТ'}"
            )
        except Exception as e:
            print(f"⚠️ Не удалось отправить сообщение админу: {e}")
        
        print("✅ БОТ ГОТОВ К РАБОТЕ!")
        print("=" * 60)
        print("🎯 Ожидание команды /start от админа...")
        
        # Автозапуск сохраненных сессий
        if config.get('auto_start') and user_sessions:
            print("🔄 Автозапуск сохраненных сессий...")
            for user_id in user_sessions.keys():
                if user_id not in active_clients:
                    asyncio.create_task(start_catching(user_id))
                    await asyncio.sleep(2)  # Задержка между запусками
        
        # Запускаем бесконечный цикл
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Критическая ошибка при запуске: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🛑 Бот завершает работу...")
        
        # Сохраняем данные
        await save_data()
        
        # Отключаем всех клиентов
        for user_id, client in list(active_clients.items()):
            try:
                await client.disconnect()
                print(f"✅ Отключен клиент {user_id}")
            except:
                pass
        
        try:
            await bot.disconnect()
            print("✅ Бот отключен")
        except:
            pass
        
        print("✅ Работа завершена!")

# ========== ЗАВЕРШЕНИЕ ==========
def cleanup():
    """Функция очистки при завершении"""
    print("\n🧹 Очистка ресурсов...")
    
    # Сохраняем данные
    try:
        asyncio.run(save_data())
    except:
        pass
    
    print("✅ Очистка завершена")

# ========== ТОЧКА ВХОДА ==========
if __name__ == "__main__":
    import atexit
    import signal
    
    # Регистрируем функцию очистки
    atexit.register(cleanup)
    
    # Обработка Ctrl+C
    signal.signal(signal.SIGINT, lambda s, f: cleanup())
    
    try:
        print("=" * 60)
        print("🤖 LOVEС CHECK BOT v3.0 - ПОЛНАЯ ВЕРСИЯ")
        print("=" * 60)
        
        # Запускаем бота
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n\n🛑 Бот остановлен пользователем (Ctrl+C)")
        cleanup()
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
