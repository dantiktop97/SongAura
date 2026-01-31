import os
import asyncio
import time
import random
from io import BytesIO
import regex as re
import requests
from telethon import TelegramClient, events
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from concurrent.futures import ThreadPoolExecutor
from aiohttp import web

# ========== НАСТРОЙКИ ИЗ RENDER ==========
api_id = os.getenv('API_ID')
api_hash = os.getenv('API_HASH')
ocr_api_key = os.getenv('OCR_API_KEY', 'K88206317388957')
channel = os.getenv('CHANNEL', '@lovec_chekovv')
avto_vivod = os.getenv('AVTO_VIVOD', 'False').lower() == 'true'
avto_vivod_tag = os.getenv('AVTO_VIVOD_TAG', '')
anti_captcha = os.getenv('ANTI_CAPTCHA', 'True').lower() == 'true'
PORT = int(os.getenv('PORT', '8000'))

# Проверка обязательных переменных
if not api_id or not api_hash:
    print("❌ ОШИБКА: API_ID и API_HASH обязательны!")
    print("💡 Добавьте в Render Dashboard → Environment")
    exit(1)

# ========== СИСТЕМА ЗАЩИТЫ ==========
class SecuritySystem:
    """Защита от блокировок Telegram"""
    
    def __init__(self):
        self.request_timestamps = []
        self.last_action_time = 0
        self.safety_mode = True
        
    async def safe_delay(self, min_ms=500, max_ms=2000):
        """Случайная задержка между действиями"""
        delay = random.uniform(min_ms/1000, max_ms/1000)
        await asyncio.sleep(delay)
        
    def check_rate_limit(self):
        """Проверка лимита запросов"""
        now = time.time()
        
        # Очищаем старые записи (старше 1 минуты)
        self.request_timestamps = [t for t in self.request_timestamps if now - t < 60]
        
        # Лимит: максимум 20 действий в минуту
        if len(self.request_timestamps) >= 20:
            wait_time = random.randint(30, 60)
            print(f"⚠️ Превышен лимит. Жду {wait_time} сек")
            time.sleep(wait_time)
            self.request_timestamps.clear()
            return False
            
        self.request_timestamps.append(now)
        return True

# Инициализация системы защиты
security = SecuritySystem()

# ========== ТЕЛЕТХОН КЛИЕНТ ==========
client = TelegramClient(
    session='render_session',
    api_id=int(api_id),
    api_hash=api_hash,
    system_version="4.16.30-vxSOSYNXA",
    device_model="Render Server",
    app_version="10.0"
)

# ========== РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ==========
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

replace_chars = ''' @#&+()*"'…;,!№•—–·±<{>}†★‡„"»«»‚‘’‹›¡¿‽~`|√π÷×§∆\\°^%©®™✓₤$₼€₸₾₶฿₳₥₦₫₿¤₲₩₮¥₽₻₷₱₧£₨¢₠₣₢₺₵₡₹₴₯₰₪'''
translation = str.maketrans('', '', replace_chars)

executor = ThreadPoolExecutor(max_workers=3)

# ========== МОНИТОРИТЬ ЭТИ ЧАТЫ ==========
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
checks = []
wallet = []
channels = []
captches = []
checks_count = 0
start_time = time.time()

# ========== OCR ФУНКЦИИ ==========
def ocr_space_sync(file: bytes, overlay=False, language='eng', scale=True, OCREngine=2):
    """Распознавание текста с картинки"""
    if not ocr_api_key:
        return ""
    
    payload = {
        'isOverlayRequired': overlay,
        'apikey': ocr_api_key,
        'language': language,
        'scale': scale,
        'OCREngine': OCREngine
    }
    
    try:
        response = requests.post(
            'https://api.ocr.space/parse/image',
            data=payload,
            files={'filename': ('image.png', file, 'image/png')},
            timeout=10
        )
        result = response.json()
        
        if result.get('ParsedResults'):
            return result.get('ParsedResults')[0].get('ParsedText', '').replace(" ", "")
        return ""
    except Exception as e:
        print(f"❌ Ошибка OCR: {e}")
        return ""

async def ocr_space(file: bytes, overlay=False, language='eng'):
    """Асинхронная обертка для OCR"""
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
                            
                        # Безопасная задержка
                        await security.safe_delay(1000, 3000)
                        
                        result = (await client.inline_query('send', f'{summ} {curency}'))[0]
                        if 'Создать чек' in result.title:
                            await result.click(avto_vivod_tag)
                            print(f"✅ Выведено {summ} {curency} на {avto_vivod_tag}")
                            
                    except Exception as e:
                        print(f"❌ Ошибка вывода: {e}")
    except Exception as e:
        print(f"❌ Ошибка в pay_out: {e}")

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========
@client.on(events.NewMessage(outgoing=True, pattern='.spam'))
async def handler(event):
    """Команда .spam"""
    try:
        chat = event.chat if event.chat else (await event.get_chat())
        args = event.message.message.split(' ')
        
        # Ограничение спама
        count = min(int(args[1]), 10)  # Максимум 10 сообщений
        
        for _ in range(count):
            await client.send_message(chat, args[2])
            await asyncio.sleep(1)  # Задержка между сообщениями
    except Exception as e:
        print(f"❌ Ошибка спама: {e}")

# Обработчик подписок на каналы
@client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать этот чек, так как вы не являетесь подписчиком канала"))
async def handle_new_message(event):
    """Подписка на каналы для активации чеков"""
    global wallet
    code = None
    
    try:
        # Проверяем безопасность
        if not security.check_rate_limit():
            return
        
        for row in event.message.reply_markup.rows:
            for button in row.buttons:
                try:
                    # Ищем код чека
                    check = code_regex.search(button.url)
                    if check:
                        code = check.group(2)
                    
                    # Подписываемся на каналы
                    channel_match = url_regex.search(button.url)
                    public_channel = public_regex.search(button.url)
                    
                    if channel_match:
                        await security.safe_delay(2000, 5000)
                        await client(ImportChatInviteRequest(channel_match.group(1)))
                        print(f"✅ Подписался на приватный канал")
                    
                    if public_channel:
                        await security.safe_delay(2000, 5000)
                        await client(JoinChannelRequest(public_channel.group(1)))
                        print(f"✅ Подписался на публичный канал: {public_channel.group(1)}")
                        
                except Exception as e:
                    print(f"⚠️ Ошибка кнопки: {e}")
    except AttributeError:
        pass
    
    # Активируем чек
    if code and code not in wallet:
        await security.safe_delay(1000, 3000)
        await client.send_message('wallet', message=f'/start {code}')
        wallet.append(code)
        print(f"✅ Активирован чек в wallet: {code[:10]}...")

# Обработчик для tonRocketBot
@client.on(events.NewMessage(chats=[1559501630], pattern="Чтобы"))
async def handle_new_message(event):
    try:
        # Проверяем безопасность
        if not security.check_rate_limit():
            return
            
        for row in event.message.reply_markup.rows:
            for button in row.buttons:
                try:
                    channel_match = url_regex.search(button.url)
                    if channel_match:
                        await security.safe_delay(2000, 5000)
                        await client(ImportChatInviteRequest(channel_match.group(1)))
                except:
                    pass
    except AttributeError:
        pass
    
    await security.safe_delay(1000, 2000)
    await event.message.click(data=b'check-subscribe')

# Обработчик для другого бота
@client.on(events.NewMessage(chats=[5014831088], pattern="Для активации чека"))
async def handle_new_message(event):
    try:
        if not security.check_rate_limit():
            return
            
        for row in event.message.reply_markup.rows:
            for button in row.buttons:
                try:
                    channel_match = url_regex.search(button.url)
                    public_channel = public_regex.search(button.url)
                    
                    if channel_match:
                        await security.safe_delay(2000, 5000)
                        await client(ImportChatInviteRequest(channel_match.group(1)))
                    
                    if public_channel:
                        await security.safe_delay(2000, 5000)
                        await client(JoinChannelRequest(public_channel.group(1)))
                except:
                    pass
    except AttributeError:
        pass
    
    await security.safe_delay(1000, 2000)
    await event.message.click(data=b'Check')

# Универсальный обработчик
@client.on(events.NewMessage(chats=[5794061503]))
async def handle_new_message(event):
    try:
        if not security.check_rate_limit():
            return
            
        for row in event.message.reply_markup.rows:
            for button in row.buttons:
                try:
                    # Активация чеков
                    if hasattr(button, 'data'):
                        try:
                            if button.data.decode().startswith(('showCheque_', 'activateCheque_')):
                                await security.safe_delay(500, 1500)
                                await event.message.click(data=button.data)
                        except:
                            pass
                    
                    # Подписка на каналы
                    channel_match = url_regex.search(button.url)
                    public_channel = public_regex.search(button.url)
                    
                    if channel_match:
                        await security.safe_delay(2000, 5000)
                        await client(ImportChatInviteRequest(channel_match.group(1)))
                    
                    if public_channel:
                        await security.safe_delay(2000, 5000)
                        await client(JoinChannelRequest(public_channel.group(1)))
                        
                except Exception as e:
                    print(f"⚠️ Ошибка обработки: {e}")
    except AttributeError:
        pass

# Функция фильтрации
async def filter(event):
    """Фильтр для успешных активаций"""
    for word in ['Вы получили', 'Вы обналичили чек на сумму:', '✅ Вы получили:', '💰 Вы получили']:
        if word in event.message.text:
            return True
    return False

# Обработчик успешных активаций
@client.on(events.MessageEdited(chats=crypto_black_list, func=filter))
@client.on(events.NewMessage(chats=crypto_black_list, func=filter))
async def handle_success_message(event):
    global checks_count
    
    try:
        entity = await client.get_entity(event.message.peer_id.user_id)
        
        if hasattr(entity, 'usernames') and entity.usernames:
            bot = entity.usernames[0].username
        elif hasattr(entity, 'username'):
            bot = entity.username
        else:
            bot = "Неизвестно"
    except:
        bot = "Неизвестно"
    
    # Извлекаем сумму
    summ = event.raw_text.split('\n')[0]
    summ = summ.replace('Вы получили ', '').replace('✅ Вы получили: ', '').replace('💰 Вы получили ', '').replace('Вы обналичили чек на сумму: ', '')
    
    # Обновляем счетчик
    checks_count += 1
    
    # Отправляем уведомление
    try:
        await client.send_message(
            channel, 
            message=f'✅ Активирован чек на сумму <b>{summ}</b>\n🤖 Бот: <b>@{bot}</b>\n📊 Всего чеков: <b>{checks_count}</b>', 
            parse_mode='HTML'
        )
        print(f"💰 Активирован чек на {summ} от @{bot}")
    except Exception as e:
        print(f"❌ Ошибка отправки уведомления: {e}")

# ОСНОВНОЙ ОБРАБОТЧИК ЧЕКОВ
@client.on(events.MessageEdited(outgoing=False, chats=crypto_black_list, blacklist_chats=True))
@client.on(events.NewMessage(outgoing=False, chats=crypto_black_list, blacklist_chats=True))
async def handle_check_message(event):
    """Основной обработчик чеков"""
    global checks
    
    # Проверяем безопасность
    if not security.check_rate_limit():
        return
    
    try:
        # Очищаем текст от спецсимволов
        message_text = event.message.text.translate(translation)
        
        # Ищем коды чеков
        found_codes = code_regex.findall(message_text)
        
        if found_codes:
            for bot_name, code in found_codes:
                if code not in checks:
                    print(f"🎯 Найден чек: {code} для {bot_name}")
                    
                    # Безопасная задержка
                    await security.safe_delay(500, 2000)
                    
                    # Активируем чек
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
                                print(f"🎯 Найден чек в кнопке: {code}")
                                
                                await security.safe_delay(500, 2000)
                                await client.send_message(match.group(1), message=f'/start {code}')
                                checks.append(code)
                    except AttributeError:
                        pass
                        
    except Exception as e:
        print(f"⚠️ Ошибка обработки сообщения: {e}")

# ОБРАБОТЧИК КАПЧ
if anti_captcha and ocr_api_key:
    @client.on(events.NewMessage(chats=[1559501630], func=lambda e: e.photo))
    async def handle_photo_message(event):
        """Обработка капч"""
        try:
            print("🖼️ Обнаружена каптча...")
            
            # Скачиваем изображение
            photo = await event.download_media(bytes)
            
            # Распознаем текст
            recognized_text = await ocr_space(file=photo)
            
            if recognized_text and recognized_text not in captches:
                print(f"🔤 Распознан текст: {recognized_text}")
                
                # Безопасная задержка
                await security.safe_delay(1000, 3000)
                
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

# ========== ВЕБ-СЕРВЕР ДЛЯ RENDER ==========
async def health_handler(request):
    """Health check для Render"""
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    return web.json_response({
        "status": "online",
        "service": "Lovec Check Bot",
        "url": "https://songaura.onrender.com",
        "checks_activated": checks_count,
        "uptime": f"{hours}h {minutes}m",
        "telegram_connected": client.is_connected(),
        "version": "2.0"
    })

async def start_web_server():
    """Запуск веб-сервера"""
    app = web.Application()
    
    # Маршруты
    app.router.add_get('/', lambda r: web.Response(
        text='<h1>🤖 Lovec Check Bot</h1><p>Status: ONLINE</p><p>URL: https://songaura.onrender.com</p>',
        content_type='text/html'
    ))
    app.router.add_get('/health', health_handler)
    app.router.add_get('/stats', lambda r: web.json_response({
        "checks_count": checks_count,
        "unique_codes": len(checks),
        "wallet_codes": len(wallet),
        "monitoring_chats": len(crypto_black_list)
    }))
    
    # Запускаем сервер
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    
    print(f"🌐 Веб-сервер запущен: https://songaura.onrender.com")
    print(f"📊 Health check: https://songaura.onrender.com/health")

# ========== ГЛАВНАЯ ФУНКЦИЯ ==========
async def main():
    """Основная функция запуска"""
    print("=" * 50)
    print("🚀 LOVEС CHECK BOT для songaura.onrender.com")
    print("=" * 50)
    print(f"🔗 Ваш хостинг: https://songaura.onrender.com")
    print(f"📢 Канал уведомлений: {channel}")
    print(f"🛡️ Защита: ВКЛЮЧЕНА")
    print("=" * 50)
    
    try:
        # Запускаем веб-сервер
        await start_web_server()
        
        # Подключаемся к Telegram
        await client.start()
        print("✅ Подключен к Telegram")
        
        # Подписываемся на канал мониторинга
        try:
            await client(JoinChannelRequest('lovec_checkov'))
            print("✅ Подписан на lovec_checkov")
        except:
            print("⚠️ Не удалось подписаться на lovec_checkov")
        
        # Настраиваем автовывод
        if avto_vivod and avto_vivod_tag:
            try:
                message = await client.send_message(avto_vivod_tag, message='1')
                await client.delete_messages(avto_vivod_tag, message_ids=[message.id])
                asyncio.create_task(pay_out())
                print(f"💰 Автовывод подключен на {avto_vivod_tag}")
            except Exception as e:
                print(f"⚠️ Автовывод: {e}")
        
        # Отправляем стартовое сообщение
        try:
            await client.send_message(
                channel,
                f"🚀 **Бот запущен на songaura.onrender.com!**\n\n"
                f"⏰ Время: {time.strftime('%H:%M:%S')}\n"
                f"🛡️ Защита: ВКЛЮЧЕНА\n"
                f"💰 Автовывод: {'ВКЛ' if avto_vivod else 'ВЫКЛ'}\n"
                f"🤖 Мониторит: {len(crypto_black_list)} ботов\n\n"
                f"🌐 Статус: https://songaura.onrender.com/health",
                parse_mode='markdown'
            )
        except:
            pass
        
        print(f"✅ Бот успешно запущен!")
        print(f"🔍 Мониторит {len(crypto_black_list)} чатов")
        print(f"📊 Статистика: /stats")
        print("=" * 50)
        
        # Бесконечный цикл
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        # Перезапуск через 30 секунд
        await asyncio.sleep(30)
        await main()

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    # Для Render важно правильно запускать
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Фатальная ошибка: {e}")
