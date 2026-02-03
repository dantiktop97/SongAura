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

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
API_ID = int(os.getenv('API_ID', '2040'))
API_HASH = os.getenv('API_HASH', 'b18441a1ff607e10a989891a5462e627')
BOT_TOKEN = os.getenv('LOVEC', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))

# Настройки ловли
CHANNEL_ID = int(os.getenv('CHANNEL', '-1004902536707'))
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')
AUTO_WITHDRAW = os.getenv('AUTO_WITHDRAW', 'False').lower() == 'true'
WITHDRAW_TAG = os.getenv('WITHDRAW_TAG', '')

# Настройки безопасности
MAX_CHECKS_PER_MINUTE = int(os.getenv('MAX_CHECKS', '30'))
MAX_JOINS_PER_HOUR = int(os.getenv('MAX_JOINS', '20'))
DELAY_BETWEEN_ACTIONS = int(os.getenv('DELAY_MS', '1000'))

# Проверка обязательных настроек
if not all([API_ID, API_HASH, BOT_TOKEN, ADMIN_ID]):
    logger.error("❌ Отсутствуют обязательные настройки!")
    print("=" * 60)
    print("❌ ОШИБКА: Проверьте .env файл!")
    print("Нужно установить: API_ID, API_HASH, LOVEC, ADMIN_ID")
    print("=" * 60)
    exit(1)

print("=" * 60)
print("🤖 LOVEС CHECK BOT v5.0 - ПОЛНАЯ ВЕРСИЯ")
print("=" * 60)
print(f"✅ API_ID: {API_ID}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ CHANNEL_ID: {CHANNEL_ID}")
print(f"✅ ANTI_CAPTCHA: {ANTI_CAPTCHA}")
print(f"✅ AUTO_WITHDRAW: {AUTO_WITHDRAW}")
print("=" * 60)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}          # {user_id: session_string}
active_clients = {}         # {user_id: TelegramClient}
user_data = {}              # Временные данные пользователей
checks_found = []           # Найденные чеки
checks_activated = 0        # Счетчик активированных чеков
withdraw_requests = []      # Запросы на вывод
start_time = time.time()    # Время запуска бота

# Регулярные выражения для поиска чеков
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

# Список ботов для мониторинга
MONITOR_CHATS = [
    1622808649,    # CryptoBot
    1559501630,    # @send bot
    1985737506,    # @tonRocketBot
    5014831088,    # @CryptoTestnetBot
    6014729293,    # @wallet
    5794061503,    # @xrocket
    6441848221     # @xJetSwapBot
]

# Спецсимволы для очистки текста
SPECIAL_CHARS = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
TRANSLATION = str.maketrans('', '', SPECIAL_CHARS)

# ========== СИСТЕМА КОНФИГУРАЦИИ ==========
class Config:
    def __init__(self):
        self.config_file = 'config.json'
        self.default_settings = {
            'auto_start': True,
            'notifications': True,
            'auto_subscribe': True,
            'solve_captcha': ANTI_CAPTCHA,
            'safety_enabled': True,
            'auto_withdraw': AUTO_WITHDRAW,
            'delay_ms': DELAY_BETWEEN_ACTIONS,
            'max_checks': MAX_CHECKS_PER_MINUTE,
            'max_joins': MAX_JOINS_PER_HOUR
        }
        self.settings = self.default_settings.copy()
    
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
    
    def save_to_file(self):
        """Сохраняет настройки в файл"""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f, indent=4)
            logger.info(f"✅ Настройки сохранены в {self.config_file}")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения настроек: {e}")
            return False
    
    def load_from_file(self):
        """Загружает настройки из файла"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    loaded_settings = json.load(f)
                    # Обновляем только существующие ключи
                    for key in self.settings.keys():
                        if key in loaded_settings:
                            self.settings[key] = loaded_settings[key]
                logger.info(f"✅ Настройки загружены из {self.config_file}")
            else:
                logger.info(f"ℹ️ Файл {self.config_file} не найден, создаю новый...")
                self.save_to_file()
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки настроек: {e}")
            # Создаем новый файл с настройками по умолчанию
            self.settings = self.default_settings.copy()
            self.save_to_file()

config = Config()
config.load_from_file()

# ========== СИСТЕМА БЕЗОПАСНОСТИ ==========
class SafetySystem:
    def __init__(self):
        self.action_history = []
        self.flood_wait_until = 0
    
    async def safe_action(self, action_type="check"):
        """Безопасное выполнение действия с задержками"""
        if not config.get('safety_enabled', True):
            return True
        
        # Проверяем flood wait
        now = time.time()
        if now < self.flood_wait_until:
            wait_time = self.flood_wait_until - now
            logger.warning(f"⏳ Flood wait, жду {wait_time:.1f} секунд")
            await asyncio.sleep(wait_time)
        
        # Очищаем старые записи
        self.action_history = [t for t in self.action_history if now - t < 300]
        
        # Проверяем лимиты
        if action_type == "check" and len(self.action_history) >= config.get('max_checks', 30):
            delay = random.uniform(30, 60)
            logger.warning(f"⚠️ Лимит чеков. Жду {delay:.1f} сек")
            await asyncio.sleep(delay)
            self.action_history.clear()
        
        # Случайная задержка
        delay_ms = config.get('delay_ms', 1000)
        delay = random.uniform(delay_ms * 0.8, delay_ms * 1.2) / 1000
        await asyncio.sleep(delay)
        
        self.action_history.append(now)
        return True
    
    def set_flood_wait(self, seconds):
        """Устанавливает flood wait"""
        self.flood_wait_until = time.time() + seconds
        logger.warning(f"⏳ Установлен flood wait на {seconds} секунд")

safety = SafetySystem()

# ========== ОСНОВНОЙ БОТ ==========
bot = TelegramClient('lovec_bot', API_ID, API_HASH)

# ========== МЕНЮ И КНОПКИ ==========
def create_main_menu():
    """Создает главное меню"""
    return [
        [Button.inline("🎯 Статус ловли", b"status")],
        [Button.inline("⚙️ Настройки", b"settings"), Button.inline("📊 Статистика", b"stats")],
        [Button.inline("💰 Вывод средств", b"withdraw"), Button.inline("🔄 Перезапуск", b"restart")],
        [Button.inline("📋 Сессии", b"sessions"), Button.inline("🆘 Помощь", b"help")]
    ]

def create_status_menu():
    """Создает меню статуса"""
    has_session = ADMIN_ID in user_sessions
    is_active = ADMIN_ID in active_clients
    
    buttons = []
    
    if not has_session:
        buttons.append([Button.inline("🔐 Создать сессию (/login)", b"create_session")])
    elif not is_active:
        buttons.append([Button.inline("🚀 Запустить ловлю", b"start_catching")])
    else:
        buttons.append([Button.inline("🛑 Остановить ловлю", b"stop_catching")])
    
    buttons.append([Button.inline("🔙 Назад", b"main")])
    return buttons

def create_settings_menu():
    """Создает меню настроек"""
    return [
        [
            Button.inline(f"{'✅' if config.get('auto_start') else '❌'} Автозапуск", b"toggle_auto_start"),
            Button.inline(f"{'✅' if config.get('notifications') else '❌'} Уведомления", b"toggle_notifications")
        ],
        [
            Button.inline(f"{'✅' if config.get('auto_subscribe') else '❌'} Автоподписка", b"toggle_auto_subscribe"),
            Button.inline(f"{'✅' if config.get('solve_captcha') else '❌'} Решение капч", b"toggle_solve_captcha")
        ],
        [
            Button.inline(f"{'✅' if config.get('safety_enabled') else '❌'} Безопасность", b"toggle_safety"),
            Button.inline(f"{'✅' if config.get('auto_withdraw') else '❌'} Автовывод", b"toggle_auto_withdraw")
        ],
        [
            Button.inline("⚡ Скорость", b"speed_settings"),
            Button.inline("🛡️ Лимиты", b"limits_settings")
        ],
        [Button.inline("💾 Сохранить настройки", b"save_settings")],
        [Button.inline("🔙 Назад", b"main")]
    ]

def create_speed_menu():
    """Создает меню настроек скорости"""
    return [
        [Button.inline("🐢 Медленно (3000мс)", b"set_speed_3000")],
        [Button.inline("🚶 Средне (1500мс)", b"set_speed_1500")],
        [Button.inline("⚡ Быстро (800мс)", b"set_speed_800")],
        [Button.inline("🚀 Макс. скорость (400мс)", b"set_speed_400")],
        [Button.inline("🔙 Назад", b"settings")]
    ]

def create_limits_menu():
    """Создает меню настроек лимитов"""
    return [
        [Button.inline("🎯 10 чеков/мин", b"set_checks_10")],
        [Button.inline("🎯 20 чеков/мин", b"set_checks_20")],
        [Button.inline("🎯 30 чеков/мин", b"set_checks_30")],
        [Button.inline("🎯 50 чеков/мин", b"set_checks_50")],
        [Button.inline("🔙 Назад", b"settings")]
    ]

def create_withdraw_menu():
    """Создает меню вывода средств"""
    buttons = []
    
    if WITHDRAW_TAG:
        buttons.append([Button.inline(f"💰 Вывод на {WITHDRAW_TAG}", b"withdraw_now")])
    
    buttons.append([Button.inline("📊 История выводов", b"withdraw_history")])
    buttons.append([Button.inline("⚙️ Настройки вывода", b"withdraw_settings")])
    buttons.append([Button.inline("🔙 Назад", b"main")])
    
    return buttons

def create_numpad():
    """Создает цифровую клавиатуру"""
    return [
        [Button.inline("1", b"num_1"), Button.inline("2", b"num_2"), Button.inline("3", b"num_3")],
        [Button.inline("4", b"num_4"), Button.inline("5", b"num_5"), Button.inline("6", b"num_6")],
        [Button.inline("7", b"num_7"), Button.inline("8", b"num_8"), Button.inline("9", b"num_9")],
        [Button.inline("0", b"num_0"), Button.inline("⌫", b"num_del"), Button.inline("✅", b"num_submit")]
    ]

# ========== ФУНКЦИИ OCR ДЛЯ КАПЧИ ==========
async def solve_captcha(image_data):
    """Решает капчу через OCR API"""
    if not config.get('solve_captcha') or not OCR_API_KEY:
        return None
    
    try:
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
            if not result.get('IsErroredOnProcessing', False):
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

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Обработчик команды /start"""
    if event.sender_id != ADMIN_ID:
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **LOVEС CHECK BOT v5.0**\n\n"
        f"👑 Админ: `{ADMIN_ID}`\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
        f"💰 Чеков: {checks_activated}\n"
        f"🔗 Сессий: {len(user_sessions)}\n"
        f"🎣 Активных: {len(active_clients)}\n\n"
        f"⚡ **Версия:** 5.0 (Полная)\n"
        f"🌐 **Хостинг:** songaura.onrender.com\n\n"
        f"**Доступные команды:**\n"
        f"• /login - Создать сессию\n"
        f"• /stop - Остановить бота\n"
        f"• /help - Справка\n\n"
        f"**Используйте кнопки для управления:**",
        buttons=create_main_menu()
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_command(event):
    """Обработчик команды /login - создание сессии"""
    if event.sender_id != ADMIN_ID:
        await event.reply("🚫 Доступ запрещен!")
        return
    
    if ADMIN_ID in user_sessions:
        await event.reply(
            "⚠️ **У вас уже есть активная сессия!**\n\n"
            "Если хотите создать новую сессию:\n"
            "1. Нажмите '📋 Сессии'\n"
            "2. Удалите текущую сессию\n"
            "3. Используйте /login снова",
            buttons=create_main_menu()
        )
        return
    
    await event.reply(
        "🔐 **СОЗДАНИЕ СЕССИИ**\n\n"
        "Отправьте номер телефона в формате:\n\n"
        "📌 **Примеры:**\n"
        "• +380681234567\n"
        "• +79123456789\n"
        "• +12345678900\n\n"
        "Или поделитесь контактом 📱\n\n"
        "✏️ **Просто отправьте номер телефона:**"
    )
    
    user_data[ADMIN_ID] = {'state': 'waiting_phone'}

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    """Остановка бота"""
    if event.sender_id != ADMIN_ID:
        return
    
    await event.reply("🛑 Останавливаю бота...")
    
    # Останавливаем все активные клиенты
    for user_id, client in list(active_clients.items()):
        try:
            await client.disconnect()
            logger.info(f"✅ Остановлен клиент {user_id}")
        except:
            pass
    
    try:
        await bot.disconnect()
    except:
        pass
    
    await event.reply("✅ Бот остановлен!")

@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Справка по боту"""
    if event.sender_id != ADMIN_ID:
        return
    
    help_text = """
🤖 **LOVEС CHECK BOT v5.0 - ПОЛНАЯ СПРАВКА**

**📋 ОСНОВНЫЕ КОМАНДЫ:**
• /start - Главное меню
• /login - Создать новую сессию
• /stop - Остановить бота
• /help - Эта справка

**🎯 ФУНКЦИИ БОТА:**
• Автоматическая ловля чеков из 7+ ботов
• Автоподписка на каналы и группы
• Решение капч через OCR API
• Автоматический вывод средств
• Система безопасности с лимитами
• Сохранение сессий и настроек
• Уведомления в канал
• Поддержка 2FA

**⚙️ ПОДДЕРЖИВАЕМЫЕ БОТЫ:**
• @CryptoBot - CQ... коды
• @send - C-... коды
• @tonRocketBot - t_... коды
• @CryptoTestnetBot - c_... коды
• @wallet - mci_... коды
• @xrocket - CQ... коды
• @xJetSwapBot - CQ... коды

**🔧 НАСТРОЙКИ (через меню):**
• Скорость работы (400-3000мс)
• Лимиты проверок (10-50/мин)
• Включение/выключение функций
• Настройка автовывода
• Управление безопасностью

**🚀 КАК НАЧАТЬ:**
1. Используйте /login для создания сессии
2. Отправьте номер телефона
3. Введите код из Telegram
4. В главном меню нажмите "Запустить ловлю"
5. Настройте параметры в меню "Настройки"
"""
    
    await event.reply(help_text, buttons=create_main_menu())

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Обработчик всех инлайн-кнопок"""
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    try:
        data = event.data.decode('utf-8')
        logger.info(f"Кнопка: {data}")
        
        # Главное меню
        if data == "main":
            await event.edit(
                f"🤖 **LOVEС CHECK BOT v5.0**\n\n"
                f"👑 Админ: `{ADMIN_ID}`\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"🔗 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных: {len(active_clients)}\n\n"
                f"**Используйте кнопки для управления:**",
                buttons=create_main_menu()
            )
        
        # Статус
        elif data == "status":
            has_session = ADMIN_ID in user_sessions
            is_active = ADMIN_ID in active_clients
            
            if not has_session:
                status_text = "❌ НЕТ СЕССИИ"
                recommendation = "Используйте команду /login для создания сессии"
            elif not is_active:
                status_text = "⏸️ ГОТОВА К ЗАПУСКУ"
                recommendation = "Нажмите '🚀 Запустить ловлю' чтобы начать"
            else:
                status_text = "✅ АКТИВНА"
                recommendation = "Ловля чеков в процессе..."
            
            await event.edit(
                f"🎯 **СТАТУС СИСТЕМЫ**\n\n"
                f"🔐 Сессия: {'✅ ЕСТЬ' if has_session else '❌ НЕТ'}\n"
                f"🎣 Ловля: {status_text}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"📈 Найдено: {len(checks_found)}\n"
                f"🛡️ Безопасность: {'✅ ВКЛ' if config.get('safety_enabled') else '❌ ВЫКЛ'}\n\n"
                f"💡 **Рекомендация:**\n{recommendation}",
                buttons=create_status_menu()
            )
        
        # Создание сессии
        elif data == "create_session":
            await event.answer("ℹ️ Используйте команду /login для создания сессии", alert=True)
        
        # Запуск ловли
        elif data == "start_catching":
            if ADMIN_ID not in user_sessions:
                await event.answer("❌ Сначала создайте сессию через /login!", alert=True)
                return
            
            if ADMIN_ID in active_clients:
                await event.answer("✅ Ловля уже запущена!", alert=True)
                return
            
            await event.edit("🎯 **Запускаю ловлю чеков...**")
            asyncio.create_task(start_catching(ADMIN_ID))
            await event.answer("✅ Ловля запущена!", alert=True)
            
            # Возвращаемся в статус через 2 секунды
            await asyncio.sleep(2)
            await callback_handler(event)
        
        # Остановка ловли
        elif data == "stop_catching":
            if ADMIN_ID in active_clients:
                try:
                    await active_clients[ADMIN_ID].disconnect()
                    del active_clients[ADMIN_ID]
                    await event.edit("🛑 **Ловля остановлена!**")
                    await event.answer("✅ Остановлено!", alert=True)
                    
                    # Уведомление
                    if config.get('notifications'):
                        try:
                            await bot.send_message(
                                CHANNEL_ID,
                                f"🛑 **ЛОВЛЯ ОСТАНОВЛЕНА**\n\n"
                                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                                f"💰 Всего чеков: {checks_activated}"
                            )
                        except:
                            pass
                except Exception as e:
                    await event.answer(f"⚠️ Ошибка остановки: {e}", alert=True)
            else:
                await event.answer("ℹ️ Ловля не запущена", alert=True)
        
        # Настройки
        elif data == "settings":
            await event.edit(
                "⚙️ **НАСТРОЙКИ СИСТЕМЫ**\n\n"
                "✅ **Текущие настройки:**\n"
                f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
                f"• Автовывод: {'✅' if config.get('auto_withdraw') else '❌'}\n"
                f"• Задержка: {config.get('delay_ms')}мс\n"
                f"• Лимит чеков: {config.get('max_checks')}/мин\n\n"
                "🛠️ **Изменить настройки:**",
                buttons=create_settings_menu()
            )
        
        # Переключение настроек
        elif data.startswith("toggle_"):
            setting = data.replace("toggle_", "")
            
            if setting == "auto_start":
                new_val = config.toggle('auto_start')
                msg = f"Автозапуск: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "notifications":
                new_val = config.toggle('notifications')
                msg = f"Уведомления: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "auto_subscribe":
                new_val = config.toggle('auto_subscribe')
                msg = f"Автоподписка: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "solve_captcha":
                new_val = config.toggle('solve_captcha')
                msg = f"Решение капч: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "safety":
                new_val = config.toggle('safety_enabled')
                msg = f"Безопасность: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            elif setting == "auto_withdraw":
                new_val = config.toggle('auto_withdraw')
                msg = f"Автовывод: {'✅ ВКЛ' if new_val else '❌ ВЫКЛ'}"
            else:
                msg = "❌ Неизвестная настройка"
            
            await event.answer(msg, alert=True)
            await callback_handler(event)  # Обновляем меню
        
        # Настройки скорости
        elif data == "speed_settings":
            await event.edit(
                f"⚡ **НАСТРОЙКА СКОРОСТИ**\n\n"
                f"Текущая задержка: {config.get('delay_ms')}мс\n\n"
                "Выберите скорость работы:",
                buttons=create_speed_menu()
            )
        
        elif data.startswith("set_speed_"):
            try:
                speed = int(data.split("_")[2])
                config.set('delay_ms', speed)
                await event.answer(f"✅ Задержка установлена: {speed}мс", alert=True)
                await event.edit(
                    "⚙️ **НАСТРОЙКИ СИСТЕМЫ**\n\n"
                    "✅ **Текущие настройки:**\n"
                    f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
                    f"• Автовывод: {'✅' if config.get('auto_withdraw') else '❌'}\n"
                    f"• Задержка: {config.get('delay_ms')}мс\n"
                    f"• Лимит чеков: {config.get('max_checks')}/мин\n\n"
                    "🛠️ **Изменить настройки:**",
                    buttons=create_settings_menu()
                )
            except:
                await event.answer("❌ Ошибка установки скорости", alert=True)
        
        # Настройки лимитов
        elif data == "limits_settings":
            await event.edit(
                f"🛡️ **НАСТРОЙКА ЛИМИТОВ**\n\n"
                f"Текущий лимит: {config.get('max_checks')} чеков/мин\n\n"
                "Выберите лимит проверок:",
                buttons=create_limits_menu()
            )
        
        elif data.startswith("set_checks_"):
            try:
                checks = int(data.split("_")[2])
                config.set('max_checks', checks)
                await event.answer(f"✅ Лимит установлен: {checks} чеков/мин", alert=True)
                await event.edit(
                    "⚙️ **НАСТРОЙКИ СИСТЕМЫ**\n\n"
                    "✅ **Текущие настройки:**\n"
                    f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n"
                    f"• Уведомления: {'✅' if config.get('notifications') else '❌'}\n"
                    f"• Автоподписка: {'✅' if config.get('auto_subscribe') else '❌'}\n"
                    f"• Решение капч: {'✅' if config.get('solve_captcha') else '❌'}\n"
                    f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
                    f"• Автовывод: {'✅' if config.get('auto_withdraw') else '❌'}\n"
                    f"• Задержка: {config.get('delay_ms')}мс\n"
                    f"• Лимит чеков: {config.get('max_checks')}/мин\n\n"
                    "🛠️ **Изменить настройки:**",
                    buttons=create_settings_menu()
                )
            except:
                await event.answer("❌ Ошибка установки лимита", alert=True)
        
        # Сохранение настроек
        elif data == "save_settings":
            if config.save_to_file():
                await event.answer("✅ Настройки сохранены!", alert=True)
            else:
                await event.answer("❌ Ошибка сохранения настроек", alert=True)
        
        # Статистика
        elif data == "stats":
            uptime = time.time() - start_time
            hours = int(uptime // 3600)
            minutes = int((uptime % 3600) // 60)
            seconds = int(uptime % 60)
            
            # Рассчитываем среднюю скорость
            if uptime > 0:
                speed_per_hour = checks_activated / (uptime / 3600)
            else:
                speed_per_hour = 0
            
            await event.edit(
                f"📊 **ПОДРОБНАЯ СТАТИСТИКА**\n\n"
                f"⏳ **Время работы:** {hours}ч {minutes}м {seconds}с\n"
                f"💰 **Активировано чеков:** {checks_activated}\n"
                f"📈 **Найдено чеков:** {len(checks_found)}\n"
                f"📊 **Скорость:** {speed_per_hour:.1f} чеков/час\n"
                f"🔗 **Активных сессий:** {len(user_sessions)}\n"
                f"🎣 **Активных ловцов:** {len(active_clients)}\n\n"
                f"⚙️ **СИСТЕМНЫЕ НАСТРОЙКИ:**\n"
                f"• Безопасность: {'✅' if config.get('safety_enabled') else '❌'}\n"
                f"• Задержка: {config.get('delay_ms')}мс\n"
                f"• Лимит: {config.get('max_checks')} чеков/мин\n"
                f"• Автозапуск: {'✅' if config.get('auto_start') else '❌'}\n\n"
                f"👑 **АДМИНИСТРАТОР:**\n"
                f"ID: {ADMIN_ID}",
                buttons=[[Button.inline("🔄 Обновить", b"stats"), Button.inline("🔙 Назад", b"main")]]
            )
        
        # Вывод средств
        elif data == "withdraw":
            await event.edit(
                "💰 **УПРАВЛЕНИЕ ВЫВОДОМ**\n\n"
                f"Текущий тег для вывода: {WITHDRAW_TAG if WITHDRAW_TAG else '❌ Не установлен'}\n"
                f"Автовывод: {'✅ ВКЛ' if config.get('auto_withdraw') else '❌ ВЫКЛ'}\n"
                f"Всего запросов на вывод: {len(withdraw_requests)}\n\n"
                "Выберите действие:",
                buttons=create_withdraw_menu()
            )
        
        elif data == "withdraw_now":
            if not WITHDRAW_TAG:
                await event.answer("❌ Не установлен тег для вывода!", alert=True)
                return
            
            await event.answer("ℹ️ Функция в разработке", alert=True)
        
        elif data == "withdraw_history":
            if not withdraw_requests:
                history_text = "📭 История выводов пуста"
            else:
                history_text = "📋 **ИСТОРИЯ ВЫВОДОВ:**\n\n"
                for i, req in enumerate(withdraw_requests[-10:], 1):  # Последние 10 записей
                    history_text += f"{i}. {req.get('amount', '?')} → {req.get('tag', '?')}\n"
            
            await event.edit(
                f"{history_text}\n\n"
                f"Всего записей: {len(withdraw_requests)}",
                buttons=[[Button.inline("🔙 Назад", b"withdraw")]]
            )
        
        elif data == "withdraw_settings":
            await event.answer("ℹ️ Настройки вывода в .env файле: WITHDRAW_TAG", alert=True)
        
        # Сессии
        elif data == "sessions":
            if not user_sessions:
                sessions_text = "❌ Нет активных сессий"
            else:
                sessions_text = "🔗 **АКТИВНЫЕ СЕССИИ:**\n\n"
                for user_id in user_sessions.keys():
                    sessions_text += f"• Пользователь ID: {user_id}\n"
            
            await event.edit(
                f"{sessions_text}\n\n"
                f"Всего сессий: {len(user_sessions)}\n\n"
                "**Действия:**",
                buttons=[
                    [Button.inline("🗑️ Удалить мою сессию", b"delete_my_session")],
                    [Button.inline("🗑️ Удалить все сессии", b"delete_all_sessions")],
                    [Button.inline("🔙 Назад", b"main")]
                ]
            )
        
        elif data == "delete_my_session":
            if ADMIN_ID in user_sessions:
                # Останавливаем ловлю если активна
                if ADMIN_ID in active_clients:
                    try:
                        await active_clients[ADMIN_ID].disconnect()
                        del active_clients[ADMIN_ID]
                    except:
                        pass
                
                del user_sessions[ADMIN_ID]
                await event.answer("✅ Ваша сессия удалена!", alert=True)
                await event.edit(
                    "🗑️ **Сессия удалена!**\n\n"
                    "Используйте /login для создания новой сессии.",
                    buttons=[[Button.inline("🔙 В меню", b"main")]]
                )
            else:
                await event.answer("❌ У вас нет активной сессии", alert=True)
        
        elif data == "delete_all_sessions":
            # Останавливаем все активные клиенты
            for user_id, client in list(active_clients.items()):
                try:
                    await client.disconnect()
                except:
                    pass
            
            user_sessions.clear()
            await event.answer("✅ Все сессии удалены!", alert=True)
            await event.edit(
                "🗑️ **Все сессии удалены!**\n\n"
                "Используйте /login для создания новой сессии.",
                buttons=[[Button.inline("🔙 В меню", b"main")]]
            )
        
        # Перезапуск
        elif data == "restart":
            await event.edit("🔄 **Перезапускаю систему...**")
            
            # Останавливаем все активные клиенты
            for user_id, client in list(active_clients.items()):
                try:
                    await client.disconnect()
                except:
                    pass
            
            active_clients.clear()
            
            await asyncio.sleep(2)
            await event.edit(
                "✅ **Система перезапущена!**\n\n"
                "Все сессии сохранены.\n"
                "Используйте '🎯 Статус ловли' для запуска.",
                buttons=create_main_menu()
            )
        
        # Помощь
        elif data == "help":
            await event.answer("ℹ️ Отправьте /help для получения справки", alert=True)
        
        # Цифровая клавиатура (для ввода кода)
        elif data.startswith("num_"):
            if ADMIN_ID not in user_data or user_data[ADMIN_ID].get('state') != 'waiting_code':
                await event.answer("❌ Неверный контекст!", alert=True)
                return
            
            action = data.split("_")[1]
            current_code = user_data[ADMIN_ID].get('code', '')
            
            if action == "del":
                if current_code:
                    user_data[ADMIN_ID]['code'] = current_code[:-1]
            
            elif action == "submit":
                code = user_data[ADMIN_ID].get('code', '')
                if len(code) >= 5:
                    await event.answer("🔐 Проверяю код...")
                    await process_telegram_code(ADMIN_ID, code, event)
                    return
                else:
                    await event.answer("❌ Минимум 5 цифр!", alert=True)
                    return
            
            else:
                if len(current_code) < 10:
                    user_data[ADMIN_ID]['code'] = current_code + action
            
            # Обновляем отображение
            new_code = user_data[ADMIN_ID].get('code', '')
            phone = user_data[ADMIN_ID].get('phone', '')
            
            dots = "•" * len(new_code) if new_code else "____"
            
            await event.edit(
                f"📱 Номер: `{phone}`\n\n"
                f"🔢 **Код из Telegram:** `{dots}`\n"
                f"📝 Введено: {len(new_code)} цифр\n\n"
                f"Нажмите ✅ когда код будет полный",
                buttons=create_numpad()
            )
        
        await event.answer()
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки кнопки: {e}", exc_info=True)
        await event.answer("⚠️ Ошибка обработки", alert=True)

# ========== ОБРАБОТКА СООБЩЕНИЙ (ВВОД НОМЕРА И ПАРОЛЯ) ==========
@bot.on(events.NewMessage)
async def message_handler(event):
    """Обработчик текстовых сообщений"""
    if event.sender_id != ADMIN_ID:
        return
    
    text = event.text.strip()
    
    # Пропускаем команды
    if text.startswith('/'):
        return
    
    # Обработка ввода номера телефона
    if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'waiting_phone':
        if text.startswith('+'):
            phone = text.replace(' ', '')
            await start_telegram_auth(ADMIN_ID, phone, event)
        else:
            await event.reply("❌ Неверный формат номера. Пример: +380681234567\n\nПопробуйте снова:")
    
    # Обработка пароля 2FA
    elif ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'waiting_password':
        await process_2fa_password(ADMIN_ID, text, event)

@bot.on(events.NewMessage(func=lambda e: e.contact))
async def contact_handler(event):
    """Обработка контакта"""
    if event.sender_id != ADMIN_ID:
        return
    
    if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'waiting_phone':
        contact = event.contact
        if contact.user_id == ADMIN_ID:
            phone = contact.phone_number
            if not phone.startswith('+'):
                phone = '+' + phone
            
            await start_telegram_auth(ADMIN_ID, phone, event)
        else:
            await event.reply("❌ Это не ваш контакт!")

# ========== АВТОРИЗАЦИЯ В TELEGRAM ==========
async def start_telegram_auth(user_id, phone, event=None):
    """Начинает авторизацию в Telegram"""
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        sent_code = await client.send_code_request(phone)
        
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
            f"⏳ Код действует: {sent_code.timeout} секунд\n\n"
            f"🔢 **Введите код из Telegram:**\n\n"
            f"Используйте цифровую клавиатуру ниже:"
        )
        
        if event:
            await event.reply(message, buttons=create_numpad())
        else:
            await bot.send_message(user_id, message, buttons=create_numpad())
        
    except Exception as e:
        error_msg = str(e)
        if "A wait of" in error_msg:
            msg = "⏳ Telegram ограничил запросы. Попробуйте позже."
        elif "PHONE_NUMBER_INVALID" in error_msg:
            msg = "❌ Неверный номер телефона!"
        elif "PHONE_NUMBER_FLOOD" in error_msg:
            msg = "⚠️ Слишком много запросов с этого номера."
        else:
            msg = f"❌ Ошибка: {error_msg[:100]}"
        
        await bot.send_message(user_id, msg)
        
        if user_id in user_data:
            if 'client' in user_data[user_id]:
                try:
                    await user_data[user_id]['client'].disconnect()
                except:
                    pass
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
                    auto_msg = "🎯 **Запускаю ловлю автоматически...**"
                    await bot.send_message(user_id, auto_msg)
                    asyncio.create_task(start_catching(user_id))
                else:
                    await bot.send_message(
                        user_id,
                        "🎯 **Готов к работе!**\nНажмите 'Запустить ловлю' в меню статуса.",
                        buttons=create_main_menu()
                    )
                
                # Уведомление в канал
                if config.get('notifications'):
                    try:
                        await bot.send_message(
                            CHANNEL_ID,
                            f"🔐 **НОВАЯ СЕССИЯ СОЗДАНА**\n\n"
                            f"👤 Пользователь: {me.first_name}\n"
                            f"📱 Телефон: {me.phone}\n"
                            f"🆔 ID: `{me.id}`\n"
                            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
                            f"Всего сессий: {len(user_sessions)}"
                        )
                    except:
                        pass
                
                await client.disconnect()
                del user_data[user_id]
                
            else:
                await bot.send_message(user_id, "❌ Не удалось авторизоваться")
                await client.disconnect()
                
        except Exception as e:
            error_msg = str(e)
            
            if "SESSION_PASSWORD_NEEDED" in error_msg:
                await bot.send_message(
                    user_id,
                    "🔐 **ТРЕБУЕТСЯ ПАРОЛЬ 2FA**\n\n"
                    "Введите пароль от двухфакторной аутентификации:"
                )
                user_data[user_id]['state'] = 'waiting_password'
                
            elif "PHONE_CODE_INVALID" in error_msg:
                await bot.send_message(user_id, "❌ Неверный код! Попробуйте снова")
                user_data[user_id]['code'] = ''
                await bot.send_message(
                    user_id,
                    f"📱 Номер: `{phone}`\n\n🔢 **Введите код снова:**",
                    buttons=create_numpad()
                )
                
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await bot.send_message(user_id, "❌ Код устарел! Начните заново с /login")
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
                buttons=create_main_menu()
            )
        
        # Уведомление
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"🔐 **СЕССИЯ С 2FA СОЗДАНА**\n\n"
                    f"👤 {me.first_name}\n"
                    f"📱 {me.phone}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
        await client.disconnect()
        del user_data[user_id]
        
    except Exception as e:
        error_msg = str(e)
        if "PASSWORD_HASH_INVALID" in error_msg:
            await event.reply("❌ **НЕВЕРНЫЙ ПАРОЛЬ 2FA!**\n\nПопробуйте снова:")
        else:
            await event.reply(f"❌ Ошибка пароля: {error_msg[:100]}")
        
        if user_id in user_data:
            if 'client' in user_data[user_id]:
                try:
                    await user_data[user_id]['client'].disconnect()
                except:
                    pass
            del user_data[user_id]

# ========== ЛОВЛЯ ЧЕКОВ ==========
async def start_catching(user_id):
    """Запуск ловли чеков"""
    if user_id not in user_sessions:
        logger.error(f"❌ Нет сессии для пользователя {user_id}")
        return
    
    try:
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
                    f"👤 Пользователь: {me.first_name}\n"
                    f"📱 Телефон: {me.phone}\n"
                    f"🆔 ID: `{me.id}`\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
                    f"⚡ **Настройки:**\n"
                    f"• Задержка: {config.get('delay_ms')}мс\n"
                    f"• Лимит: {config.get('max_checks')}/мин\n"
                    f"• Безопасность: {'✅ ВКЛ' if config.get('safety_enabled') else '❌ ВЫКЛ'}"
                )
            except Exception as e:
                logger.warning(f"Не удалось отправить уведомление: {e}")
        
        # Основной обработчик сообщений
        @client.on(events.NewMessage(chats=MONITOR_CHATS))
        async def check_handler(event):
            await safety.safe_action("check")
            
            try:
                text = event.text or ''
                cleaned_text = text.translate(TRANSLATION)
                
                # Поиск чеков по всем паттернам
                for pattern in CODE_PATTERNS:
                    matches = re.findall(pattern, cleaned_text, re.IGNORECASE)
                    for match in matches:
                        # Извлекаем код
                        if '?start=' in match:
                            code = match.split('?start=')[1]
                            if code not in checks_found:
                                logger.info(f"🎯 Найден чек: {code[:10]}...")
                                checks_found.append(code)
                                
                                # Получаем имя бота
                                bot_name = match.split('t.me/')[1].split('?')[0]
                                
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
                                                f"👤 Пользователь: {me.first_name}\n"
                                                f"📊 Всего: {checks_activated}\n"
                                                f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                                            )
                                        except:
                                            pass
                                    
                                    # Автовывод
                                    if config.get('auto_withdraw') and WITHDRAW_TAG:
                                        await asyncio.sleep(3)
                                        await auto_withdraw(client, bot_name, me.first_name)
                                        
                                except Exception as e:
                                    if "FLOOD_WAIT" in str(e):
                                        wait_time = int(str(e).split()[-2])
                                        safety.set_flood_wait(wait_time)
                                        logger.warning(f"⏳ Flood wait {wait_time} секунд")
                                    else:
                                        logger.error(f"❌ Ошибка активации чека: {e}")
                
                # Обработка капч
                if config.get('solve_captcha') and ("captcha" in text.lower() or "капча" in text.lower()):
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
                                                f"👤 Пользователь: {me.first_name}\n"
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
                                            safety.set_flood_wait(wait_time)
                                            logger.warning(f"⏳ Flood wait {wait_time} секунд")
                                
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
                                            safety.set_flood_wait(wait_time)
                                            logger.warning(f"⏳ Flood wait {wait_time} секунд")
                                
                            except Exception as e:
                                if "FLOOD_WAIT" not in str(e):
                                    logger.warning(f"⚠️ Ошибка подписки: {e}")
                                    
            except Exception as e:
                logger.error(f"❌ Ошибка обработки сообщения: {e}")
        
        # Проверка соединения каждые 5 минут
        async def connection_checker():
            while user_id in active_clients:
                try:
                    await asyncio.sleep(300)
                    # Простая проверка - получаем информацию о себе
                    try:
                        await client.get_me()
                    except Exception as e:
                        logger.warning(f"⚠️ Потеряно соединение для {me.first_name}: {e}")
                        # Пытаемся переподключиться
                        await client.connect()
                        if await client.is_user_authorized():
                            logger.info(f"✅ Соединение восстановлено для {me.first_name}")
                        else:
                            logger.error(f"❌ Не удалось восстановить соединение для {me.first_name}")
                            break
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"❌ Ошибка проверки соединения: {e}")
                    await asyncio.sleep(60)
        
        # Запускаем проверку соединения
        checker_task = asyncio.create_task(connection_checker())
        
        # Бесконечный цикл ожидания
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Отменяем задачу проверки соединения
        checker_task.cancel()
        try:
            await checker_task
        except asyncio.CancelledError:
            pass
        
        # Остановка
        await client.disconnect()
        logger.info(f"🛑 Ловля остановлена для {me.first_name}")
        
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"🛑 **ЛОВЛЯ ОСТАНОВЛЕНА**\n\n"
                    f"👤 Пользователь: {me.first_name}\n"
                    f"💰 Чеков за сеанс: {checks_activated}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
    except Exception as e:
        logger.error(f"❌ Ошибка ловли: {e}", exc_info=True)
        if user_id in active_clients:
            del active_clients[user_id]

async def auto_withdraw(client, bot_name, user_name):
    """Автоматический вывод средств"""
    if not config.get('auto_withdraw') or not WITHDRAW_TAG:
        return
    
    try:
        await asyncio.sleep(3)
        
        # Отправляем команду баланса
        await client.send_message(bot_name, '/balance')
        await asyncio.sleep(2)
        
        # Отправляем команду вывода
        await client.send_message(bot_name, f'/withdraw {WITHDRAW_TAG}')
        
        logger.info(f"💰 Автовывод на {WITHDRAW_TAG}")
        
        # Сохраняем запрос
        withdraw_requests.append({
            'timestamp': time.time(),
            'user': user_name,
            'bot': bot_name,
            'tag': WITHDRAW_TAG
        })
        
        if config.get('notifications'):
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"💸 **АВТОВЫВОД СРЕДСТВ**\n\n"
                    f"👤 Пользователь: {user_name}\n"
                    f"🤖 Бот: @{bot_name}\n"
                    f"🏷️ Тег: {WITHDRAW_TAG}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
                
    except Exception as e:
        logger.warning(f"⚠️ Ошибка автовывода: {e}")

# ========== СОХРАНЕНИЕ И ЗАГРУЗКА ДАННЫХ ==========
async def save_all_data():
    """Сохраняет все данные в файлы"""
    try:
        # Сохраняем сессии
        sessions_data = {
            'sessions': user_sessions,
            'checks_found': checks_found,
            'checks_activated': checks_activated,
            'withdraw_requests': withdraw_requests,
            'timestamp': time.time()
        }
        
        with open('sessions.json', 'w') as f:
            json.dump(sessions_data, f, indent=4)
        
        logger.info("💾 Все данные сохранены")
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения данных: {e}")

async def load_all_data():
    """Загружает все данные из файлов"""
    try:
        if os.path.exists('sessions.json'):
            with open('sessions.json', 'r') as f:
                data = json.load(f)
            
            user_sessions.update(data.get('sessions', {}))
            checks_found.extend(data.get('checks_found', []))
            
            global checks_activated
            checks_activated = data.get('checks_activated', 0)
            
            withdraw_requests.extend(data.get('withdraw_requests', []))
            
            logger.info(f"✅ Загружено {len(user_sessions)} сессий")
            logger.info(f"✅ Чеков в памяти: {len(checks_found)}")
            logger.info(f"✅ Активировано: {checks_activated}")
        else:
            logger.info("ℹ️ Файл sessions.json не найден, начинаем с чистого листа")
    except Exception as e:
        logger.error(f"⚠️ Ошибка загрузки данных: {e}")

# ========== ЗАПУСК БОТА ==========
async def main():
    """Основная функция запуска бота"""
    print("🚀 ЗАПУСК LOVEС CHECK BOT v5.0...")
    
    try:
        # Загружаем сохраненные данные
        await load_all_data()
        
        # Запускаем бота
        await bot.start(bot_token=BOT_TOKEN)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        print(f"✅ Загружено сессий: {len(user_sessions)}")
        print(f"✅ Настроек загружено: {len(config.settings)}")
        print("=" * 60)
        print("✅ СИСТЕМА ГОТОВА К РАБОТЕ!")
        print("=" * 60)
        
        # Отправляем приветственное сообщение
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEС CHECK BOT v5.0 ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: `{ADMIN_ID}`\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
            f"🌐 Хостинг: songaura.onrender.com\n\n"
            f"⚡ **Версия:** 5.0 (Полная)\n"
            f"🔗 **Сессий:** {len(user_sessions)}\n"
            f"💰 **Чеков:** {checks_activated}\n\n"
            f"**📋 ДОСТУПНЫЕ КОМАНДЫ:**\n"
            f"• /start - Главное меню\n"
            f"• /login - Создать сессию\n"
            f"• /stop - Остановить бота\n"
            f"• /help - Справка\n\n"
            f"**🎯 КАК НАЧАТЬ:**\n"
            f"1. Используйте команду /login\n"
            f"2. Отправьте номер телефона\n"
            f"3. Введите код из Telegram\n"
            f"4. В меню нажмите 'Запустить ловлю'\n\n"
            f"**Используйте кнопки для управления системой!**"
        )
        
        print("⏳ Ожидание команд...")
        
        # Автозапуск сохраненных сессий
        if config.get('auto_start') and user_sessions:
            print("🔄 Автозапуск сохраненных сессий...")
            for user_id in list(user_sessions.keys()):
                if user_id not in active_clients:
                    asyncio.create_task(start_catching(user_id))
                    await asyncio.sleep(3)  # Задержка между запусками
        
        # Запускаем основной цикл
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Критическая ошибка при запуске: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("\n🛑 Завершение работы...")
        
        # Сохраняем все данные
        await save_all_data()
        config.save_to_file()
        
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
        
        print("✅ Все данные сохранены!")
        print("✅ Работа завершена!")

# ========== ЗАВЕРШЕНИЕ ==========
def cleanup():
    """Функция очистки при завершении"""
    print("\n🧹 Очистка ресурсов...")
    
    # Сохраняем данные синхронно
    try:
        # Создаем новое событийное loop для сохранения
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Сохраняем данные
        loop.run_until_complete(save_all_data())
        
        # Сохраняем настройки
        config.save_to_file()
        
        loop.close()
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
    def signal_handler(sig, frame):
        print(f"\n🛑 Получен сигнал {sig}, завершаю работу...")
        cleanup()
        exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Запускаем бота
        print("=" * 60)
        print("🤖 LOVEС CHECK BOT v5.0 - ПОЛНАЯ ВЕРСИЯ")
        print("=" * 60)
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\n\n🛑 Остановлено пользователем (Ctrl+C)")
        cleanup()
    except Exception as e:
        print(f"\n❌ Непредвиденная ошибка: {e}")
        import traceback
        traceback.print_exc()
        cleanup()
