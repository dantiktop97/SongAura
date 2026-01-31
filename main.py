#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import json
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from aiohttp import web

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ========== КОНФИГУРАЦИЯ ==========
# Переменные окружения Render
BOT_TOKEN = os.getenv('LOVEC')
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
ADMIN_ID = int(os.getenv('ADMIN_ID', '2936440352'))
CHANNEL = os.getenv('CHANNEL', '@lovec_chekovv')
PORT = int(os.getenv('PORT', '8000'))

# Проверка конфигурации
if not BOT_TOKEN:
    logger.error("❌ ОШИБКА: Переменная LOVEC (токен бота) не установлена!")
    logger.error("💡 Получите токен у @BotFather и добавьте в Render")
    sys.exit(1)

if not API_ID or not API_HASH:
    logger.error("❌ ОШИБКА: API_ID и API_HASH не установлены!")
    logger.error("💡 Получите на my.telegram.org и добавьте в Render")
    sys.exit(1)

logger.info(f"🚀 Запуск Master Bot...")
logger.info(f"👑 Админ ID: {ADMIN_ID}")
logger.info(f"🌐 Канал: {CHANNEL}")

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
try:
    bot = TelegramClient(
        session='bot_manager',
        api_id=int(API_ID),
        api_hash=API_HASH
    ).start(bot_token=BOT_TOKEN)
    logger.info("✅ Бот инициализирован")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    sys.exit(1)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
USER_SESSION_FILE = 'user_session.txt'
CONFIG_FILE = 'bot_config.json'
bot_start_time = datetime.now()
active_session = None
session_creation_data = {}  # Для хранения данных при создании сессии

# ========== МЕНЕДЖЕР ДАННЫХ ==========
class DataManager:
    """Управление файлами данных"""
    
    @staticmethod
    def save_session(session_string: str) -> bool:
        """Сохранить сессию пользователя"""
        try:
            with open(USER_SESSION_FILE, 'w') as f:
                f.write(session_string)
            logger.info("✅ Сессия сохранена в файл")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сессии: {e}")
            return False
    
    @staticmethod
    def load_session() -> str:
        """Загрузить сессию пользователя"""
        try:
            if os.path.exists(USER_SESSION_FILE):
                with open(USER_SESSION_FILE, 'r') as f:
                    session = f.read().strip()
                    if session:
                        logger.info("✅ Сессия загружена из файла")
                        return session
            return ""
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки сессии: {e}")
            return ""
    
    @staticmethod
    def delete_session() -> bool:
        """Удалить сессию"""
        try:
            if os.path.exists(USER_SESSION_FILE):
                os.remove(USER_SESSION_FILE)
                logger.info("🗑️ Сессия удалена")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка удаления сессии: {e}")
            return False
    
    @staticmethod
    def load_config() -> dict:
        """Загрузить конфигурацию"""
        default_config = {
            "auto_withdraw": False,
            "withdraw_tag": "",
            "notifications": True,
            "created_at": datetime.now().isoformat()
        }
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # Обновляем только существующие ключи
                    for key in default_config:
                        if key in config:
                            default_config[key] = config[key]
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки конфига: {e}")
        
        return default_config
    
    @staticmethod
    def save_config(config: dict) -> bool:
        """Сохранить конфигурацию"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            logger.info("✅ Конфигурация сохранена")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфига: {e}")
            return False

# Загружаем конфигурацию
config = DataManager.load_config()

# ========== КОМАНДЫ БОТА ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_command(event):
    """Обработчик команды /start"""
    if event.sender_id != ADMIN_ID:
        await event.reply("⛔ **Доступ запрещен!**\nТолько администратор может использовать этого бота.")
        return
    
    buttons = [
        [Button.inline("🔐 Создать сессию", b"create_session"),
         Button.inline("📊 Статус", b"status")],
        [Button.inline("⚙️ Настройки", b"settings"),
         Button.inline("🗑️ Удалить сессию", b"delete_session")],
        [Button.inline("❓ Помощь", b"help")]
    ]
    
    await event.reply(
        f"🤖 **Master Bot v1.2**\n\n"
        f"👑 **Админ:** `{ADMIN_ID}`\n"
        f"⏰ **Запущен:** {bot_start_time.strftime('%H:%M:%S')}\n"
        f"🌐 **Сервер:** Render\n\n"
        f"**Выберите действие:**",
        buttons=buttons,
        parse_mode='markdown'
    )

@bot.on(events.NewMessage(pattern='/status'))
async def status_command(event):
    """Статус системы"""
    if event.sender_id != ADMIN_ID:
        return
    
    session_exists = os.path.exists(USER_SESSION_FILE)
    uptime = datetime.now() - bot_start_time
    
    text = (
        f"📊 **Статус системы**\n\n"
        f"✅ **Бот:** Работает\n"
        f"⏱ **Аптайм:** {str(uptime).split('.')[0]}\n"
        f"🔐 **Сессия:** {'✅ Сохранена' if session_exists else '❌ Отсутствует'}\n"
        f"📁 **Конфиг:** {'✅ Загружен' if config else '❌ Ошибка'}\n"
        f"🌐 **Порт:** {PORT}\n"
        f"📅 **Время:** {datetime.now().strftime('%H:%M:%S')}"
    )
    
    buttons = [
        [Button.inline("🔄 Обновить", b"status")],
        [Button.inline("◀️ Назад", b"main_menu")]
    ]
    
    await event.reply(text, buttons=buttons, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/help'))
async def help_command(event):
    """Помощь"""
    if event.sender_id != ADMIN_ID:
        return
    
    text = (
        "📚 **Помощь по Master Bot**\n\n"
        "**Основные функции:**\n"
        "• 🔐 Создание и сохранение сессии\n"
        "• ⚙️ Управление настройками\n"
        "• 📊 Мониторинг статуса\n"
        "• 🗑️ Удаление данных\n\n"
        "**Как создать сессию:**\n"
        "1. Нажмите 'Создать сессию'\n"
        "2. Отправьте номер телефона (+79991234567)\n"
        "3. Введите код из Telegram\n"
        "4. Сессия сохранится автоматически\n\n"
        "**Команды:**\n"
        "• `/start` - Главное меню\n"
        "• `/status` - Статус системы\n"
        "• `/help` - Эта справка\n"
        "• `/stop` - Остановить бота\n\n"
        "**Безопасность:**\n"
        "• Все данные хранятся на Render\n"
        "• Доступ только у вас\n"
        "• Сессия защищена"
    )
    
    await event.reply(text, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/stop'))
async def stop_command(event):
    """Безопасная остановка"""
    if event.sender_id != ADMIN_ID:
        return
    
    await event.reply("🛑 **Останавливаю бота...**\n\nRender автоматически перезапустит сервис.")
    
    # Сохраняем конфигурацию
    DataManager.save_config(config)
    
    # Корректное завершение
    await bot.disconnect()
    await asyncio.sleep(1)
    
    logger.info("✅ Бот остановлен по команде админа")
    sys.exit(0)

# ========== ОБРАБОТЧИКИ ИНЛАЙН-КНОПОК ==========
@bot.on(events.CallbackQuery)
async def callback_handler(event):
    """Обработка инлайн-кнопок"""
    if event.sender_id != ADMIN_ID:
        await event.answer("⛔ Доступ только для администратора!", alert=True)
        return
    
    data = event.data.decode('utf-8')
    
    try:
        # Главное меню
        if data == "main_menu":
            await start_command(event)
        
        # Статус
        elif data == "status":
            await status_command(event)
        
        # Настройки
        elif data == "settings":
            session_exists = os.path.exists(USER_SESSION_FILE)
            
            text = (
                f"⚙️ **Настройки бота**\n\n"
                f"🔐 **Сессия:** {'✅ Сохранена' if session_exists else '❌ Отсутствует'}\n"
                f"💰 **Автовывод:** {'✅ ВКЛ' if config.get('auto_withdraw', False) else '❌ ВЫКЛ'}\n"
                f"🏷️ **Тег вывода:** {config.get('withdraw_tag', 'Не указан')}\n"
                f"📢 **Уведомления:** {'✅ ВКЛ' if config.get('notifications', True) else '❌ ВЫКЛ'}\n\n"
                f"**Управление:**"
            )
            
            buttons = [
                [Button.inline("💰 Вкл/Выкл автовывод", b"toggle_withdraw")],
                [Button.inline("📢 Вкл/Выкл уведомления", b"toggle_notify")],
                [Button.inline("💾 Сохранить настройки", b"save_config")],
                [Button.inline("◀️ Назад", b"main_menu")]
            ]
            
            await event.edit(text, buttons=buttons, parse_mode='markdown')
        
        # Создание сессии
        elif data == "create_session":
            # Сохраняем состояние для этого пользователя
            session_creation_data[event.sender_id] = {'step': 'waiting_phone'}
            
            await event.edit(
                "🔐 **Создание новой сессии**\n\n"
                "Отправьте номер телефона в формате:\n"
                "`+79991234567`\n\n"
                "Или нажмите ❌ для отмены:",
                buttons=[Button.inline("❌ Отмена", b"main_menu")],
                parse_mode='markdown'
            )
        
        # Удаление сессии
        elif data == "delete_session":
            if DataManager.delete_session():
                await event.answer("✅ Сессия удалена")
                await event.edit(
                    "🗑️ **Сессия удалена**\n\n"
                    "Все данные пользователя удалены с сервера.",
                    buttons=[Button.inline("◀️ В меню", b"main_menu")]
                )
            else:
                await event.answer("❌ Ошибка удаления", alert=True)
        
        # Переключение автовывода
        elif data == "toggle_withdraw":
            config['auto_withdraw'] = not config.get('auto_withdraw', False)
            status = "ВКЛ" if config['auto_withdraw'] else "ВЫКЛ"
            await event.answer(f"✅ Автовывод {status}")
            await callback_handler(event)  # Обновляем меню
        
        # Переключение уведомлений
        elif data == "toggle_notify":
            config['notifications'] = not config.get('notifications', True)
            status = "ВКЛ" if config['notifications'] else "ВЫКЛ"
            await event.answer(f"✅ Уведомления {status}")
            await callback_handler(event)
        
        # Сохранение конфига
        elif data == "save_config":
            if DataManager.save_config(config):
                await event.answer("✅ Настройки сохранены")
            else:
                await event.answer("❌ Ошибка сохранения", alert=True)
        
        # Помощь
        elif data == "help":
            await help_command(event)
        
        else:
            await event.answer("ℹ️ Команда в разработке")
    
    except Exception as e:
        logger.error(f"Ошибка обработки callback: {e}")
        await event.answer("❌ Ошибка обработки команды")

# ========== ОБРАБОТЧИК СОЗДАНИЯ СЕССИИ ==========
@bot.on(events.NewMessage)
async def session_creation_handler(event):
    """Обработка создания сессии"""
    if event.sender_id != ADMIN_ID:
        return
    
    user_id = event.sender_id
    
    # Проверяем, находится ли пользователь в процессе создания сессии
    if user_id in session_creation_data:
        step = session_creation_data[user_id].get('step')
        text = event.message.text
        
        # Отмена
        if text.lower() == '/cancel' or text == '❌':
            del session_creation_data[user_id]
            await event.reply("❌ Создание сессии отменено.")
            return
        
        # Шаг 1: Ожидание номера телефона
        if step == 'waiting_phone':
            if text.startswith('+') and text[1:].isdigit() and len(text) >= 10:
                # Сохраняем номер
                session_creation_data[user_id]['phone'] = text
                session_creation_data[user_id]['step'] = 'waiting_code'
                
                await event.reply(
                    f"📱 **Номер принят:** {text}\n\n"
                    f"Отправляю код подтверждения...",
                    parse_mode='markdown'
                )
                
                try:
                    # Создаем временного клиента
                    temp_client = TelegramClient(
                        StringSession(),
                        int(API_ID),
                        API_HASH
                    )
                    await temp_client.connect()
                    
                    # Отправляем запрос на код
                    sent_code = await temp_client.send_code_request(text)
                    session_creation_data[user_id]['phone_code_hash'] = sent_code.phone_code_hash
                    session_creation_data[user_id]['temp_client'] = temp_client
                    
                    await event.reply(
                        "✅ **Код отправлен на телефон!**\n\n"
                        "Введите 5-значный код из Telegram:\n"
                        "(например: 12345)\n\n"
                        "Или отправьте /cancel для отмены"
                    )
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки кода: {e}")
                    await event.reply(f"❌ Ошибка: {str(e)}")
                    if user_id in session_creation_data:
                        del session_creation_data[user_id]
            
            else:
                await event.reply("❌ Неверный формат номера. Пример: `+79991234567`", parse_mode='markdown')
        
        # Шаг 2: Ожидание кода
        elif step == 'waiting_code':
            if text.isdigit() and len(text) == 5:
                try:
                    temp_client = session_creation_data[user_id]['temp_client']
                    phone = session_creation_data[user_id]['phone']
                    phone_code_hash = session_creation_data[user_id]['phone_code_hash']
                    
                    # Пытаемся войти с кодом
                    await temp_client.sign_in(
                        phone=phone,
                        code=text,
                        phone_code_hash=phone_code_hash
                    )
                    
                    # Получаем строку сессии
                    session_string = temp_client.session.save()
                    
                    # Сохраняем
                    if DataManager.save_session(session_string):
                        # Получаем информацию о пользователе
                        me = await temp_client.get_me()
                        
                        await event.reply(
                            f"🎉 **Сессия успешно создана!**\n\n"
                            f"👤 **Пользователь:** {me.first_name or 'Неизвестно'}\n"
                            f"📱 **Телефон:** {phone}\n"
                            f"🆔 **ID:** {me.id}\n"
                            f"🔐 **Сессия:** Сохранена на сервере\n\n"
                            f"Теперь вы можете использовать ловца чеков!",
                            parse_mode='markdown'
                        )
                    else:
                        await event.reply("❌ Ошибка сохранения сессии")
                    
                    # Отключаем клиента
                    await temp_client.disconnect()
                    
                    # Очищаем данные
                    del session_creation_data[user_id]
                    
                except Exception as e:
                    logger.error(f"Ошибка входа: {e}")
                    await event.reply(f"❌ Ошибка: {str(e)}")
                    
                    # Очищаем данные при ошибке
                    if user_id in session_creation_data:
                        temp_client = session_creation_data[user_id].get('temp_client')
                        if temp_client:
                            await temp_client.disconnect()
                        del session_creation_data[user_id]
            
            else:
                await event.reply("❌ Код должен быть 5 цифр. Пример: `12345`", parse_mode='markdown')

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
async def health_handler(request):
    """Health check endpoint"""
    return web.json_response({
        "status": "online",
        "service": "Master Bot",
        "uptime": str(datetime.now() - bot_start_time),
        "admin_id": ADMIN_ID,
        "session_exists": os.path.exists(USER_SESSION_FILE)
    })

async def start_web_server():
    """Запуск веб-сервера"""
    try:
        app = web.Application()
        app.router.add_get('/', lambda r: web.Response(
            text='<h1>🤖 Master Bot</h1><p>Status: Online</p><p>Admin: {}</p>'.format(ADMIN_ID),
            content_type='text/html'
        ))
        app.router.add_get('/health', health_handler)
        app.router.add_get('/status', health_handler)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', PORT)
        await site.start()
        
        logger.info(f"🌐 Веб-сервер запущен на порту {PORT}")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка запуска веб-сервера: {e}")
        return False

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    """Основная функция запуска"""
    try:
        logger.info("=" * 50)
        logger.info("🚀 ЗАПУСК MASTER BOT")
        logger.info("=" * 50)
        
        # Запускаем веб-сервер
        web_task = asyncio.create_task(start_web_server())
        
        # Проверяем существующую сессию
        existing_session = DataManager.load_session()
        if existing_session:
            logger.info("✅ Найдена сохраненная сессия пользователя")
        else:
            logger.info("ℹ️ Сессия пользователя не найдена")
        
        # Отправляем уведомление админу
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🤖 **Master Bot запущен!**\n\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"🌐 Сервер: Render\n"
                f"🔐 Сессия: {'✅ Сохранена' if existing_session else '❌ Отсутствует'}\n\n"
                f"Отправьте /start для управления ботом",
                parse_mode='markdown'
            )
            logger.info(f"✅ Приветственное сообщение отправлено админу {ADMIN_ID}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось отправить сообщение админу: {e}")
        
        logger.info("✅ Бот готов к работе!")
        logger.info("💬 Команды: /start, /status, /help, /stop")
        logger.info("=" * 50)
        
        # Ждем завершения
        await asyncio.gather(web_task, bot.run_until_disconnected())
        
    except KeyboardInterrupt:
        logger.info("⏹️ Остановка по запросу пользователя")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
    finally:
        # Корректное завершение
        logger.info("🔄 Завершение работы...")
        try:
            await bot.disconnect()
        except:
            pass
        logger.info("✅ Работа завершена")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Для Render важно правильно обрабатывать event loop
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
    except Exception as e:
        logger.error(f"❌ Фатальная ошибка: {e}")
        sys.exit(1)
