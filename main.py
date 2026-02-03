import os
import asyncio
import time
import re
import json
import random
import requests
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from io import BytesIO
import base64

# ========== НАСТРОЙКИ ==========
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

# Проверка настроек
if not all([API_ID, API_HASH, BOT_TOKEN, ADMIN_ID]):
    print("❌ ОШИБКА: Проверьте настройки в .env файле!")
    print("Нужно установить: API_ID, API_HASH, LOVEC (токен бота), ADMIN_ID")
    exit(1)

print("=" * 60)
print("🤖 LOVEС CHECK BOT - ПОЛНАЯ ВЕРСИЯ")
print("=" * 60)
print(f"✅ API_ID: {API_ID}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ Канал: {CHANNEL_ID}")
print(f"✅ Капчи: {ANTI_CAPTCHA}")
print(f"✅ Автовывод: {AUTO_WITHDRAW}")
print(f"✅ Задержка: {DELAY_MS}мс")
print("=" * 60)

# ========== ВИРТУАЛЬНОЕ ХРАНИЛИЩЕ ==========
class VirtualStorage:
    def __init__(self):
        self.config = {
            'auto_start': True,
            'notifications': True,
            'auto_subscribe': True,
            'solve_captcha': ANTI_CAPTCHA,
            'safety_enabled': True,
            'auto_withdraw': AUTO_WITHDRAW,
            'delay_ms': DELAY_MS,
            'max_checks': MAX_CHECKS,
            'max_joins': MAX_JOINS
        }
        self.sessions = {}
        self.checks_found = []
        self.checks_activated = 0
        self.withdraw_history = []
    
    def save_config(self):
        """Сохраняет конфиг в память"""
        return True
    
    def load_config(self):
        """Загружает конфиг из памяти"""
        return True

storage = VirtualStorage()

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_sessions = {}
active_clients = {}
user_data = {}
checks_found = storage.checks_found
checks_activated = storage.checks_activated
withdraw_requests = storage.withdraw_history
start_time = time.time()

# Регулярки для чеков
PATTERNS = [
    r"t\.me/CryptoBot\?start=CQ[A-Za-z0-9]{10}",
    r"t\.me/send\?start=C-[A-Za-z0-9]{10}",
    r"t\.me/tonRocketBot\?start=t_[A-Za-z0-9]{15}",
    r"t\.me/CryptoTestnetBot\?start=c_[a-z0-9]{24}",
    r"t\.me/wallet\?start=mci_[A-Za-z0-9]{15}",
    r"t\.me/xrocket\?start=CQ[A-Za-z0-9]{10}",
    r"t\.me/xJetSwapBot\?start=CQ[A-Za-z0-9]{10}"
]

CODE_REGEX = re.compile('|'.join(PATTERNS), re.IGNORECASE)
URL_REGEX = re.compile(r"https://t\.me/\+(\w{12,})")
PUBLIC_REGEX = re.compile(r"https://t\.me/(\w{4,})")

# Боты для мониторинга
MONITOR_CHATS = [
    1622808649,    # CryptoBot
    1559501630,    # @send bot
    1985737506,    # @tonRocketBot
    5014831088,    # @CryptoTestnetBot
    6014729293,    # @wallet
    5794061503,    # @xrocket
    6441848221     # @xJetSwapBot
]

# Очистка текста
SPECIAL_CHARS = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
TRANSLATION = str.maketrans('', '', SPECIAL_CHARS)

# Бот для управления
bot = TelegramClient('lovec_bot', API_ID, API_HASH)

# ========== МЕНЮ ==========
def create_main_menu():
    return [
        [Button.inline("🎯 Статус", b"status")],
        [Button.inline("⚙️ Настройки", b"settings"), Button.inline("📊 Статистика", b"stats")],
        [Button.inline("💰 Вывод", b"withdraw"), Button.inline("🔁 Перезапуск", b"restart")],
        [Button.inline("📋 Сессии", b"sessions"), Button.inline("🆘 Помощь", b"help_menu")]
    ]

def create_status_menu():
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
    return [
        [
            Button.inline(f"{'✅' if storage.config['auto_start'] else '❌'} Автозапуск", b"toggle_auto_start"),
            Button.inline(f"{'✅' if storage.config['notifications'] else '❌'} Уведомления", b"toggle_notifications")
        ],
        [
            Button.inline(f"{'✅' if storage.config['auto_subscribe'] else '❌'} Подписки", b"toggle_auto_subscribe"),
            Button.inline(f"{'✅' if storage.config['solve_captcha'] else '❌'} Капчи", b"toggle_solve_captcha")
        ],
        [
            Button.inline(f"{'✅' if storage.config['safety_enabled'] else '❌'} Безопасность", b"toggle_safety"),
            Button.inline(f"{'✅' if storage.config['auto_withdraw'] else '❌'} Автовывод", b"toggle_auto_withdraw")
        ],
        [
            Button.inline("⚡ Скорость", b"speed_settings"),
            Button.inline("🛡️ Лимиты", b"limits_settings")
        ],
        [Button.inline("🔙 Назад", b"main")]
    ]

def create_speed_menu():
    return [
        [Button.inline("🐢 Медленно (2000мс)", b"speed_2000")],
        [Button.inline("⚡ Средне (1000мс)", b"speed_1000")],
        [Button.inline("🚀 Быстро (500мс)", b"speed_500")],
        [Button.inline("🔙 Назад", b"settings")]
    ]

def create_limits_menu():
    return [
        [Button.inline("🎯 10/мин", b"checks_10")],
        [Button.inline("🎯 20/мин", b"checks_20")],
        [Button.inline("🎯 30/мин", b"checks_30")],
        [Button.inline("🎯 50/мин", b"checks_50")],
        [Button.inline("🔙 Назад", b"settings")]
    ]

def create_numpad():
    return [
        [Button.inline("1", b"1"), Button.inline("2", b"2"), Button.inline("3", b"3")],
        [Button.inline("4", b"4"), Button.inline("5", b"5"), Button.inline("6", b"6")],
        [Button.inline("7", b"7"), Button.inline("8", b"8"), Button.inline("9", b"9")],
        [Button.inline("0", b"0"), Button.inline("⌫", b"del"), Button.inline("✅", b"submit")]
    ]

# ========== OCR ДЛЯ КАПЧИ ==========
async def solve_captcha(image_data):
    """Решает капчу через OCR API"""
    if not storage.config['solve_captcha'] or not OCR_API_KEY:
        return None
    
    try:
        # Конвертируем в base64
        img_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # Используем OCR Space API
        url = "https://api.ocr.space/parse/image"
        payload = {
            'apikey': OCR_API_KEY,
            'base64Image': f'data:image/jpeg;base64,{img_base64}',
            'language': 'eng',
            'isOverlayRequired': False,
            'OCREngine': 2
        }
        
        response = requests.post(url, data=payload, timeout=10)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('ParsedResults'):
                text = result['ParsedResults'][0]['ParsedText'].strip()
                # Извлекаем только цифры
                digits = ''.join(filter(str.isdigit, text))
                if digits:
                    print(f"✅ Капча решена: {digits}")
                    return digits
        
        return None
        
    except Exception as e:
        print(f"❌ Ошибка решения капчи: {e}")
        return None

# ========== СИСТЕМА БЕЗОПАСНОСТИ ==========
class SafetySystem:
    def __init__(self):
        self.action_history = []
    
    async def safe_action(self):
        """Безопасное действие с задержкой"""
        if not storage.config['safety_enabled']:
            return
        
        now = time.time()
        # Очищаем старые записи
        self.action_history = [t for t in self.action_history if now - t < 60]
        
        # Проверяем лимит
        if len(self.action_history) >= storage.config['max_checks']:
            delay = random.uniform(30, 60)
            print(f"⚠️ Лимит чеков, жду {delay:.1f} сек")
            await asyncio.sleep(delay)
            self.action_history.clear()
        
        # Случайная задержка
        delay_ms = storage.config['delay_ms']
        delay = random.uniform(delay_ms * 0.8, delay_ms * 1.2) / 1000
        await asyncio.sleep(delay)
        
        self.action_history.append(now)

safety = SafetySystem()

# ========== КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if event.sender_id != ADMIN_ID:
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **LOVEС CHECK BOT**\n\n"
        f"👑 Админ: {ADMIN_ID}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
        f"💰 Чеков: {checks_activated}\n"
        f"🔗 Сессий: {len(user_sessions)}\n"
        f"🎣 Активных: {len(active_clients)}\n\n"
        f"**Команды:**\n"
        f"• /login - Создать сессию\n"
        f"• /stop - Остановить бота\n"
        f"• /help - Справка",
        buttons=create_main_menu()
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    if ADMIN_ID in user_sessions:
        await event.reply(
            "⚠️ **Сессия уже существует!**\n\n"
            "Для создания новой сессии:\n"
            "1. Нажмите '📋 Сессии'\n"
            "2. Удалите текущую сессию\n"
            "3. Используйте /login снова",
            buttons=create_main_menu()
        )
        return
    
    await event.reply(
        "🔐 **СОЗДАНИЕ СЕССИИ**\n\n"
        "Отправьте номер телефона в формате:\n"
        "+380681234567\n"
        "+79123456789\n\n"
        "Или поделитесь контактом 📱",
        buttons=[[Button.inline("🔙 Назад", b"main")]]
    )
    user_data[ADMIN_ID] = {'state': 'wait_phone'}

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    await event.reply("🛑 Останавливаю бота...")
    
    # Останавливаем всех клиентов
    for user_id, client in list(active_clients.items()):
        try:
            await client.disconnect()
        except:
            pass
    
    try:
        await bot.disconnect()
    except:
        pass
    
    await event.reply("✅ Бот остановлен!")

@bot.on(events.NewMessage(pattern='/help'))
async def help_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    help_text = """
🤖 **LOVEС CHECK BOT - СПРАВКА**

**📋 КОМАНДЫ:**
• /start - Главное меню
• /login - Создать сессию
• /stop - Остановить бота
• /help - Эта справка

**🎯 ФУНКЦИИ:**
• Автоловля чеков из 7+ ботов
• Автоподписка на каналы
• Решение капч (OCR API)
• Автовывод средств
• Система безопасности
• Уведомления в канал
• Поддержка 2FA

**⚙️ БОТЫ:**
• @CryptoBot
• @send
• @tonRocketBot
• @CryptoTestnetBot
• @wallet
• @xrocket
• @xJetSwapBot

**🚀 НАЧАТЬ:**
1. /login - создать сессию
2. Отправить номер телефона
3. Ввести код из Telegram
4. Нажать 'Запустить ловлю'
    """
    
    await event.reply(help_text, buttons=create_main_menu())

# ========== ОБРАБОТЧИК КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    
    if user_id != ADMIN_ID:
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    try:
        data = event.data.decode('utf-8')
        
        # Главное меню
        if data == "main":
            await event.edit(
                f"🤖 **LOVEС CHECK BOT**\n\n"
                f"👑 Админ: {ADMIN_ID}\n"
                f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"🔗 Сессий: {len(user_sessions)}\n"
                f"🎣 Активных: {len(active_clients)}",
                buttons=create_main_menu()
            )
        
        elif data == "status":
            has_session = ADMIN_ID in user_sessions
            is_active = ADMIN_ID in active_clients
            
            if not has_session:
                status_text = "❌ НЕТ СЕССИИ"
                action_btn = [Button.inline("🔐 Создать сессию (/login)", b"create_session")]
            elif not is_active:
                status_text = "⏸️ ГОТОВА"
                action_btn = [Button.inline("🚀 Запустить ловлю", b"start_catching")]
            else:
                status_text = "✅ АКТИВНА"
                action_btn = [Button.inline("🛑 Остановить ловлю", b"stop_catching")]
            
            await event.edit(
                f"🎯 **СТАТУС**\n\n"
                f"🔐 Сессия: {'✅ ЕСТЬ' if has_session else '❌ НЕТ'}\n"
                f"🎣 Ловля: {status_text}\n"
                f"💰 Чеков: {checks_activated}\n"
                f"🛡️ Безопасность: {'✅ ВКЛ' if storage.config['safety_enabled'] else '❌ ВЫКЛ'}\n"
                f"⚡ Задержка: {storage.config['delay_ms']}мс",
                buttons=[action_btn, [Button.inline("🔙 Назад", b"main")]]
            )
        
        elif data == "create_session":
            await event.answer("ℹ️ Используйте команду /login", alert=True)
        
        elif data == "start_catching":
            if ADMIN_ID not in user_sessions:
                await event.answer("❌ Сначала создайте сессию через /login!", alert=True)
                return
            
            if ADMIN_ID in active_clients:
                await event.answer("✅ Уже запущено!", alert=True)
                return
            
            await event.edit("🎯 Запускаю ловлю...")
            asyncio.create_task(start_catching(ADMIN_ID))
            await event.answer("✅ Ловля запущена!", alert=True)
            await asyncio.sleep(1)
            await callback_handler(event)
        
        elif data == "stop_catching":
            if ADMIN_ID in active_clients:
                try:
                    await active_clients[ADMIN_ID].disconnect()
                    del active_clients[ADMIN_ID]
                    await event.edit("🛑 Ловля остановлена!")
                    await event.answer("✅ Остановлено!", alert=True)
                except:
                    await event.answer("⚠️ Ошибка остановки", alert=True)
            else:
                await event.answer("ℹ️ Ловля не запущена", alert=True)
        
        elif data == "settings":
            await event.edit(
                "⚙️ **НАСТРОЙКИ**\n\n"
                f"✅ Автозапуск: {'✅' if storage.config['auto_start'] else '❌'}\n"
                f"🔔 Уведомления: {'✅' if storage.config['notifications'] else '❌'}\n"
                f"📈 Автоподписка: {'✅' if storage.config['auto_subscribe'] else '❌'}\n"
                f"🛡️ Решение капч: {'✅' if storage.config['solve_captcha'] else '❌'}\n"
                f"⚡ Безопасность: {'✅' if storage.config['safety_enabled'] else '❌'}\n"
                f"💰 Автовывод: {'✅' if storage.config['auto_withdraw'] else '❌'}\n"
                f"⏱️ Задержка: {storage.config['delay_ms']}мс\n"
                f"🎯 Лимит: {storage.config['max_checks']}/мин",
                buttons=create_settings_menu()
            )
        
        # Переключение настроек
        elif data.startswith("toggle_"):
            setting = data.replace("toggle_", "")
            if setting in storage.config:
                storage.config[setting] = not storage.config[setting]
                await event.answer(f"✅ {setting}: {'ВКЛ' if storage.config[setting] else 'ВЫКЛ'}", alert=True)
                await callback_handler(event)
        
        # Скорость
        elif data == "speed_settings":
            await event.edit(
                f"⚡ **СКОРОСТЬ**\n\n"
                f"Текущая задержка: {storage.config['delay_ms']}мс\n\n"
                "Выберите скорость:",
                buttons=create_speed_menu()
            )
        
        elif data.startswith("speed_"):
            try:
                speed = int(data.split("_")[1])
                storage.config['delay_ms'] = speed
                await event.answer(f"✅ Задержка: {speed}мс", alert=True)
                await callback_handler(event)
            except:
                await event.answer("❌ Ошибка", alert=True)
        
        # Лимиты
        elif data == "limits_settings":
            await event.edit(
                f"🛡️ **ЛИМИТЫ**\n\n"
                f"Текущий лимит: {storage.config['max_checks']}/мин\n\n"
                "Выберите лимит:",
                buttons=create_limits_menu()
            )
        
        elif data.startswith("checks_"):
            try:
                checks = int(data.split("_")[1])
                storage.config['max_checks'] = checks
                await event.answer(f"✅ Лимит: {checks}/мин", alert=True)
                await callback_handler(event)
            except:
                await event.answer("❌ Ошибка", alert=True)
        
        # Статистика
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
                f"⚡ Задержка: {storage.config['delay_ms']}мс\n"
                f"🛡️ Лимит: {storage.config['max_checks']}/мин",
                buttons=[[Button.inline("🔄 Обновить", b"stats"), Button.inline("🔙 Назад", b"main")]]
            )
        
        # Вывод
        elif data == "withdraw":
            await event.edit(
                "💰 **ВЫВОД СРЕДСТВ**\n\n"
                f"Тег: {WITHDRAW_TAG if WITHDRAW_TAG else '❌ Не установлен'}\n"
                f"Автовывод: {'✅ ВКЛ' if storage.config['auto_withdraw'] else '❌ ВЫКЛ'}\n"
                f"История: {len(withdraw_requests)} записей\n\n"
                "Функции:",
                buttons=[
                    [Button.inline("💸 Вывести сейчас", b"withdraw_now")],
                    [Button.inline("📋 История выводов", b"withdraw_history")],
                    [Button.inline("🔙 Назад", b"main")]
                ]
            )
        
        elif data == "withdraw_now":
            if not WITHDRAW_TAG:
                await event.answer("❌ Установите WITHDRAW_TAG в .env", alert=True)
                return
            await event.answer("ℹ️ Вывод при следующем чеке", alert=True)
        
        elif data == "withdraw_history":
            if not withdraw_requests:
                history = "📭 История пуста"
            else:
                history = "📋 **ИСТОРИЯ ВЫВОДОВ:**\n"
                for i, req in enumerate(withdraw_requests[-5:], 1):
                    history += f"{i}. {req.get('bot', '?')} → {req.get('tag', '?')}\n"
            
            await event.edit(
                f"{history}\n\nВсего: {len(withdraw_requests)}",
                buttons=[[Button.inline("🔙 Назад", b"withdraw")]]
            )
        
        # Сессии
        elif data == "sessions":
            if not user_sessions:
                sessions_text = "❌ Нет сессий"
            else:
                sessions_text = "🔗 **СЕССИИ:**\n\n"
                for uid in user_sessions.keys():
                    sessions_text += f"• ID: {uid}\n"
            
            await event.edit(
                f"{sessions_text}\n\nВсего: {len(user_sessions)}",
                buttons=[
                    [Button.inline("🗑️ Удалить мою", b"delete_my_session")],
                    [Button.inline("🗑️ Удалить все", b"delete_all_sessions")],
                    [Button.inline("🔙 Назад", b"main")]
                ]
            )
        
        elif data == "delete_my_session":
            if ADMIN_ID in user_sessions:
                if ADMIN_ID in active_clients:
                    try:
                        await active_clients[ADMIN_ID].disconnect()
                        del active_clients[ADMIN_ID]
                    except:
                        pass
                del user_sessions[ADMIN_ID]
                await event.answer("✅ Ваша сессия удалена!", alert=True)
            else:
                await event.answer("❌ Нет сессии", alert=True)
        
        elif data == "delete_all_sessions":
            for uid, client in list(active_clients.items()):
                try:
                    await client.disconnect()
                except:
                    pass
            user_sessions.clear()
            await event.answer("✅ Все сессии удалены!", alert=True)
        
        # Перезапуск
        elif data == "restart":
            await event.edit("🔄 Перезапускаю...")
            for uid, client in list(active_clients.items()):
                try:
                    await client.disconnect()
                except:
                    pass
            active_clients.clear()
            await asyncio.sleep(2)
            await event.edit("✅ Перезапущено!", buttons=create_main_menu())
        
        # Помощь
        elif data == "help_menu":
            await event.answer("ℹ️ Отправьте /help", alert=True)
        
        # Цифровая клавиатура
        elif data in "0123456789":
            if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'wait_code':
                code = user_data[ADMIN_ID].get('code', '')
                if len(code) < 10:
                    user_data[ADMIN_ID]['code'] = code + data
                    new_code = user_data[ADMIN_ID]['code']
                    dots = "•" * len(new_code)
                    await event.edit(
                        f"📱 Номер: {user_data[ADMIN_ID].get('phone', '')}\n\n"
                        f"🔢 Код: {dots}\n"
                        f"📝 Цифр: {len(new_code)}\n\n"
                        "Нажмите ✅ когда готово",
                        buttons=create_numpad()
                    )
        
        elif data == "del":
            if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'wait_code':
                code = user_data[ADMIN_ID].get('code', '')
                if code:
                    user_data[ADMIN_ID]['code'] = code[:-1]
                    new_code = user_data[ADMIN_ID]['code']
                    dots = "•" * len(new_code) if new_code else "____"
                    await event.edit(
                        f"📱 Номер: {user_data[ADMIN_ID].get('phone', '')}\n\n"
                        f"🔢 Код: {dots}\n"
                        f"📝 Цифр: {len(new_code)}\n\n"
                        "Нажмите ✅ когда готово",
                        buttons=create_numpad()
                    )
        
        elif data == "submit":
            if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'wait_code':
                code = user_data[ADMIN_ID].get('code', '')
                if len(code) >= 5:
                    await event.answer("🔐 Проверяю код...")
                    await process_telegram_code(ADMIN_ID, code, event)
                else:
                    await event.answer("❌ Минимум 5 цифр!", alert=True)
        
        await event.answer()
        
    except Exception as e:
        print(f"❌ Ошибка кнопки: {e}")
        await event.answer("⚠️ Ошибка обработки", alert=True)

# ========== ОБРАБОТКА СООБЩЕНИЙ ==========
@bot.on(events.NewMessage)
async def message_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    text = event.text.strip()
    
    if text.startswith('/'):
        return
    
    # Ввод номера
    if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'wait_phone':
        if text.startswith('+'):
            phone = text.replace(' ', '')
            await start_telegram_auth(ADMIN_ID, phone, event)
        else:
            await event.reply("❌ Формат: +380681234567")
    
    # Ввод пароля 2FA
    elif ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'wait_password':
        await process_2fa_password(ADMIN_ID, text, event)

@bot.on(events.NewMessage(func=lambda e: e.contact))
async def contact_handler(event):
    if event.sender_id != ADMIN_ID:
        return
    
    if ADMIN_ID in user_data and user_data[ADMIN_ID].get('state') == 'wait_phone':
        contact = event.contact
        if contact.user_id == ADMIN_ID:
            phone = contact.phone_number
            if not phone.startswith('+'):
                phone = '+' + phone
            await start_telegram_auth(ADMIN_ID, phone, event)

# ========== АВТОРИЗАЦИЯ ==========
async def start_telegram_auth(user_id, phone, event=None):
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
            f"📱 Номер: {phone}\n"
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

async def process_telegram_code(user_id, code, event=None):
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
                    f"🆔 ID: {me.id}\n\n"
                    f"🎯 **Готов к работе!**"
                )
                
                await bot.send_message(
                    user_id,
                    success_msg,
                    buttons=[
                        [Button.inline("🚀 Запустить ловлю", b"start_catching")],
                        [Button.inline("🔙 В меню", b"main")]
                    ]
                )
                
                if storage.config['notifications']:
                    try:
                        await bot.send_message(
                            CHANNEL_ID,
                            f"🔐 **НОВАЯ СЕССИЯ**\n\n"
                            f"👤 {me.first_name}\n"
                            f"📱 {me.phone}\n"
                            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                        )
                    except:
                        pass
                
                await client.disconnect()
                del user_data[user_id]
                
            else:
                await bot.send_message(user_id, "❌ Не удалось авторизоваться")
                await client.disconnect()
                
        except SessionPasswordNeededError:
            await bot.send_message(user_id, "🔐 **ТРЕБУЕТСЯ ПАРОЛЬ 2FA**\n\nВведите пароль:")
            user_data[user_id]['state'] = 'wait_password'
                
        except Exception as e:
            error = str(e)
            if "PHONE_CODE_INVALID" in error:
                await bot.send_message(user_id, "❌ Неверный код!")
                user_data[user_id]['code'] = ''
                await bot.send_message(
                    user_id,
                    f"📱 Номер: {phone}\n\n🔢 **Введите код снова:**",
                    buttons=create_numpad()
                )
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error[:100]}")
                await client.disconnect()
                del user_data[user_id]
                
    except Exception as e:
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)[:100]}")

async def process_2fa_password(user_id, password, event):
    try:
        client = user_data[user_id]['client']
        
        await client.sign_in(password=password)
        
        session_string = client.session.save()
        user_sessions[user_id] = session_string
        
        me = await client.get_me()
        
        success_msg = f"✅ **ВХОД С 2FA УСПЕШЕН!**\n\n👤 {me.first_name}\n📱 {me.phone}"
        
        await event.reply(
            success_msg,
            buttons=[
                [Button.inline("🚀 Запустить ловлю", b"start_catching")],
                [Button.inline("🔙 В меню", b"main")]
            ]
        )
        
        if storage.config['notifications']:
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"🔐 **СЕССИЯ С 2FA**\n\n"
                    f"👤 {me.first_name}\n"
                    f"📱 {me.phone}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
        
        await client.disconnect()
        del user_data[user_id]
        
    except Exception as e:
        await event.reply(f"❌ Ошибка пароля: {e}")

# ========== ЛОВЛЯ ЧЕКОВ ==========
async def start_catching(user_id):
    if user_id not in user_sessions:
        print(f"❌ Нет сессии для {user_id}")
        return
    
    try:
        client = TelegramClient(StringSession(user_sessions[user_id]), API_ID, API_HASH)
        await client.start()
        
        me = await client.get_me()
        active_clients[user_id] = client
        
        print(f"✅ Ловля запущена для {me.first_name}")
        
        # Уведомление
        if storage.config['notifications']:
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
            await safety.safe_action()
            
            try:
                text = event.text or ''
                cleaned = text.translate(TRANSLATION)
                
                # Ищем чеки
                for pattern in PATTERNS:
                    matches = re.findall(pattern, cleaned, re.IGNORECASE)
                    for match in matches:
                        if '?start=' in match:
                            code = match.split('?start=')[1]
                            if code not in checks_found:
                                print(f"🎯 Найден чек: {code[:10]}...")
                                checks_found.append(code)
                                
                                # Имя бота
                                bot_name = match.split('t.me/')[1].split('?')[0]
                                
                                # Активируем чек
                                await safety.safe_action()
                                await client.send_message(bot_name, f'/start {code}')
                                
                                global checks_activated
                                checks_activated += 1
                                
                                # Уведомление
                                if storage.config['notifications']:
                                    try:
                                        await bot.send_message(
                                            CHANNEL_ID,
                                            f"💰 **ЧЕК АКТИВИРОВАН!**\n\n"
                                            f"🎯 Код: {code[:10]}...\n"
                                            f"🤖 Бот: @{bot_name}\n"
                                            f"👤 {me.first_name}\n"
                                            f"📊 Всего: {checks_activated}"
                                        )
                                    except:
                                        pass
                                
                                # Автовывод
                                if storage.config['auto_withdraw'] and WITHDRAW_TAG:
                                    await asyncio.sleep(5)
                                    await auto_withdraw(client, bot_name, me.first_name)
                
                # Капчи
                if storage.config['solve_captcha'] and ("captcha" in text.lower() or "капча" in text.lower()):
                    if event.message.photo:
                        try:
                            photo = event.message.photo
                            image_data = await client.download_media(photo, bytes)
                            
                            if image_data:
                                captcha_code = await solve_captcha(image_data)
                                
                                if captcha_code:
                                    await asyncio.sleep(1)
                                    await event.reply(captcha_code)
                                    print(f"✅ Капча решена: {captcha_code}")
                        except Exception as e:
                            print(f"⚠️ Ошибка капчи: {e}")
                
                # Автоподписка
                if storage.config['auto_subscribe'] and event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                url = button.url
                                if not url:
                                    continue
                                
                                await safety.safe_action()
                                
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
                                    print(f"⚠️ Ошибка подписки: {e}")
                                    
            except Exception as e:
                print(f"❌ Ошибка обработки: {e}")
        
        # Бесконечный цикл
        while user_id in active_clients:
            await asyncio.sleep(1)
        
        # Остановка
        await client.disconnect()
        
        if storage.config['notifications']:
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
        print(f"❌ Ошибка ловли: {e}")
        if user_id in active_clients:
            del active_clients[user_id]

async def auto_withdraw(client, bot_name, user_name):
    """Автовывод средств"""
    if not storage.config['auto_withdraw'] or not WITHDRAW_TAG:
        return
    
    try:
        await asyncio.sleep(5)
        
        # Проверяем баланс
        await client.send_message(bot_name, '/balance')
        await asyncio.sleep(3)
        
        # Выводим
        await client.send_message(bot_name, f'/withdraw {WITHDRAW_TAG}')
        print(f"💰 Автовывод на {WITHDRAW_TAG}")
        
        # Сохраняем запрос
        withdraw_requests.append({
            'timestamp': time.time(),
            'user': user_name,
            'bot': bot_name,
            'tag': WITHDRAW_TAG
        })
        
        if storage.config['notifications']:
            try:
                await bot.send_message(
                    CHANNEL_ID,
                    f"💸 **АВТОВЫВОД**\n\n"
                    f"👤 {user_name}\n"
                    f"🤖 @{bot_name}\n"
                    f"🏷️ {WITHDRAW_TAG}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
                
    except Exception as e:
        print(f"⚠️ Ошибка автовывода: {e}")

# ========== ЗАПУСК ==========
async def main():
    print("🚀 Запуск LOVEС CHECK BOT...")
    
    try:
        await bot.start(bot_token=BOT_TOKEN)
        me = await bot.get_me()
        
        print(f"✅ Бот запущен: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        print("=" * 60)
        print("✅ СИСТЕМА ГОТОВА К РАБОТЕ!")
        print("=" * 60)
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **LOVEС CHECK BOT ЗАПУЩЕН!**\n\n"
            f"🔗 Бот: @{me.username}\n"
            f"👑 Админ: {ADMIN_ID}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"**Функции:**\n"
            f"• Ловля чеков из 7+ ботов\n"
            f"• Решение капч (OCR)\n"
            f"• Автовывод средств\n"
            f"• Автоподписка на каналы\n"
            f"• Полное управление через кнопки\n\n"
            f"**Команды:**\n"
            f"• /start - Главное меню\n"
            f"• /login - Создать сессию\n"
            f"• /stop - Остановить бота\n"
            f"• /help - Справка"
        )
        
        print("⏳ Ожидание команд...")
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
    finally:
        print("\n🛑 Завершение работы...")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Остановлено пользователем")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
