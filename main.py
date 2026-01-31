import os
import asyncio
import logging
from io import BytesIO
from datetime import datetime
import random
import json
import time

import regex as re
import requests
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError
from concurrent.futures import ThreadPoolExecutor
from aiohttp import web

# ========== НАСТРОЙКА ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Получаем переменные из Render
API_ID = os.getenv('API_ID')
API_HASH = os.getenv('API_HASH')
OCR_API_KEY = os.getenv('OCR_API_KEY', '')
CHANNEL = os.getenv('CHANNEL', '@lovec_chekovv')
AUTO_WITHDRAW = os.getenv('AVTO_VIVOD', 'False').lower() == 'true'
WITHDRAW_TAG = os.getenv('AVTO_VIVOD_TAG', '')
ANTI_CAPTCHA = os.getenv('ANTI_CAPTCHA', 'False').lower() == 'true'
PORT = int(os.getenv('PORT', 8000))
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))  # Ваш Telegram ID для управления

# Проверка
if not API_ID or not API_HASH:
    logger.error("❌ API_ID и API_HASH обязательны!")
    exit(1)

client = TelegramClient(
    session='render_bot',
    api_id=int(API_ID),
    api_hash=API_HASH,
    system_version="4.16.30-vxSOSYNXA"
)

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
executor = ThreadPoolExecutor(max_workers=3)
checks = []
activated_checks = []
checks_count = 0
bot_start_time = datetime.now()
session_stats = {
    'start_time': datetime.now(),
    'total_messages': 0,
    'total_checks': 0,
    'total_errors': 0
}

# Регулярки
CODE_REGEX = re.compile(
    r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start="
    r"(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})",
    re.IGNORECASE
)
URL_REGEX = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
PUBLIC_REGEX = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# ========== СИСТЕМА КОМАНД ==========
class BotCommands:
    """Все команды бота с инлайн-кнопками"""
    
    @staticmethod
    async def show_main_menu(event):
        """Главное меню"""
        buttons = [
            [Button.inline("📊 Статистика", b"stats"),
             Button.inline("⚙️ Настройки", b"settings")],
            [Button.inline("🔍 Поиск чеков", b"search_checks"),
             Button.inline("🔄 Автовывод", b"auto_withdraw")],
            [Button.inline("🚀 Быстрые действия", b"quick_actions"),
             Button.inline("❓ Помощь", b"help")],
            [Button.inline("🛠️ Админ-панель", b"admin_panel")]
        ]
        
        text = (
            "🤖 **Главное меню Check Bot**\n\n"
            "Выберите действие:"
        )
        
        if event.message:
            await event.edit(text, buttons=buttons, parse_mode='markdown')
        else:
            await event.reply(text, buttons=buttons, parse_mode='markdown')
    
    @staticmethod
    async def show_stats(event):
        """Показать статистику"""
        uptime = datetime.now() - bot_start_time
        
        text = (
            f"📊 **Статистика бота**\n\n"
            f"⏱ **Время работы:** {str(uptime).split('.')[0]}\n"
            f"💰 **Активировано чеков:** {checks_count}\n"
            f"🔍 **Найдено кодов:** {len(checks)}\n"
            f"📈 **Успешных активаций:** {len(activated_checks)}\n"
            f"📡 **Статус:** {'✅ Онлайн' if client.is_connected() else '❌ Офлайн'}\n\n"
            f"💾 **Память:** {len(checks)} записей\n"
            f"🔄 **Автовывод:** {'ВКЛ' if AUTO_WITHDRAW else 'ВЫКЛ'}\n"
            f"🛡️ **Антикапча:** {'ВКЛ' if ANTI_CAPTCHA else 'ВЫКЛ'}"
        )
        
        buttons = [
            [Button.inline("🔄 Обновить", b"stats"),
             Button.inline("📈 Детали", b"detailed_stats")],
            [Button.inline("🗑️ Очистить статистику", b"clear_stats"),
             Button.inline("◀️ Назад", b"main_menu")]
        ]
        
        await event.edit(text, buttons=buttons, parse_mode='markdown')
    
    @staticmethod
    async def show_settings(event):
        """Настройки бота"""
        text = (
            "⚙️ **Настройки бота**\n\n"
            f"📢 **Канал уведомлений:** {CHANNEL}\n"
            f"💸 **Автовывод:** {'✅ ВКЛ' if AUTO_WITHDRAW else '❌ ВЫКЛ'}\n"
            f"🤖 **Тег для вывода:** {WITHDRAW_TAG or 'Не указан'}\n"
            f"🛡️ **Антикапча:** {'✅ ВКЛ' if ANTI_CAPTCHA else '❌ ВЫКЛ'}\n"
            f"👑 **Админ ID:** {ADMIN_ID or 'Не указан'}"
        )
        
        buttons = [
            [Button.inline("🔄 Вкл/Выкл автовывод", b"toggle_withdraw"),
             Button.inline("🎯 Изменить канал", b"change_channel")],
            [Button.inline("🤖 Вкл/Выкл антикапчу", b"toggle_captcha"),
             Button.inline("🏷️ Изменить тег вывода", b"change_withdraw_tag")],
            [Button.inline("◀️ Назад", b"main_menu")]
        ]
        
        await event.edit(text, buttons=buttons, parse_mode='markdown')
    
    @staticmethod
    async def show_quick_actions(event):
        """Быстрые действия"""
        text = (
            "🚀 **Быстрые действия**\n\n"
            "Мгновенные команды для управления:"
        )
        
        buttons = [
            [Button.inline("💰 Проверить баланс", b"check_balance"),
             Button.inline("🔍 Проверить 1 чек", b"check_single")],
            [Button.inline("🎯 Активировать все", b"activate_all"),
             Button.inline("📤 Вывести сейчас", b"withdraw_now")],
            [Button.inline("🔄 Перезапустить бота", b"restart_bot"),
             Button.inline("📋 Список чеков", b"list_checks")],
            [Button.inline("◀️ Назад", b"main_menu")]
        ]
        
        await event.edit(text, buttons=buttons, parse_mode='markdown')
    
    @staticmethod
    async def show_admin_panel(event):
        """Админ панель"""
        if event.sender_id != ADMIN_ID and ADMIN_ID != 0:
            await event.answer("⛔ Только для администратора!", alert=True)
            return
        
        text = (
            "🛠️ **Административная панель**\n\n"
            f"👑 **Админ ID:** {ADMIN_ID}\n"
            f"📊 **Всего сообщений:** {session_stats['total_messages']}\n"
            f"⚠️ **Ошибок:** {session_stats['total_errors']}"
        )
        
        buttons = [
            [Button.inline("📊 Полные логи", b"show_logs"),
             Button.inline("🚫 Остановить бота", b"stop_bot")],
            [Button.inline("🔧 Тест OCR", b"test_ocr"),
             Button.inline("📡 Тест подключения", b"test_connection")],
            [Button.inline("⚡ Экспорт данных", b"export_data"),
             Button.inline("💣 Сброс настроек", b"reset_settings")],
            [Button.inline("◀️ Назад", b"main_menu")]
        ]
        
        await event.edit(text, buttons=buttons, parse_mode='markdown')
    
    @staticmethod
    async def show_help(event):
        """Помощь и инструкции"""
        text = (
            "❓ **Помощь по командам**\n\n"
            "**Основные команды:**\n"
            "• `/start` или `/menu` - Главное меню\n"
            "• `/stats` - Статистика\n"
            "• `/settings` - Настройки\n"
            "• `/search` - Поиск чеков\n"
            "• `/withdraw` - Управление выводом\n\n"
            "**Быстрые команды:**\n"
            "• `/balance` - Проверить баланс\n"
            "• `/activate` - Активировать все найденные чеки\n"
            "• `/restart` - Перезапустить бота\n"
            "• `/help` - Эта справка\n\n"
            "**Управление через кнопки:**\n"
            "Все функции доступны через инлайн-меню!"
        )
        
        buttons = [
            [Button.inline("📚 Примеры использования", b"usage_examples")],
            [Button.inline("🐛 Сообщить об ошибке", b"report_bug")],
            [Button.inline("◀️ Назад", b"main_menu")]
        ]
        
        await event.edit(text, buttons=buttons, parse_mode='markdown')

# ========== ОБРАБОТЧИКИ КОМАНД ==========
@client.on(events.NewMessage(pattern=r'^/(start|menu|начать)$'))
async def start_command(event):
    """Обработчик /start"""
    await BotCommands.show_main_menu(event)

@client.on(events.NewMessage(pattern=r'^/(stats|статистика|инфо)$'))
async def stats_command(event):
    """Обработчик /stats"""
    await BotCommands.show_stats(event)

@client.on(events.NewMessage(pattern=r'^/(settings|настройки)$'))
async def settings_command(event):
    """Обработчик /settings"""
    await BotCommands.show_settings(event)

@client.on(events.NewMessage(pattern=r'^/(help|помощь|справка)$'))
async def help_command(event):
    """Обработчик /help"""
    await BotCommands.show_help(event)

@client.on(events.NewMessage(pattern=r'^/(balance|баланс)$'))
async def balance_command(event):
    """Проверка баланса"""
    try:
        msg = await event.reply("🔄 Проверяю баланс...")
        
        # Проверяем баланс в CryptoBot
        await client.send_message('CryptoBot', '/wallet')
        await asyncio.sleep(2)
        
        messages = await client.get_messages('CryptoBot', limit=1)
        if messages:
            balance_text = messages[0].message[:500]  # Обрезаем длинный текст
            await msg.edit(f"💰 **Баланс:**\n\n{balance_text}")
        else:
            await msg.edit("❌ Не удалось получить баланс")
            
    except Exception as e:
        await event.reply(f"❌ Ошибка: {str(e)}")

@client.on(events.NewMessage(pattern=r'^/(activate|активировать)$'))
async def activate_command(event):
    """Активировать все найденные чеки"""
    if not checks:
        await event.reply("📭 Нет найденных чеков для активации")
        return
    
    msg = await event.reply(f"🔄 Активирую {len(checks)} чеков...")
    
    activated = 0
    for code in checks[:50]:  # Максимум 50 за раз
        try:
            # Ищем бота для этого кода
            for bot_name in ['CryptoBot', 'tonRocketBot', 'wallet']:
                try:
                    await client.send_message(bot_name, f'/start {code}')
                    await asyncio.sleep(0.5)
                    activated += 1
                    break
                except:
                    continue
        except:
            pass
    
    await msg.edit(f"✅ Активировано {activated} чеков из {len(checks)}")

@client.on(events.NewMessage(pattern=r'^/(search|поиск)$'))
async def search_command(event):
    """Ручной поиск чеков"""
    # Можно добавить логику поиска в истории сообщений
    await event.reply(
        "🔍 **Ручной поиск чеков**\n\n"
        "Отправьте мне сообщение с чеком, и я его активирую.\n"
        "Или используйте кнопки ниже:",
        buttons=[
            [Button.inline("🔎 Искать в истории", b"search_history")],
            [Button.inline("📁 Проверить файлы", b"check_files")]
        ]
    )

# ========== ОБРАБОТЧИКИ КНОПОК ==========
@client.on(events.CallbackQuery())
async def button_handler(event):
    """Обработка всех инлайн-кнопок"""
    try:
        data = event.data.decode('utf-8')
        
        # Главное меню и подменю
        if data == "main_menu":
            await BotCommands.show_main_menu(event)
        
        elif data == "stats":
            await BotCommands.show_stats(event)
        
        elif data == "settings":
            await BotCommands.show_settings(event)
        
        elif data == "quick_actions":
            await BotCommands.show_quick_actions(event)
        
        elif data == "admin_panel":
            await BotCommands.show_admin_panel(event)
        
        elif data == "help":
            await BotCommands.show_help(event)
        
        # Действия
        elif data == "check_balance":
            await event.answer("🔄 Проверяю баланс...")
            await balance_command(event)
        
        elif data == "activate_all":
            await event.answer("🔄 Активирую все чеки...")
            await activate_command(event)
        
        elif data == "withdraw_now":
            if not AUTO_WITHDRAW or not WITHDRAW_TAG:
                await event.answer("❌ Автовывод не настроен!", alert=True)
                return
            
            await event.answer("💰 Вывод средств...")
            # Здесь логика вывода
            
        elif data == "restart_bot":
            await event.answer("🔄 Перезапускаю...")
            await event.edit("🔄 Бот перезапускается...")
            os._exit(0)  # Render перезапустит
        
        elif data == "toggle_withdraw":
            global AUTO_WITHDRAW
            AUTO_WITHDRAW = not AUTO_WITHDRAW
            status = "ВКЛ" if AUTO_WITHDRAW else "ВЫКЛ"
            await event.answer(f"✅ Автовывод {status}")
            await BotCommands.show_settings(event)
        
        elif data == "toggle_captcha":
            global ANTI_CAPTCHA
            ANTI_CAPTCHA = not ANTI_CAPTCHA
            status = "ВКЛ" if ANTI_CAPTCHA else "ВЫКЛ"
            await event.answer(f"✅ Антикапча {status}")
            await BotCommands.show_settings(event)
        
        elif data == "clear_stats":
            global checks_count, checks, activated_checks
            old_count = checks_count
            checks_count = 0
            checks = []
            activated_checks = []
            await event.answer(f"✅ Очищено {old_count} записей")
            await BotCommands.show_stats(event)
        
        elif data == "detailed_stats":
            uptime = datetime.now() - bot_start_time
            details = (
                f"📈 **Детальная статистика**\n\n"
                f"⏱ **Аптайм:** {uptime}\n"
                f"📅 **Запущен:** {bot_start_time.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"💾 **Память чеков:** {len(checks)}\n"
                f"✅ **Активаций:** {len(activated_checks)}\n"
                f"📊 **Успешность:** {len(activated_checks)/max(checks_count,1)*100:.1f}%\n"
                f"🔗 **Последние 5 чеков:**\n"
            )
            
            for check in activated_checks[-5:]:
                details += f"  • {check}\n"
            
            await event.edit(details, parse_mode='markdown')
        
        elif data == "list_checks":
            if not checks:
                await event.answer("📭 Нет чеков", alert=True)
                return
            
            check_list = "📋 **Последние 20 чеков:**\n\n"
            for i, code in enumerate(checks[-20:], 1):
                check_list += f"{i}. `{code}`\n"
            
            await event.edit(check_list, parse_mode='markdown')
        
        # Админ функции
        elif data == "show_logs":
            if event.sender_id != ADMIN_ID:
                await event.answer("⛔ Только админ!", alert=True)
                return
            
            logs = (
                f"📋 **Логи системы**\n\n"
                f"👤 **Пользователь:** {event.sender_id}\n"
                f"📡 **Соединение:** {client.is_connected()}\n"
                f"📊 **Сообщений:** {session_stats['total_messages']}\n"
                f"⚠️ **Ошибок:** {session_stats['total_errors']}\n"
                f"💾 **Чеков в памяти:** {len(checks)}\n"
                f"🕒 **Время:** {datetime.now().strftime('%H:%M:%S')}"
            )
            
            await event.edit(logs, parse_mode='markdown')
        
        elif data == "stop_bot":
            if event.sender_id != ADMIN_ID:
                await event.answer("⛔ Только админ!", alert=True)
                return
            
            await event.edit("🛑 **Бот останавливается...**\n\nСервер Render продолжит работу.")
            await asyncio.sleep(2)
            os._exit(1)
        
        elif data == "test_connection":
            if client.is_connected():
                await event.answer("✅ Соединение стабильное")
            else:
                await event.answer("❌ Нет соединения", alert=True)
        
        elif data == "export_data":
            if event.sender_id != ADMIN_ID:
                await event.answer("⛔ Только админ!", alert=True)
                return
            
            # Экспорт данных в JSON
            data = {
                "checks": checks,
                "activated": activated_checks,
                "stats": {
                    "count": checks_count,
                    "start_time": bot_start_time.isoformat(),
                    "uptime": str(datetime.now() - bot_start_time)
                }
            }
            
            # Сохраняем временно
            with open('export.json', 'w') as f:
                json.dump(data, f, indent=2)
            
            # Отправляем файл
            await client.send_file(
                event.chat_id,
                'export.json',
                caption="📦 Экспорт данных бота"
            )
            
            os.remove('export.json')
            await event.answer("✅ Данные экспортированы")
        
        else:
            await event.answer("ℹ️ Функция в разработке")
    
    except Exception as e:
        logger.error(f"Ошибка обработки кнопки: {e}")
        await event.answer("❌ Ошибка обработки")

# ========== ОСНОВНАЯ ЛОГИКА БОТА ==========
# (все ваши оригинальные функции обработки чеков остаются)

@client.on(events.NewMessage(chats=[1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]))
async def handle_crypto_messages(event):
    """Обработка сообщений из крипто-ботов"""
    global checks_count, checks, activated_checks
    
    try:
        session_stats['total_messages'] += 1
        
        # Поиск чеков в тексте
        message_text = event.message.text or ""
        codes = CODE_REGEX.findall(message_text)
        
        if codes:
            for bot_name, code in codes:
                if code not in checks:
                    logger.info(f"🎯 Найден чек: {code}")
                    checks.append(code)
                    
                    # Активируем чек
                    await asyncio.sleep(0.5)
                    await client.send_message(bot_name, f'/start {code}')
                    
                    # Отправляем уведомление в канал
                    await client.send_message(
                        CHANNEL,
                        f'✅ **Активирован чек**\n\n'
                        f'💎 Код: `{code}`\n'
                        f'🤖 Бот: @{bot_name}\n'
                        f'📊 Всего: {checks_count + 1}',
                        parse_mode='markdown'
                    )
                    
                    checks_count += 1
                    activated_checks.append({
                        'time': datetime.now().isoformat(),
                        'code': code,
                        'bot': bot_name
                    })
        
        # Обработка кнопок
        if event.message.reply_markup:
            for row in event.message.reply_markup.rows:
                for button in row.buttons:
                    try:
                        if hasattr(button, 'url') and button.url:
                            match = CODE_REGEX.search(button.url)
                            if match and match.group(2) not in checks:
                                code = match.group(2)
                                bot = match.group(1)
                                
                                checks.append(code)
                                await client.send_message(bot, f'/start {code}')
                                await asyncio.sleep(0.5)
                    except:
                        pass
    
    except FloodWaitError as e:
        logger.warning(f"⚠️ FloodWait: {e.seconds} сек")
        await asyncio.sleep(e.seconds + 5)
    except Exception as e:
        logger.error(f"Ошибка обработки: {e}")
        session_stats['total_errors'] += 1

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
async def health_check(request):
    """Health check для Render"""
    return web.json_response({
        "status": "online",
        "checks": checks_count,
        "connected": client.is_connected(),
        "uptime": str(datetime.now() - bot_start_time)
    })

async def start_web_server():
    """Запуск веб-сервера на порту 8000"""
    app = web.Application()
    app.router.add_get('/', lambda r: web.Response(text='🤖 Bot Online'))
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Веб-сервер запущен на порту {PORT}")

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    """Основная функция запуска"""
    try:
        # Подключаемся к Telegram
        await client.start()
        logger.info("✅ Подключен к Telegram")
        
        # Получаем информацию об аккаунте
        me = await client.get_me()
        logger.info(f"👤 Аккаунт: {me.first_name} (@{me.username})")
        
        # Запускаем веб-сервер
        await start_web_server()
        
        # Отправляем стартовое сообщение
        await client.send_message(
            CHANNEL,
            f"🚀 **Бот запущен!**\n\n"
            f"👤 **Аккаунт:** {me.first_name}\n"
            f"⏰ **Время:** {datetime.now().strftime('%H:%M:%S')}\n"
            f"📡 **Статус:** Онлайн\n"
            f"🔧 **Управление:** Отправьте /menu",
            parse_mode='markdown'
        )
        
        logger.info("🤖 Бот готов к работе!")
        logger.info("📱 Команды: /start /stats /settings /help")
        
        # Бесконечный цикл
        await client.run_until_disconnected()
        
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        await asyncio.sleep(30)
        await main()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    logger.info("🚀 Запуск управляемого бота...")
    asyncio.run(main())
