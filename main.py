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
bot_token = os.getenv('LOVEC', '')
channel = os.getenv('CHANNEL', '-1004902536707')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0'))
OCR_API_KEY = os.getenv('OCR_API_KEY', 'K88206317388957')

print("=" * 60)
print("🤖 LOVEС CHECK BOT - ФИНАЛЬНАЯ ВЕРСИЯ")
print("=" * 60)

# Проверка
if not api_id or not api_hash or not bot_token or not ADMIN_ID:
    print("❌ ОШИБКА: Не все переменные установлены!")
    exit(1)

print(f"✅ API_ID: {api_id}")
print(f"✅ ADMIN_ID: {ADMIN_ID}")
print(f"✅ Номер: +380 68 692 63 71")

# ========== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ==========
user_data = {}
session_strings = {}
checks = []
wallet = []
checks_count = 0
captches = []
active_catchers = {}
code_attempts = {}

# Регулярные выражения
code_regex = re.compile(r"t\.me/(CryptoBot|send|tonRocketBot|CryptoTestnetBot|wallet|xrocket|xJetSwapBot)\?start=(CQ[A-Za-z0-9]{10}|C-[A-Za-z0-9]{10}|t_[A-Za-z0-9]{15}|mci_[A-Za-z0-9]{15}|c_[a-z0-9]{24})", re.IGNORECASE)
url_regex = re.compile(r"https:\/\/t\.me\/\+(\w{12,})")
public_regex = re.compile(r"https:\/\/t\.me\/(\w{4,})")

# Черный список чатов
crypto_black_list = [1622808649, 1559501630, 1985737506, 5014831088, 6014729293, 5794061503]

# Бот для управления
bot = TelegramClient('lovec_bot', api_id, api_hash)

# ========== УЛУЧШЕННАЯ КЛАВИАТУРА ==========
def create_numpad_keyboard(code=""):
    """Создает цифровую клавиатуру"""
    buttons = [
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
            Button.inline("⌫ Удалить", b"num_del"),
            Button.inline("✅ Готово", b"num_done")
        ]
    ]
    return buttons

# ========== ПРОВЕРКА АДМИНА ==========
async def is_admin(user_id):
    return user_id == ADMIN_ID

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    if not await is_admin(event.sender_id):
        await event.reply("🚫 Доступ запрещен!")
        return
    
    await event.reply(
        f"🤖 **Lovec Check Bot**\n\n"
        f"👑 Админ: <code>{ADMIN_ID}</code>\n"
        f"📱 Номер: +380 68 692 63 71\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"🔹 **Команды:**\n"
        f"• /login - Войти в аккаунт\n"
        f"• /quick_login - Быстрый вход\n"
        f"• /status - Статус\n"
        f"• /start_catch - Ловить чеки\n"
        f"• /stop_catch - Стоп\n"
        f"• /stats - Статистика\n\n"
        f"⚠️ Работает только для админа!",
        parse_mode='HTML'
    )

@bot.on(events.NewMessage(pattern='/login'))
async def login_handler(event):
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    # Проверяем существующую сессию
    if user_id in session_strings:
        await event.reply("✅ Сессия уже есть! Используйте /start_catch")
        return
    
    await event.reply(
        "🔑 **Авторизация**\n\n"
        "📱 Ваш номер: `+380 68 692 63 71`\n\n"
        "Нажмите кнопку ниже чтобы запросить код:",
        buttons=[
            [Button.inline("📱 Запросить код", b"request_code")],
            [Button.inline("❌ Отмена", b"cancel_login")]
        ]
    )

@bot.on(events.NewMessage(pattern='/quick_login'))
async def quick_login_handler(event):
    """Быстрый вход с предустановленным номером"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id in session_strings:
        await event.reply("✅ Уже авторизован!")
        return
    
    await event.reply("⏳ Запрашиваю код для +380 68 692 63 71...")
    
    # Создаем клиент
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        await client.connect()
        
        # Запрашиваем код
        sent_code = await client.send_code_request('+380686926371')
        
        # Сохраняем данные
        user_data[user_id] = {
            'state': 'waiting_code',
            'phone': '+380686926371',
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash,
            'code': '',
            'timestamp': time.time()
        }
        
        await event.reply(
            "✅ **Код отправлен!**\n\n"
            "📱 Номер: `+380 68 692 63 71`\n"
            "⏳ Проверьте Telegram или SMS\n\n"
            "Введите код через клавиатуру:",
            buttons=create_numpad_keyboard()
        )
        
    except Exception as e:
        error_msg = str(e)
        await event.reply(f"❌ Ошибка: {error_msg[:100]}")
        if 'client' in locals():
            try:
                await client.disconnect()
            except:
                pass

@bot.on(events.CallbackQuery(data=b'request_code'))
async def request_code_handler(event):
    """Запрос кода"""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    await event.edit("⏳ Запрашиваю код для +380 68 692 63 71...")
    
    # Создаем клиент
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        await client.connect()
        
        # Запрашиваем код
        sent_code = await client.send_code_request('+380686926371')
        
        # Сохраняем данные
        user_data[user_id] = {
            'state': 'waiting_code',
            'phone': '+380686926371',
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash,
            'code': '',
            'timestamp': time.time()
        }
        
        await event.edit(
            "✅ **Код отправлен!**\n\n"
            "📱 Номер: `+380 68 692 63 71`\n"
            "⏳ Проверьте Telegram\n\n"
            "Используйте клавиатуру для ввода кода:",
            buttons=create_numpad_keyboard()
        )
        
    except Exception as e:
        error_msg = str(e)
        await event.edit(f"❌ Ошибка: {error_msg[:100]}")
        if 'client' in locals():
            try:
                await client.disconnect()
            except:
                pass

@bot.on(events.CallbackQuery(data=b'cancel_login'))
async def cancel_login_handler(event):
    """Отмена входа"""
    user_id = event.sender_id
    if user_id in user_data:
        client = user_data[user_id].get('client')
        if client:
            try:
                await client.disconnect()
            except:
                pass
        del user_data[user_id]
    
    await event.edit("❌ Авторизация отменена")

# ========== ОБРАБОТЧИК ЦИФРОВОЙ КЛАВИАТУРЫ ==========
@bot.on(events.CallbackQuery(pattern=b'num_'))
async def numpad_handler(event):
    """Обработка цифровой клавиатуры"""
    user_id = event.sender_id
    
    if not await is_admin(user_id):
        await event.answer("🚫 Доступ запрещен!", alert=True)
        return
    
    if user_id not in user_data or user_data[user_id].get('state') != 'waiting_code':
        await event.answer("❌ Сначала запросите код: /login", alert=True)
        return
    
    action = event.data.decode().split('_')[1]
    current_code = user_data[user_id].get('code', '')
    
    if action == 'del':
        # Удалить последнюю цифру
        if current_code:
            user_data[user_id]['code'] = current_code[:-1]
    
    elif action == 'done':
        # Отправить код
        code = user_data[user_id].get('code', '')
        if len(code) >= 5:
            await event.answer("⌛ Проверяю код...")
            await process_code(user_id, code, event)
        else:
            await event.answer("❌ Нужно минимум 5 цифр!", alert=True)
        return
    
    else:
        # Добавить цифру
        if len(current_code) < 10:
            user_data[user_id]['code'] = current_code + action
    
    # Обновляем сообщение
    new_code = user_data[user_id].get('code', '')
    code_display = new_code if new_code else "______"
    
    await event.edit(
        f"📱 Номер: `+380 68 692 63 71`\n\n"
        f"📝 **Введите код:** `{code_display}`\n\n"
        f"🔢 Цифр введено: {len(new_code)}\n"
        f"✅ Нажмите 'Готово' когда введете все цифры",
        buttons=create_numpad_keyboard()
    )
    
    await event.answer()

async def process_code(user_id, code, event=None):
    """Обработка введенного кода"""
    try:
        if user_id not in user_data:
            await bot.send_message(user_id, "❌ Сессия истекла. /login")
            return
        
        phone = user_data[user_id]['phone']
        phone_code_hash = user_data[user_id]['phone_code_hash']
        client = user_data[user_id]['client']
        
        await bot.send_message(user_id, "🔐 Проверяю код...")
        
        try:
            # Пытаемся войти
            result = await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=phone_code_hash
            )
            
            # Сохраняем сессию
            session_string = client.session.save()
            session_strings[user_id] = session_string
            
            # Получаем информацию
            me = await client.get_me()
            
            await bot.send_message(
                user_id,
                f"✅ **Успешный вход!**\n\n"
                f"👤 Имя: {me.first_name}\n"
                f"📱 Телефон: {me.phone}\n"
                f"🆔 ID: {me.id}\n\n"
                f"🎯 Теперь используйте /start_catch"
            )
            
            # Отправляем в канал
            try:
                await bot.send_message(
                    channel,
                    f"✅ **Новый вход!**\n\n"
                    f"👤 {me.first_name}\n"
                    f"📱 {me.phone}\n"
                    f"⏰ {datetime.now().strftime('%H:%M:%S')}"
                )
            except:
                pass
            
            # Очищаем
            del user_data[user_id]
            await client.disconnect()
            
            if event:
                try:
                    await event.answer("✅ Успешно!", alert=True)
                    await event.delete()
                except:
                    pass
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Ошибка входа: {error_msg}")
            
            if "PHONE_CODE_INVALID" in error_msg:
                await bot.send_message(user_id, "❌ Неверный код! Попробуйте снова:")
                
                # Увеличиваем счетчик попыток
                if user_id not in code_attempts:
                    code_attempts[user_id] = 0
                code_attempts[user_id] += 1
                
                if code_attempts[user_id] >= 3:
                    await bot.send_message(user_id, "🚫 Слишком много попыток. Начните заново: /login")
                    if user_id in user_data:
                        client = user_data[user_id].get('client')
                        if client:
                            await client.disconnect()
                        del user_data[user_id]
                    if user_id in code_attempts:
                        del code_attempts[user_id]
                else:
                    # Показываем клавиатуру снова
                    await bot.send_message(
                        user_id,
                        f"❌ Попытка {code_attempts[user_id]}/3\n"
                        f"Введите код снова:",
                        buttons=create_numpad_keyboard()
                    )
            
            elif "SESSION_PASSWORD_NEEDED" in error_msg:
                await bot.send_message(user_id, "🔐 Нужен пароль 2FA. Введите пароль:")
                user_data[user_id]['state'] = 'waiting_password'
            
            elif "PHONE_CODE_EXPIRED" in error_msg:
                await bot.send_message(user_id, "⏳ Код истек. /login")
                if user_id in user_data:
                    client = user_data[user_id].get('client')
                    if client:
                        await client.disconnect()
                    del user_data[user_id]
            
            else:
                await bot.send_message(user_id, f"❌ Ошибка: {error_msg[:100]}")
    
    except Exception as e:
        await bot.send_message(user_id, f"❌ Ошибка: {e}")

# ========== ОБРАБОТКА ПАРОЛЯ 2FA ==========
@bot.on(events.NewMessage)
async def password_handler(event):
    """Обработка пароля 2FA"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    text = event.text.strip()
    
    if user_id in user_data and user_data[user_id].get('state') == 'waiting_password':
        try:
            client = user_data[user_id]['client']
            
            await client.sign_in(password=text)
            
            # Сохраняем сессию
            session_string = client.session.save()
            session_strings[user_id] = session_string
            
            me = await client.get_me()
            
            await event.reply(
                f"✅ **Вход с 2FA успешен!**\n\n"
                f"👤 {me.first_name}\n"
                f"📱 {me.phone}\n\n"
                f"🎯 Используйте /start_catch"
            )
            
            del user_data[user_id]
            await client.disconnect()
            
        except Exception as e:
            await event.reply(f"❌ Ошибка пароля: {e}")

# ========== ЛОВЛЯ ЧЕКОВ ==========
@bot.on(events.NewMessage(pattern='/start_catch'))
async def start_catch_handler(event):
    """Начать ловлю чеков"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id not in session_strings:
        await event.reply("❌ Сначала войдите: /login")
        return
    
    if user_id in active_catchers:
        await event.reply("✅ Ловля уже идет!")
        return
    
    await event.reply("🎯 Запускаю ловлю чеков...")
    asyncio.create_task(start_catching(user_id))

async def start_catching(user_id):
    """Основная функция ловли"""
    try:
        # Создаем клиента из сессии
        client = TelegramClient(StringSession(session_strings[user_id]), api_id, api_hash)
        await client.start()
        
        me = await client.get_me()
        
        await bot.send_message(
            channel,
            f"🎯 **Ловля начата!**\n\n"
            f"👤 {me.first_name}\n"
            f"📱 {me.phone}\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}"
        )
        
        active_catchers[user_id] = client
        
        # Обработчик чеков
        @client.on(events.NewMessage(chats=crypto_black_list))
        async def check_handler(event):
            try:
                text = event.text or ''
                found_codes = code_regex.findall(text)
                
                if found_codes:
                    for bot_name, code in found_codes:
                        if code not in checks:
                            print(f"🎯 Чек: {code}")
                            await client.send_message(bot_name, f'/start {code}')
                            checks.append(code)
                            
                            global checks_count
                            checks_count += 1
                            
                            # Уведомление
                            await bot.send_message(
                                channel,
                                f"💰 **Новый чек!**\n\n"
                                f"🎯 Код: {code[:10]}...\n"
                                f"🤖 Бот: {bot_name}\n"
                                f"📊 Всего: {checks_count}"
                            )
                
                # Проверяем кнопки
                if event.message.reply_markup:
                    for row in event.message.reply_markup.rows:
                        for button in row.buttons:
                            try:
                                if hasattr(button, 'url'):
                                    match = code_regex.search(button.url)
                                    if match and match.group(2) not in checks:
                                        code = match.group(2)
                                        await client.send_message(match.group(1), f'/start {code}')
                                        checks.append(code)
                                        checks_count += 1
                            except:
                                pass
                                
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")
        
        # Автоподписка
        @client.on(events.NewMessage(chats=[1985737506], pattern="⚠️ Вы не можете активировать"))
        async def subscription_handler(event):
            try:
                for row in event.message.reply_markup.rows:
                    for button in row.buttons:
                        try:
                            channel_match = url_regex.search(button.url)
                            if channel_match:
                                await client(ImportChatInviteRequest(channel_match.group(1)))
                            
                            public_channel = public_regex.search(button.url)
                            if public_channel:
                                await client(JoinChannelRequest(public_channel.group(1)))
                        except:
                            pass
            except:
                pass
        
        print(f"✅ Ловля для {me.first_name}")
        
        # Ждем
        while user_id in active_catchers:
            await asyncio.sleep(1)
        
        await client.disconnect()
        
        await bot.send_message(
            channel,
            f"🛑 **Ловля остановлена**\n\n"
            f"👤 {me.first_name}\n"
            f"📊 Чеков: {checks_count}"
        )
        
    except Exception as e:
        await bot.send_message(
            channel,
            f"❌ **Ошибка ловли**\n\n{e}"
        )

@bot.on(events.NewMessage(pattern='/stop_catch'))
async def stop_catch_handler(event):
    """Остановить ловлю"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    if user_id in active_catchers:
        client = active_catchers[user_id]
        await client.disconnect()
        del active_catchers[user_id]
        await event.reply("🛑 Ловля остановлена")
    else:
        await event.reply("ℹ️ Ловля не запущена")

@bot.on(events.NewMessage(pattern='/status'))
async def status_handler(event):
    """Статус"""
    if not await is_admin(event.sender_id):
        return
    
    user_id = event.sender_id
    
    has_session = user_id in session_strings
    is_catching = user_id in active_catchers
    
    await event.reply(
        f"📊 **Статус**\n\n"
        f"🔐 Сессия: {'✅ Есть' if has_session else '❌ Нет'}\n"
        f"🎣 Ловля: {'✅ ВКЛ' if is_catching else '❌ ВЫКЛ'}\n"
        f"📈 Чеков: {checks_count}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}"
    )

@bot.on(events.NewMessage(pattern='/stats'))
async def stats_handler(event):
    """Статистика"""
    if not await is_admin(event.sender_id):
        return
    
    uptime = time.time() - start_time
    hours = int(uptime // 3600)
    minutes = int((uptime % 3600) // 60)
    
    await event.reply(
        f"📈 **Статистика**\n\n"
        f"⏰ Работает: {hours}ч {minutes}м\n"
        f"🎯 Чеков: {checks_count}\n"
        f"📊 Уникальных: {len(checks)}\n"
        f"🔗 Сессий: {len(session_strings)}\n"
        f"🎣 Ловцов: {len(active_catchers)}\n\n"
        f"🔄 /start - Обновить"
    )

# ========== ЗАПУСК ==========
start_time = time.time()

async def main():
    """Основная функция"""
    print("🚀 Запускаю Lovec Check Bot...")
    
    try:
        await bot.start(bot_token=bot_token)
        me = await bot.get_me()
        
        print(f"✅ Бот: @{me.username}")
        print(f"✅ Админ: {ADMIN_ID}")
        print(f"✅ Номер: +380 68 692 63 71")
        
        await bot.send_message(
            ADMIN_ID,
            f"🤖 **Бот запущен!**\n\n"
            f"🔗 @{me.username}\n"
            f"📱 Номер: +380 68 692 63 71\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"📋 Используйте /quick_login для быстрого входа"
        )
        
        print("=" * 60)
        print("✅ ГОТОВО!")
        print("=" * 60)
        print("📱 Для входа:")
        print("1. Напишите /quick_login")
        print("2. Введите код из Telegram")
        print("3. Напишите /start_catch")
        print("=" * 60)
        
        await bot.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main())
