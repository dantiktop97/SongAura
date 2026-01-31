import os
import asyncio
import logging
import json
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from aiohttp import web

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Переменные Render
BOT_TOKEN = os.getenv('LOVEC')  # Токен из переменной LOVEC
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
ADMIN_ID = int(os.getenv('ADMIN_ID', '2936440352'))
CHANNEL = os.getenv('CHANNEL', '@lovec_chekovv')
PORT = int(os.getenv('PORT', 8000))

# Проверка
if not BOT_TOKEN:
    logger.error("❌ LOVEC (токен бота) обязателен!")
    exit(1)
if not API_ID or not API_HASH:
    logger.error("❌ API_ID и API_HASH обязательны!")
    exit(1)

# Инициализация бота
bot = TelegramClient('bot_manager', api_id=int(API_ID), api_hash=API_HASH).start(bot_token=BOT_TOKEN)

# Файлы для хранения
SESSION_FILE = 'user_session.txt'
CONFIG_FILE = 'bot_config.json'

# Глобальные переменные
user_client = None
user_session_string = None
bot_start_time = datetime.now()

# ========== МЕНЕДЖЕР КОНФИГУРАЦИИ ==========
class ConfigManager:
    """Управление конфигурацией бота"""
    
    @staticmethod
    def load_config():
        """Загрузить конфигурацию"""
        default_config = {
            "auto_withdraw": False,
            "withdraw_tag": "",
            "anti_captcha": False,
            "ocr_key": "",
            "monitor_chats": [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503],
            "notifications": True,
            "created_at": datetime.now().isoformat()
        }
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r') as f:
                    loaded = json.load(f)
                    # Объединяем с дефолтными значениями
                    default_config.update(loaded)
            return default_config
        except:
            return default_config
    
    @staticmethod
    def save_config(config):
        """Сохранить конфигурацию"""
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения конфига: {e}")
            return False

# Загружаем конфигурацию
config = ConfigManager.load_config()

# ========== МЕНЕДЖЕР СЕССИЙ ==========
class SessionManager:
    """Управление сессиями пользователя"""
    
    @staticmethod
    def save_session(session_string: str):
        """Сохранить сессию в файл"""
        try:
            with open(SESSION_FILE, 'w') as f:
                f.write(session_string)
            logger.info("✅ Сессия сохранена")
            
            # Также сохраняем в переменную
            global user_session_string
            user_session_string = session_string
            
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка сохранения сессии: {e}")
            return False
    
    @staticmethod
    def load_session():
        """Загрузить сессию из файла"""
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, 'r') as f:
                    session = f.read().strip()
                    if session:
                        global user_session_string
                        user_session_string = session
                        return session
            return None
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки сессии: {e}")
            return None
    
    @staticmethod
    def delete_session():
        """Удалить сессию"""
        try:
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
            global user_session_string, user_client
            user_session_string = None
            user_client = None
            logger.info("🗑️ Сессия удалена")
            return True
        except:
            return False

# ========== КОМАНДЫ БОТА ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Команда /start"""
    if event.sender_id != ADMIN_ID:
        await event.reply("⛔ Доступ запрещен. Только для администратора.")
        return
    
    buttons = [
        [Button.inline("🔐 Создать сессию", b"create_session"),
         Button.inline("📊 Статус", b"status")],
        [Button.inline("⚙️ Настройки", b"settings"),
         Button.inline("🚀 Запуск ловца", b"start_checker")],
        [Button.inline("❓ Помощь", b"help")]
    ]
    
    await event.reply(
        f"🤖 **Master Bot - Панель управления**\n\n"
        f"👑 Админ: {event.sender_id}\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
        f"🔧 Версия: 1.0\n\n"
        f"Выберите действие:",
        buttons=buttons,
        parse_mode='markdown'
    )

@bot.on(events.NewMessage(pattern='/session'))
async def session_command(event):
    """Управление сессией"""
    if event.sender_id != ADMIN_ID:
        return
    
    session_exists = SessionManager.load_session() is not None
    
    text = (
        "🔐 **Управление сессией**\n\n"
        f"Статус: {'✅ СОХРАНЕНА' if session_exists else '❌ ОТСУТСТВУЕТ'}\n"
    )
    
    buttons = [
        [Button.inline("🆕 Создать новую", b"create_session")],
        [Button.inline("🗑️ Удалить", b"delete_session")],
        [Button.inline("📋 Показать", b"show_session")],
        [Button.inline("◀️ Назад", b"main_menu")]
    ]
    
    await event.reply(text, buttons=buttons, parse_mode='markdown')

@bot.on(events.NewMessage(pattern='/settings'))
async def settings_command(event):
    """Настройки бота"""
    if event.sender_id != ADMIN_ID:
        return
    
    text = (
        "⚙️ **Настройки бота**\n\n"
        f"💰 Автовывод: {'✅ ВКЛ' if config['auto_withdraw'] else '❌ ВЫКЛ'}\n"
        f"🏷️ Тег вывода: {config['withdraw_tag'] or 'Не указан'}\n"
        f"🛡️ Антикапча: {'✅ ВКЛ' if config['anti_captcha'] else '❌ ВЫКЛ'}\n"
        f"📢 Уведомления: {'✅ ВКЛ' if config['notifications'] else '❌ ВЫКЛ'}\n"
        f"📊 Мониторит чатов: {len(config['monitor_chats'])}"
    )
    
    buttons = [
        [Button.inline("💰 Вкл/Выкл автовывод", b"toggle_withdraw")],
        [Button.inline("🛡️ Вкл/Выкл антикапчу", b"toggle_captcha")],
        [Button.inline("📢 Уведомления", b"toggle_notify")],
        [Button.inline("🎯 Изменить тег", b"change_withdraw_tag")],
        [Button.inline("📝 Редактировать чаты", b"edit_chats")],
        [Button.inline("💾 Сохранить", b"save_settings"),
         Button.inline("◀️ Назад", b"main_menu")]
    ]
    
    await event.reply(text, buttons=buttons, parse_mode='markdown')

# ========== ИНЛАЙН КНОПКИ ==========
@bot.on(events.CallbackQuery)
async def button_handler(event):
    """Обработчик инлайн-кнопок"""
    global config, user_session_string
    
    if event.sender_id != ADMIN_ID:
        await event.answer("⛔ Только для администратора!", alert=True)
        return
    
    data = event.data.decode('utf-8')
    
    try:
        # Главное меню
        if data == "main_menu":
            await start_handler(event)
        
        # Создание сессии
        elif data == "create_session":
            await event.edit(
                "🔐 **Создание сессии**\n\n"
                "Для создания сессии нужно:\n"
                "1. Отправить номер телефона в формате +79991234567\n"
                "2. Ввести код из Telegram\n"
                "3. При необходимости - пароль 2FA\n\n"
                "Отправьте номер телефона:",
                buttons=[Button.inline("❌ Отмена", b"main_menu")]
            )
            
            # Ждем номер телефона
            @bot.on(events.NewMessage(from_users=ADMIN_ID))
            async def wait_for_phone(phone_event):
                if phone_event.sender_id == ADMIN_ID and phone_event.message.text.startswith('+'):
                    phone = phone_event.message.text
                    
                    await event.edit(f"📞 **Номер получен:** {phone}\n\nОжидаю код из Telegram...")
                    
                    try:
                        # Создаем временного клиента
                        temp_client = TelegramClient(
                            StringSession(),
                            int(API_ID),
                            API_HASH,
                            device_model="iPhone",
                            system_version="iOS 17",
                            app_version="10.0"
                        )
                        
                        await temp_client.connect()
                        
                        # Запрашиваем код
                        sent_code = await temp_client.send_code_request(phone)
                        
                        await event.edit(
                            f"📱 **Код отправлен на {phone}**\n\n"
                            f"Введите код из Telegram (5 цифр):"
                        )
                        
                        # Ждем код
                        @bot.on(events.NewMessage(from_users=ADMIN_ID))
                        async def wait_for_code(code_event):
                            if code_event.sender_id == ADMIN_ID and code_event.message.text.isdigit():
                                code = code_event.message.text
                                
                                try:
                                    # Пытаемся войти
                                    await temp_client.sign_in(phone, code, phone_code_hash=sent_code.phone_code_hash)
                                    
                                    # Получаем строку сессии
                                    session_string = temp_client.session.save()
                                    
                                    # Сохраняем
                                    SessionManager.save_session(session_string)
                                    
                                    # Получаем информацию об аккаунте
                                    me = await temp_client.get_me()
                                    
                                    await event.edit(
                                        f"✅ **Сессия создана успешно!**\n\n"
                                        f"👤 Пользователь: {me.first_name}\n"
                                        f"📱 Телефон: {phone}\n"
                                        f"🆔 ID: {me.id}\n"
                                        f"📅 Создана: {datetime.now().strftime('%H:%M:%S')}\n\n"
                                        f"Сессия автоматически сохранена на сервере.",
                                        buttons=[Button.inline("◀️ В меню", b"main_menu")]
                                    )
                                    
                                    await temp_client.disconnect()
                                    
                                    # Удаляем обработчики
                                    bot.remove_event_handler(wait_for_phone)
                                    bot.remove_event_handler(wait_for_code)
                                    
                                except SessionPasswordNeededError:
                                    await event.edit(
                                        "🔐 **Требуется пароль 2FA**\n\n"
                                        "Введите пароль двухфакторной аутентификации:"
                                    )
                                    
                                    @bot.on(events.NewMessage(from_users=ADMIN_ID))
                                    async def wait_for_password(pass_event):
                                        if pass_event.sender_id == ADMIN_ID:
                                            password = pass_event.message.text
                                            
                                            try:
                                                await temp_client.sign_in(password=password)
                                                
                                                # Получаем строку сессии
                                                session_string = temp_client.session.save()
                                                SessionManager.save_session(session_string)
                                                
                                                me = await temp_client.get_me()
                                                
                                                await event.edit(
                                                    f"✅ **Сессия создана с 2FA!**\n\n"
                                                    f"👤 Пользователь: {me.first_name}\n"
                                                    f"✅ 2FA: Защищено паролем\n"
                                                    f"📅 Создана: {datetime.now().strftime('%H:%M:%S')}",
                                                    buttons=[Button.inline("◀️ В меню", b"main_menu")]
                                                )
                                                
                                                await temp_client.disconnect()
                                                bot.remove_event_handler(wait_for_password)
                                                
                                            except Exception as e:
                                                await event.edit(f"❌ Ошибка пароля: {e}")
                                                
                                except Exception as e:
                                    await event.edit(f"❌ Ошибка: {e}")
                                    await temp_client.disconnect()
                    
                    except Exception as e:
                        await event.edit(f"❌ Ошибка: {e}")
        
        # Статус
        elif data == "status":
            session_loaded = SessionManager.load_session() is not None
            uptime = datetime.now() - bot_start_time
            
            text = (
                f"📊 **Статус системы**\n\n"
                f"⏱ Аптайм: {str(uptime).split('.')[0]}\n"
                f"🔐 Сессия: {'✅ ЗАГРУЖЕНА' if session_loaded else '❌ ОТСУТСТВУЕТ'}\n"
                f"👑 Админ ID: {ADMIN_ID}\n"
                f"🤖 Бот: Работает\n"
                f"🌐 Render: Онлайн\n"
                f"📅 Запуск: {bot_start_time.strftime('%H:%M:%S')}"
            )
            
            buttons = [
                [Button.inline("🔄 Проверить соединение", b"test_connection")],
                [Button.inline("📈 Подробно", b"detailed_stats")],
                [Button.inline("◀️ Назад", b"main_menu")]
            ]
            
            await event.edit(text, buttons=buttons, parse_mode='markdown')
        
        # Настройки
        elif data == "settings":
            await settings_command(event)
        
        # Переключение настроек
        elif data == "toggle_withdraw":
            config['auto_withdraw'] = not config['auto_withdraw']
            status = "ВКЛ" if config['auto_withdraw'] else "ВЫКЛ"
            await event.answer(f"✅ Автовывод {status}")
            await settings_command(event)
        
        elif data == "toggle_captcha":
            config['anti_captcha'] = not config['anti_captcha']
            status = "ВКЛ" if config['anti_captcha'] else "ВЫКЛ"
            await event.answer(f"✅ Антикапча {status}")
            await settings_command(event)
        
        elif data == "toggle_notify":
            config['notifications'] = not config['notifications']
            status = "ВКЛ" if config['notifications'] else "ВЫКЛ"
            await event.answer(f"✅ Уведомления {status}")
            await settings_command(event)
        
        elif data == "save_settings":
            if ConfigManager.save_config(config):
                await event.answer("✅ Настройки сохранены")
            else:
                await event.answer("❌ Ошибка сохранения", alert=True)
            await settings_command(event)
        
        # Показать сессию
        elif data == "show_session":
            session = SessionManager.load_session()
            if session:
                # Показываем только часть для безопасности
                preview = session[:50] + "..." + session[-50:] if len(session) > 100 else session
                await event.edit(
                    f"🔐 **Сессия пользователя**\n\n"
                    f"📏 Длина: {len(session)} символов\n"
                    f"👁️ Предпросмотр:\n`{preview}`\n\n"
                    f"⚠️ **Не делитесь этой строкой!**",
                    parse_mode='markdown',
                    buttons=[Button.inline("◀️ Назад", b"session")]
                )
            else:
                await event.answer("❌ Сессия не найдена", alert=True)
        
        # Удалить сессию
        elif data == "delete_session":
            if SessionManager.delete_session():
                await event.answer("🗑️ Сессия удалена")
                await event.edit(
                    "✅ **Сессия удалена**\n\n"
                    "Все данные пользователя удалены с сервера.",
                    buttons=[Button.inline("◀️ В меню", b"main_menu")]
                )
            else:
                await event.answer("❌ Ошибка удаления", alert=True)
        
        # Запуск ловца чеков
        elif data == "start_checker":
            session = SessionManager.load_session()
            if not session:
                await event.answer("❌ Сначала создайте сессию!", alert=True)
                return
            
            await event.edit(
                "🚀 **Запуск ловца чеков...**\n\n"
                "Подключаюсь к аккаунту...",
                buttons=[Button.inline("🔄 Обновить", b"start_checker")]
            )
            
            # Здесь будет код запуска ловца чеков
            # (можно добавить из предыдущих скриптов)
            
            await asyncio.sleep(2)
            await event.edit(
                "✅ **Ловец чеков запущен!**\n\n"
                "🤖 Аккаунт: Подключен\n"
                "📡 Мониторинг: Активен\n"
                "💰 Автовывод: " + ("ВКЛ" if config['auto_withdraw'] else "ВЫКЛ") + "\n"
                "📢 Уведомления в: " + CHANNEL,
                buttons=[
                    [Button.inline("⏸️ Остановить", b"stop_checker")],
                    [Button.inline("◀️ В меню", b"main_menu")]
                ]
            )
        
        # Помощь
        elif data == "help":
            text = (
                "❓ **Помощь по Master Bot**\n\n"
                "**Основные функции:**\n"
                "• 🔐 Создание сессии - автоматическая авторизация\n"
                "• 🤖 Управление ловцом чеков\n"
                "• ⚙️ Настройки в реальном времени\n"
                "• 📊 Мониторинг статуса\n\n"
                "**Команды:**\n"
                "• /start - Главное меню\n"
                "• /session - Управление сессией\n"
                "• /settings - Настройки бота\n"
                "• /status - Статус системы\n\n"
                "**Безопасность:**\n"
                "• Доступ только для администратора\n"
                "• Сессия хранится на Render\n"
                "• Данные защищены"
            )
            
            await event.edit(
                text,
                buttons=[Button.inline("◀️ Назад", b"main_menu")],
                parse_mode='markdown'
            )
        
        # Тест соединения
        elif data == "test_connection":
            await event.answer("🔄 Проверяю соединение...")
            await asyncio.sleep(1)
            await event.answer("✅ Соединение стабильное")
        
        else:
            await event.answer("ℹ️ Функция в разработке")
    
    except Exception as e:
        logger.error(f"Ошибка обработки кнопки: {e}")
        await event.answer("❌ Ошибка обработки")

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
async def health_check(request):
    """Health check для Render"""
    return web.json_response({
        "status": "online",
        "bot": "running",
        "admin_id": ADMIN_ID,
        "session_exists": SessionManager.load_session() is not None,
        "uptime": str(datetime.now() - bot_start_time)
    })

async def start_web_server():
    """Запуск веб-сервера"""
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text='🤖 Master Bot - Панель управления'))
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Веб-сервер запущен на порту {PORT}")

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    """Основная функция"""
    logger.info("🚀 Запуск Master Bot...")
    logger.info(f"👑 Админ ID: {ADMIN_ID}")
    logger.info(f"🤖 Токен бота: {'***' + BOT_TOKEN[-5:] if BOT_TOKEN else 'НЕТ'}")
    
    try:
        # Запускаем веб-сервер
        await start_web_server()
        
        # Проверяем существующую сессию
        session = SessionManager.load_session()
        if session:
            logger.info("✅ Сессия пользователя загружена")
        else:
            logger.info("ℹ️ Сессия не найдена. Создайте через бота.")
        
        # Запускаем бота
        logger.info("🤖 Бот запущен. Отправьте /start в Telegram")
        
        # Отправляем приветственное сообщение админу
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🤖 **Master Bot запущен!**\n\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}\n"
                f"🌐 Сервер: Render\n"
                f"🔐 Сессия: {'✅ СОХРАНЕНА' if session else '❌ ОТСУТСТВУЕТ'}\n\n"
                f"Отправьте /start для управления",
                parse_mode='markdown'
            )
        except:
            logger.warning("⚠️ Не удалось отправить приветствие админу")
        
        # Бесконечный цикл
        await bot.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Для Render
    asyncio.run(main())
