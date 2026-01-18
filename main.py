#!/usr/bin/env python3
"""
Anony SMS Bot - Ultimate Professional Version v10.0
Полностью рабочий бот с полным функционалом
"""

import os
import sys
import time
import json
import logging
import qrcode
import threading
import hashlib
import re
import random
import string
from datetime import datetime, timedelta
from io import BytesIO
from contextlib import contextmanager
import sqlite3
import requests
from typing import Dict, List, Optional, Any, Tuple

from flask import Flask, request, jsonify
from telebot import TeleBot, types
from telebot.apihelper import ApiException, ApiTelegramException
from PIL import Image, ImageDraw, ImageFont
import html

# ====== КОНФИГУРАЦИЯ ======
TOKEN = os.getenv("PLAY", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7549204023"))
CHANNEL = os.getenv("CHANNEL", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://songaura.onrender.com")
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "data.db")

# Конфигурация безопасности
ANTISPAM_INTERVAL = 2
MAX_REQUESTS_PER_MINUTE = 30
MAX_FILE_SIZE = 50 * 1024 * 1024
MAX_MESSAGE_LENGTH = 4000
SESSION_TIMEOUT = 300

# Модерация
BLACKLIST_WORDS = [
    'спам', 'реклама', 'скам', 'мошенничество', 'обман',
    'взлом', 'хак', 'пароль', 'карта', 'банк', 'кредит',
    'порно', 'порнография', 'нарко', 'drug', 'sex',
    'оскорбление', 'угроза', 'шантаж'
]

# ====== ЛОГГИРОВАНИЕ ======
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ====== ИНИЦИАЛИЗАЦИЯ ======
bot = TeleBot(TOKEN, parse_mode="HTML", num_threads=4)
app = Flask(__name__)

# ====== ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ======
user_sessions = {}
admin_modes = {}
message_cooldown = {}
request_counts = {}
rate_limit_cache = {}
file_cache = {}
session_timestamps = {}

# ====== ПОЛНЫЕ ПЕРЕВОДЫ (РУССКИЙ И АНГЛИЙСКИЙ) ======
TRANSLATIONS = {
    'ru': {
        # Основные команды
        'start': """🎉 <b>Добро пожаловать в Anony SMS!</b> 🎉

Рады видеть тебя 💬✨
Здесь тайны и эмоции превращаются в сообщения 👀💌

<b>🔥 Отправляй и получай абсолютно анонимные сообщения —</b>
никаких имён, только честность, интрига и эмоции 🕶️✨

<b>Хочешь узнать, что о тебе думают друзья?</b>
Получить тайное признание или анонимный комплимент? 😏💖

<b>🔗 Твоя личная ссылка:</b>
<code>{link}</code>

<b>🚀 Поделись ею в чатах или сторис —</b>
и жди анонимные сообщения 💌🤫

<b>Каждое сообщение — маленькая загадка</b> 👀✨

👇 <b>Жми кнопки ниже и погнали!</b> 🚀""",
        
        'start_ref': """🎯 <b>Вы перешли по ссылке пользователя!</b>

Теперь вы можете отправить этому пользователю <b>полностью анонимное сообщение</b>.

💌 <i>Напишите ваше сообщение ниже:</i>

<i>Вы можете отправить:</i>
• Текст ✍️
• Фото 📸
• Видео 🎬
• Голосовое 🎤
• Документ 📎
• Стикер 😜""",
        
        'my_link': """🔗 <b>Ваша уникальная ссылка для анонимок:</b>

<code>{link}</code>

<i>📤 Поделитесь этой ссылкой с друзьями в:</i>
• Чатах 💬
• Социальных сетях 🌐
• Сторис 📲

<i>🎭 Каждый переход — новый анонимный отправитель!
🔥 Чем больше делитесь, тем больше тайн узнаёте 😏</i>""",
        
        'profile': """👤 <b>Ваш профиль</b>

<b>📊 Статистика:</b>
├ Получено сообщений: <b>{received}</b>
├ Отправлено сообщений: <b>{sent}</b>
├ Переходов по ссылке: <b>{clicks}</b>
├ Регистрация: <b>{registered}</b>
└ Последняя активность: <b>{last_active}</b>

<b>⚙️ Настройки:</b>
├ Получение сообщений: {receive_status}
└ Язык: 🇷🇺 Русский""",
        
        'anonymous_message': """📨 <b>У вас новое анонимное сообщение!</b>

💌 <i>Кто-то отправил вам тайное послание...</i>

{message_content}

<i>🔒 Отправитель останется неизвестным...</i>""",
        
        'message_sent': """✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Ваше сообщение доставлено
🔒 Ваша личность скрыта
💌 Получатель не узнает кто вы</i>

<b>Хотите отправить ещё?</b>
Напишите новое сообщение""",
        
        'help': """ℹ️ <b>Полное руководство по Anony SMS</b>

<b>🎯 Что это такое?</b>
Anony SMS — это бот для <b>полностью анонимных</b> сообщений! 
Никто не узнает, кто отправил послание 👻

<b>📨 КАК ПОЛУЧАТЬ сообщения:</b>
1. Нажми «📩 Моя ссылка»
2. Скопируй свою уникальную ссылку
3. Поделись с друзьями
4. Жди анонимные сообщения! 💌

<b>✉️ КАК ОТПРАВЛЯТЬ сообщения:</b>
1. Перейди по чужой ссылке
2. Напиши сообщение
3. Отправь — получатель не узнает твою личность! 🎭

<b>📎 ЧТО МОЖНО ОТПРАВИТЬ:</b>
✅ Текстовые сообщения ✍️
✅ Фотографии 📸
✅ Видео 🎬
✅ Голосовые сообщения 🎤
✅ Стикеры 😜
✅ GIF 🎞️
✅ Документы 📎

<b>⚙️ НАСТРОЙКИ:</b>
• Включить/выключить приём сообщений
• Просмотр статистики
• Генерация QR-кода

<b>🔒 БЕЗОПАСНОСТЬ:</b>
• <b>Полная анонимность</b>
• Конфиденциальность гарантирована 🔐
• Автоматическая модерация
• Защита от спама

<b>🆘 ПОДДЕРЖКА:</b>
Возникли проблемы? Нажми «🆘 Поддержка»""",
        
        'settings': "⚙️ <b>Настройки</b>\n\n<i>Настрой бот под себя:</i>",
        'turn_on': "✅ <b>Приём анонимных сообщений включён!</b>\n\n<i>Теперь друзья могут отправлять тебе тайные послания 🔮</i>",
        'turn_off': "✅ <b>Приём анонимных сообщений отключён!</b>\n\n<i>Ты не будешь получать новые анонимки 🔒\nМожешь включить в любой момент ⚡</i>",
        'language': "🌐 <b>Выберите язык</b>\n\n<i>Выбор языка изменит интерфейс бота.</i>",
        'blocked': "🚫 <b>Вы заблокированы в этом боте.</b>\n\n<i>Если это ошибка, обратитесь в поддержку.</i>",
        'user_not_found': "❌ Пользователь не найден.",
        'messages_disabled': "❌ Этот пользователь отключил получение сообщений.",
        'wait': "⏳ Подождите 2 секунды перед следующим сообщением.",
        'canceled': "❌ Действие отменено",
        'spam_wait': "⏳ Подождите 2 секунды перед следующим сообщением.",
        'qr_code': """📱 <b>Ваш персональный QR-код</b>

<i>Сканируйте и отправляйте анонимные сообщения мгновенно! ⚡</i>

<b>🔗 Ссылка:</b>
<code>{link}</code>""",
        
        # Статистика пользователя
        'user_stats': """📊 <b>Ваша детальная статистика</b>

<b>📈 ОСНОВНЫЕ МЕТРИКИ:</b>
├ 📨 Получено: <b>{received}</b> сообщений
├ 📤 Отправлено: <b>{sent}</b> сообщений
├ 🔗 Переходов: <b>{clicks}</b> раз
└ ⏱️ Сред. ответ: <b>{response_time}</b>

<b>📅 АКТИВНОСТЬ:</b>
├ 📆 Зарегистрирован: <b>{registered}</b>
├ 📅 Последняя активность: <b>{last_active}</b>
└ 🕐 Сред. время в боте: <b>{avg_time}</b> мин/день

<b>📊 ДЕТАЛЬНО:</b>
├ 📈 Активность по часам: {hours_chart}
├ 📅 Активность по дням: {days_chart}
└ 📝 Типы сообщений: {types_chart}

<b>🏆 ДОСТИЖЕНИЯ ({achievements_count}):</b>
{achievements}""",
        
        # Админ
        'admin_panel': "👑 <b>Панель администратора</b>\n\n<i>Доступ к управлению ботом 🔧</i>",
        'admin_stats': """👑 <b>Статистика бота</b>

<b>📊 ОСНОВНЫЕ МЕТРИКИ:</b>
├ Всего пользователей: <b>{total_users}</b>
├ Активных сегодня: <b>{today_active}</b>
├ Всего сообщений: <b>{total_messages}</b>
├ Сообщений за 24ч: <b>{messages_24h}</b>
├ Новых за 24ч: <b>{new_users_24h}</b>
├ Заблокированных: <b>{blocked_users}</b>
├ Открытых тикетов: <b>{open_tickets}</b>
└ Сред. активность в час: <b>{avg_hourly}</b>

<b>📈 ДЕТАЛЬНАЯ СТАТИСТИКА:</b>
├ Пользователей за неделю: <b>{users_week}</b>
├ Сообщений за неделю: <b>{messages_week}</b>
├ Активных за неделю: <b>{active_week}</b>
├ Удерживание (30 дней): <b>{retention_30d}%</b>
└ Конверсия в сообщения: <b>{conversion_rate}%</b>""",
        
        'broadcast_start': """📢 <b>Создание рассылки</b>

<i>Отправьте сообщение которое будет отправлено всем пользователям.</i>

<b>📎 Можно отправить:</b>
• Текст с HTML-разметкой ✍️
• Фото с подписью 📸
• Видео с описанием 🎬
• Документ с комментарием 📎
• Стикер 😜""",
        
        'broadcast_progress': "⏳ <b>Начинаю рассылку...</b>\n\nВсего пользователей: {total}",
        'broadcast_result': """✅ <b>Рассылка завершена!</b>

<b>📊 РЕЗУЛЬТАТЫ:</b>
├ Всего пользователей: <b>{total}</b>
├ Успешно отправлено: <b>{sent}</b>
├ Не удалось отправить: <b>{failed}</b>
└ Пропущено (заблок.): <b>{blocked}</b>""",
        
        'users_management': "👥 <b>Управление пользователями</b>\n\n<i>Поиск и управление пользователями бота 🔧</i>",
        
        'find_user': "🔍 <b>Поиск пользователя</b>\n\n<i>Введите ID пользователя или юзернейм (без @):</i>",
        'user_info': """🔍 <b>ИНФОРМАЦИЯ О ПОЛЬЗОВАТЕЛЕ</b>

<b>👤 ОСНОВНЫЕ ДАННЫЕ:</b>
├ ID: <code>{user_id}</code>
├ Имя: <b>{first_name}</b>
├ Юзернейм: {username}
├ Зарегистрирован: {registered}
└ Последняя активность: {last_active}

<b>📊 СТАТИСТИКА:</b>
├ 📨 Получено: <b>{received}</b>
├ 📤 Отправлено: <b>{sent}</b>
├ 🔗 Переходов: <b>{clicks}</b>
└ ⚙️ Приём сообщений: {receive_status}

<b>🚫 СТАТУС:</b> {block_status}""",
        
        'logs': "📋 <b>Логи сообщений</b>",
        'no_logs': "📋 <b>Логи сообщений пусты</b>\n\n<i>Пока нет отправленных сообщений.</i>",
        'tickets': "🆘 <b>Открытые тикеты</b>",
        'no_tickets': "🆘 <b>Открытых тикетов нет</b>\n\n<i>Все обращения обработаны ✅</i>",
        'admin_settings': """⚙️ <b>Настройки администратора</b>

<b>🔔 УВЕДОМЛЕНИЯ:</b>
├ Новые сообщения: {notifications}
└ В канал: {channel_status}

<b>⚡ ПРОИЗВОДИТЕЛЬНОСТЬ:</b>
├ Антиспам: {antispam} сек.
└ База данных: ✅ Работает""",
        
        'direct_message': """✉️ <b>Отправьте сообщение для пользователя</b> <code>{user_id}</code>

<i>Сообщение придёт как от бота 🤖
Можно отправить текст, фото или видео.</i>""",
        
        'message_sent_admin': """✅ <b>Сообщение отправлено</b>

👤 Пользователь: <code>{user_id}</code>
📝 Тип: {message_type}""",
        
        'block_user': "✅ Пользователь <code>{user_id}</code> заблокирован.",
        'unblock_user': "✅ Пользователь <code>{user_id}</code> разблокирован.",
        'user_blocked': "🚫 <b>Пользователь заблокирован</b>",
        'user_already_blocked': "✅ Пользователь уже заблокирован",
        'user_not_blocked': "✅ Пользователь не заблокирован",
        
        # Новые переводы
        'main_menu': "🏠 Главное меню",
        'just_now': "только что",
        'minutes_ago': "{minutes} минут назад",
        'hours_ago': "{hours} часов назад",
        'yesterday': "вчера",
        'days_ago': "{days} дней назад",
        'never': "никогда",
        'language_changed': "✅ Язык изменен",
        'send_anonymous_to': "Отправьте анонимное сообщение",
        'send_anonymous_description': "Напишите сообщение, фото, видео или голосовое сообщение",
        'send_reply': "Отправьте ответное сообщение",
        'reply_to_ticket': "Ответить на тикет",
        'user_blocked_bot': "❌ Пользователь заблокировал бота",
        'text': "Текст",
        
        # Кнопки
        'btn_my_link': "📩 Моя ссылка",
        'btn_profile': "👤 Профиль",
        'btn_stats': "📊 Статистика",
        'btn_settings': "⚙️ Настройки",
        'btn_qr': "📱 QR-код",
        'btn_help': "ℹ️ Помощь",
        'btn_support': "🆘 Поддержка",
        'btn_admin': "👑 Админ",
        'btn_turn_on': "🔔 Вкл. сообщения",
        'btn_turn_off': "🔕 Выкл. сообщения",
        'btn_language': "🌐 Язык",
        'btn_back': "⬅️ Назад",
        'btn_cancel': "❌ Отмена",
        'btn_history': "📜 История",
        
        'btn_admin_stats': "📊 Статистика",
        'btn_admin_broadcast': "📢 Рассылка",
        'btn_admin_manage_users': "👥 Управление",
        'btn_admin_find': "🔍 Найти",
        'btn_admin_logs': "📋 Логи",
        'btn_admin_tickets': "🆘 Тикеты",
        'btn_admin_settings': "⚙️ Настройки",
        'btn_admin_block': "🚫 Блок/Разблок",
        'btn_admin_backup': "💾 Бэкап",
        'btn_admin_export': "📤 Экспорт",
        
        'btn_reply': "💌 Ответить",
        'btn_ignore': "🚫 Игнор",
        'btn_block': "🚫 Заблокировать",
        'btn_unblock': "✅ Разблокировать",
        'btn_message': "✉️ Написать ему",
        'btn_refresh': "🔄 Обновить",
        'btn_toggle_text': "🔕 Скрыть текст",
        'btn_show_text': "🔔 Показать текст",
        'btn_reply_ticket': "📝 Ответить",
        'btn_close_ticket': "✅ Закрыть",
        
        # Поддержка
        'support': """🆘 <b>Служба поддержки</b>

<i>Опишите вашу проблему как можно подробнее 💭
Мы постараемся ответить в кратчайшие сроки ⏰</i>

<b>📎 Что можно отправить:</b>
• Текстовое описание проблемы ✍️
• Скриншот ошибки 📸
• Видео с багом 🎬
• Любой медиафайл 📎""",
        
        'support_sent': """✅ <b>Запрос в поддержку отправлен!</b>

<i>Ваш тикет: <b>#{ticket_id}</b>
Мы ответим вам в ближайшее время ⏰</i>""",
        
        # История
        'history': "📜 <b>История сообщений</b>\n\n<i>Последние 20 сообщений:</i>",
        'history_empty': "📜 <b>У вас пока нет сообщений</b>\n\n<i>Начните общение, отправив первую анонимку!</i>",
        'history_item': """<b>{index}. {direction} {name}</b> <i>({time})</i>
💬 <i>{preview}</i>""",
        'history_incoming': "⬇️ От",
        'history_outgoing': "⬆️ Кому",
        
        # Блокировка
        'block_instruction': "🚫 <b>Блокировка/Разблокировка пользователя</b>\n\nВведите ID пользователя или юзернейм (без @):",
        'block_success': "✅ Пользователь <code>{user_id}</code> заблокирован.",
        'unblock_success': "✅ Пользователь <code>{user_id}</code> разблокирован.",
        'block_already': "✅ Пользователь уже заблокирован.",
        'user_not_blocked_msg': "✅ Пользователь не был заблокирован.",
        
        # Ошибки
        'file_too_large': "❌ Файл слишком большой (максимум {max_size}MB).",
        'message_too_long': "❌ Сообщение слишком длинное (максимум {max_length} символов).",
        'rate_limit_exceeded': "⏳ Слишком много запросов. Подождите {seconds} секунд.",
        'content_blocked': "❌ Сообщение содержит запрещённые слова.",
        'session_expired': "⏰ Сессия истекла. Начните заново.",
        
        # Экспорт
        'export_instruction': "📤 <b>Экспорт данных</b>\n\n<i>Выберите что экспортировать:</i>",
        'export_users': "👥 Экспорт пользователей",
        'export_messages': "📨 Экспорт сообщений",
        'export_stats': "📊 Экспорт статистики",
        'export_processing': "⏳ <b>Экспорт данных...</b>\n\n<i>Пожалуйста, подождите.</i>",
        'export_complete': "✅ <b>Экспорт завершен!</b>\n\n<i>Данные успешно сохранены.</i>",
        
        # Системные
        'system_error': "❌ Произошла системная ошибка. Пожалуйста, попробуйте позже.",
        'maintenance': "🔧 Бот находится на техническом обслуживании. Приносим извинения за неудобства.",
    },
    
    'en': {
        # Main commands
        'start': """🎉 <b>Welcome to Anony SMS!</b> 🎉

Glad to see you 💬✨
Here secrets and emotions turn into messages 👀💌

<b>🔥 Send and receive completely anonymous messages —</b>
no names, just honesty, intrigue and emotions 🕶️✨

<b>Want to know what your friends think about you?</b>
Get a secret confession or anonymous compliment? 😏💖

<b>🔗 Your personal link:</b>
<code>{link}</code>

<b>🚀 Share it in chats or stories —</b>
and wait for anonymous messages 💌🤫

<b>Every message is a little mystery</b> 👀✨

👇 <b>Click the buttons below and let's go!</b> 🚀""",
        
        'start_ref': """🎯 <b>You followed a user's link!</b>

Now you can send this user a <b>completely anonymous message</b>.

💌 <i>Write your message below:</i>

<i>You can send:</i>
• Text ✍️
• Photo 📸
• Video 🎬
• Voice message 🎤
• Document 📎
• Sticker 😜""",
        
        'my_link': """🔗 <b>Your unique link for anonymous messages:</b>

<code>{link}</code>

<i>📤 Share with friends in:</i>
• Chats 💬
• Social networks 🌐
• Stories 📲

<i>🎭 Every click — a new anonymous sender!
🔥 The more you share, the more secrets you discover 😏</i>""",
        
        'profile': """👤 <b>Your Profile</b>

<b>📊 Statistics:</b>
├ Messages received: <b>{received}</b>
├ Messages sent: <b>{sent}</b>
├ Link clicks: <b>{clicks}</b>
├ Registered: <b>{registered}</b>
└ Last active: <b>{last_active}</b>

<b>⚙️ Settings:</b>
├ Receive messages: {receive_status}
└ Language: 🇺🇸 English""",
        
        'anonymous_message': """📨 <b>You have a new anonymous message!</b>

💌 <i>Someone sent you a secret message...</i>

{message_content}

<i>🔒 The sender will remain unknown...</i>""",
        
        'message_sent': """✅ <b>Message sent anonymously!</b>

<i>🎯 Your message delivered
🔒 Your identity hidden
💌 Recipient won't know who you are</i>

<b>Want to send more?</b>
Write a new message""",
        
        'help': """ℹ️ <b>Complete Anony SMS Guide</b>

<b>🎯 What is it?</b>
Anony SMS is a bot for <b>completely anonymous</b> messages!
No one will know who sent the message 👻

<b>📨 HOW TO RECEIVE messages:</b>
1. Click "📩 My link"
2. Copy your unique link
3. Share with friends
4. Wait for anonymous messages! 💌

<b>✉️ HOW TO SEND messages:</b>
1. Follow someone's link
2. Write a message
3. Send — the recipient won't know your identity! 🎭

<b>📎 WHAT CAN BE SENT:</b>
✅ Text messages ✍️
✅ Photos 📸
✅ Videos 🎬
✅ Voice messages 🎤
✅ Stickers 😜
✅ GIFs 🎞️
✅ Documents 📎

<b>⚙️ SETTINGS:</b>
• Enable/disable message reception
• View statistics
• Generate QR code

<b>🔒 SECURITY:</b>
• <b>Complete anonymity</b>
• Confidentiality guaranteed 🔐
• Automatic moderation
• Spam protection

<b>🆘 SUPPORT:</b>
Having problems? Click "🆘 Support" """,
        
        'settings': "⚙️ <b>Settings</b>\n\n<i>Customize the bot for yourself:</i>",
        'turn_on': "✅ <b>Anonymous message reception enabled!</b>\n\n<i>Now friends can send you secret messages 🔮</i>",
        'turn_off': "✅ <b>Anonymous message reception disabled!</b>\n\n<i>You won't receive new anonymous messages 🔒\nYou can enable it at any time ⚡</i>",
        'language': "🌐 <b>Choose language</b>\n\n<i>Language selection will change the bot interface.</i>",
        'blocked': "🚫 <b>You are blocked in this bot.</b>\n\n<i>If this is an error, please contact support.</i>",
        'user_not_found': "❌ User not found.",
        'messages_disabled': "❌ This user has disabled message reception.",
        'wait': "⏳ Wait 2 seconds before the next message.",
        'canceled': "❌ Action canceled",
        'spam_wait': "⏳ Wait 2 seconds before the next message.",
        'qr_code': """📱 <b>Your personal QR code</b>

<i>Scan and send anonymous messages instantly! ⚡</i>

<b>🔗 Link:</b>
<code>{link}</code>""",
        
        # User statistics
        'user_stats': """📊 <b>Your detailed statistics</b>

<b>📈 MAIN METRICS:</b>
├ 📨 Received: <b>{received}</b> messages
├ 📤 Sent: <b>{sent}</b> messages
├ 🔗 Clicks: <b>{clicks}</b> times
└ ⏱️ Avg. response: <b>{response_time}</b>

<b>📅 ACTIVITY:</b>
├ 📆 Registered: <b>{registered}</b>
├ 📅 Last activity: <b>{last_active}</b>
└ 🕐 Avg. time in bot: <b>{avg_time}</b> min/day

<b>📊 DETAILED:</b>
├ 📈 Activity by hour: {hours_chart}
├ 📅 Activity by day: {days_chart}
└ 📝 Message types: {types_chart}

<b>🏆 ACHIEVEMENTS ({achievements_count}):</b>
{achievements}""",
        
        # Admin
        'admin_panel': "👑 <b>Administrator Panel</b>\n\n<i>Access to bot management 🔧</i>",
        'admin_stats': """👑 <b>Bot Statistics</b>

<b>📊 MAIN METRICS:</b>
├ Total users: <b>{total_users}</b>
├ Active today: <b>{today_active}</b>
├ Total messages: <b>{total_messages}</b>
├ Messages in 24h: <b>{messages_24h}</b>
├ New in 24h: <b>{new_users_24h}</b>
├ Blocked: <b>{blocked_users}</b>
├ Open tickets: <b>{open_tickets}</b>
└ Avg. activity per hour: <b>{avg_hourly}</b>

<b>📈 DETAILED STATISTICS:</b>
├ Users this week: <b>{users_week}</b>
├ Messages this week: <b>{messages_week}</b>
├ Active this week: <b>{active_week}</b>
├ Retention (30 days): <b>{retention_30d}%</b>
└ Conversion to messages: <b>{conversion_rate}%</b>""",
        
        'broadcast_start': """📢 <b>Create Broadcast</b>

<i>Send a message that will be sent to all users.</i>

<b>📎 Can send:</b>
• Text with HTML markup ✍️
• Photo with caption 📸
• Video with description 🎬
• Document with comment 📎
• Sticker 😜""",
        
        'broadcast_progress': "⏳ <b>Starting broadcast...</b>\n\nTotal users: {total}",
        'broadcast_result': """✅ <b>Broadcast completed!</b>

<b>📊 RESULTS:</b>
├ Total users: <b>{total}</b>
├ Successfully sent: <b>{sent}</b>
├ Failed to send: <b>{failed}</b>
└ Skipped (blocked): <b>{blocked}</b>""",
        
        'users_management': "👥 <b>User Management</b>\n\n<i>Search and manage bot users 🔧</i>",
        
        'find_user': "🔍 <b>Find user</b>\n\n<i>Enter user ID or username (without @):</i>",
        'user_info': """🔍 <b>USER INFORMATION</b>

<b>👤 BASIC DATA:</b>
├ ID: <code>{user_id}</code>
├ Name: <b>{first_name}</b>
├ Username: {username}
├ Registered: {registered}
└ Last activity: {last_active}

<b>📊 STATISTICS:</b>
├ 📨 Received: <b>{received}</b>
├ 📤 Sent: <b>{sent}</b>
├ 🔗 Clicks: <b>{clicks}</b>
└ ⚙️ Receive messages: {receive_status}

<b>🚫 STATUS:</b> {block_status}""",
        
        'logs': "📋 <b>Message logs</b>",
        'no_logs': "📋 <b>Message logs are empty</b>\n\n<i>No messages sent yet.</i>",
        'tickets': "🆘 <b>Open tickets</b>",
        'no_tickets': "🆘 <b>No open tickets</b>\n\n<i>All requests processed ✅</i>",
        'admin_settings': """⚙️ <b>Administrator Settings</b>

<b>🔔 NOTIFICATIONS:</b>
├ New messages: {notifications}
└ To channel: {channel_status}

<b>⚡ PERFORMANCE:</b>
├ Anti-spam: {antispam} sec.
└ Database: ✅ Working""",
        
        'direct_message': """✉️ <b>Send message for user</b> <code>{user_id}</code>

<i>The message will come from the bot 🤖
You can send text, photo or video.</i>""",
        
        'message_sent_admin': """✅ <b>Message sent</b>

👤 User: <code>{user_id}</code>
📝 Type: {message_type}""",
        
        'block_user': "✅ User <code>{user_id}</code> blocked.",
        'unblock_user': "✅ User <code>{user_id}</code> unblocked.",
        'user_blocked': "🚫 <b>User blocked</b>",
        'user_already_blocked': "✅ User already blocked",
        'user_not_blocked': "✅ User not blocked",
        
        # New translations
        'main_menu': "🏠 Main menu",
        'just_now': "just now",
        'minutes_ago': "{minutes} minutes ago",
        'hours_ago': "{hours} hours ago",
        'yesterday': "yesterday",
        'days_ago': "{days} days ago",
        'never': "never",
        'language_changed': "✅ Language changed",
        'send_anonymous_to': "Send anonymous message",
        'send_anonymous_description': "Write a message, photo, video or voice message",
        'send_reply': "Send reply message",
        'reply_to_ticket': "Reply to ticket",
        'user_blocked_bot': "❌ User blocked the bot",
        'text': "Text",
        
        # Buttons
        'btn_my_link': "📩 My link",
        'btn_profile': "👤 Profile",
        'btn_stats': "📊 Statistics",
        'btn_settings': "⚙️ Settings",
        'btn_qr': "📱 QR code",
        'btn_help': "ℹ️ Help",
        'btn_support': "🆘 Support",
        'btn_admin': "👑 Admin",
        'btn_turn_on': "🔔 Enable messages",
        'btn_turn_off': "🔕 Disable messages",
        'btn_language': "🌐 Language",
        'btn_back': "⬅️ Back",
        'btn_cancel': "❌ Cancel",
        'btn_history': "📜 History",
        
        'btn_admin_stats': "📊 Statistics",
        'btn_admin_broadcast': "📢 Broadcast",
        'btn_admin_manage_users': "👥 Manage",
        'btn_admin_find': "🔍 Find",
        'btn_admin_logs': "📋 Logs",
        'btn_admin_tickets': "🆘 Tickets",
        'btn_admin_settings': "⚙️ Settings",
        'btn_admin_block': "🚫 Block/Unblock",
        'btn_admin_backup': "💾 Backup",
        'btn_admin_export': "📤 Export",
        
        'btn_reply': "💌 Reply",
        'btn_ignore': "🚫 Ignore",
        'btn_block': "🚫 Block",
        'btn_unblock': "✅ Unblock",
        'btn_message': "✉️ Message",
        'btn_refresh': "🔄 Refresh",
        'btn_toggle_text': "🔕 Hide text",
        'btn_show_text': "🔔 Show text",
        'btn_reply_ticket': "📝 Reply",
        'btn_close_ticket': "✅ Close",
        
        # Support
        'support': """🆘 <b>Support Service</b>

<i>Describe your problem in as much detail as possible 💭
We will try to respond as soon as possible ⏰</i>

<b>📎 What can be sent:</b>
• Text description of the problem ✍️
• Error screenshot 📸
• Bug video 🎬
• Any media file 📎""",
        
        'support_sent': """✅ <b>Support request sent!</b>

<i>Your ticket: <b>#{ticket_id}</b>
We will respond to you as soon as possible ⏰</i>""",
        
        # History
        'history': "📜 <b>Message history</b>\n\n<i>Last 20 messages:</i>",
        'history_empty': "📜 <b>You don't have messages yet</b>\n\n<i>Start communication by sending your first anonymous message!</i>",
        'history_item': """<b>{index}. {direction} {name}</b> <i>({time})</i>
💬 <i>{preview}</i>""",
        'history_incoming': "⬇️ From",
        'history_outgoing': "⬆️ To",
        
        # Block
        'block_instruction': "🚫 <b>Block/Unblock user</b>\n\nEnter user ID or username (without @):",
        'block_success': "✅ User <code>{user_id}</code> blocked.",
        'unblock_success': "✅ User <code>{user_id}</code> unblocked.",
        'block_already': "✅ User already blocked.",
        'user_not_blocked_msg': "✅ User was not blocked.",
        
        # Errors
        'file_too_large': "❌ File is too large (maximum {max_size}MB).",
        'message_too_long': "❌ Message is too long (maximum {max_length} characters).",
        'rate_limit_exceeded': "⏳ Too many requests. Wait {seconds} seconds.",
        'content_blocked': "❌ Message contains forbidden words.",
        'session_expired': "⏰ Session expired. Start over.",
        
        # Export
        'export_instruction': "📤 <b>Export data</b>\n\n<i>Choose what to export:</i>",
        'export_users': "👥 Export users",
        'export_messages': "📨 Export messages",
        'export_stats': "📊 Export statistics",
        'export_processing': "⏳ <b>Exporting data...</b>\n\n<i>Please wait.</i>",
        'export_complete': "✅ <b>Export completed!</b>\n\n<i>Data successfully saved.</i>",
        
        # System
        'system_error': "❌ A system error occurred. Please try again later.",
        'maintenance': "🔧 The bot is under maintenance. We apologize for the inconvenience.",
    }
}

# ====== УТИЛИТЫ ======
def t(lang: str, key: str, **kwargs) -> str:
    """Функция перевода"""
    if lang not in TRANSLATIONS:
        lang = 'ru'
    if key not in TRANSLATIONS[lang]:
        # Fallback to Russian if key not found in current language
        if 'ru' in TRANSLATIONS and key in TRANSLATIONS['ru']:
            return TRANSLATIONS['ru'][key].format(**kwargs) if kwargs else TRANSLATIONS['ru'][key]
        return key
    return TRANSLATIONS[lang][key].format(**kwargs) if kwargs else TRANSLATIONS[lang][key]

def format_time(timestamp: int, lang: str = 'ru') -> str:
    """Форматирование времени"""
    dt = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        if diff.seconds < 60:
            return t(lang, 'just_now')
        elif diff.seconds < 3600:
            return t(lang, 'minutes_ago', minutes=diff.seconds // 60)
        else:
            return t(lang, 'hours_ago', hours=diff.seconds // 3600)
    elif diff.days == 1:
        return t(lang, 'yesterday')
    else:
        return dt.strftime("%d.%m.%Y")

def generate_link(user_id: int) -> str:
    """Генерация ссылки"""
    try:
        bot_username = bot.get_me().username
        return f"https://t.me/{bot_username}?start={user_id}"
    except:
        return f"https://t.me/{bot.get_me().username}?start={user_id}"

def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """Проверка ограничения скорости"""
    now = time.time()
    minute = int(now // 60)
    
    if user_id not in rate_limit_cache:
        rate_limit_cache[user_id] = {'minute': minute, 'count': 1}
        return True, 0
    
    if rate_limit_cache[user_id]['minute'] != minute:
        rate_limit_cache[user_id] = {'minute': minute, 'count': 1}
        return True, 0
    
    rate_limit_cache[user_id]['count'] += 1
    if rate_limit_cache[user_id]['count'] > MAX_REQUESTS_PER_MINUTE:
        wait_time = 60 - (now % 60)
        return False, int(wait_time)
    
    return True, 0

def check_spam(user_id: int) -> bool:
    """Проверка антиспама"""
    current_time = time.time()
    last_time = message_cooldown.get(user_id, 0)
    
    if current_time - last_time < ANTISPAM_INTERVAL:
        return False
    
    message_cooldown[user_id] = current_time
    return True

def check_session_timeout(user_id: int) -> bool:
    """Проверка времени сессии"""
    if user_id not in session_timestamps:
        session_timestamps[user_id] = time.time()
        return True
    
    if time.time() - session_timestamps[user_id] > SESSION_TIMEOUT:
        if user_id in user_sessions:
            del user_sessions[user_id]
        if user_id in admin_modes:
            del admin_modes[user_id]
        session_timestamps[user_id] = time.time()
        return False
    
    session_timestamps[user_id] = time.time()
    return True

def check_content_moderation(text: str) -> bool:
    """Проверка сообщения на запрещённые слова"""
    if not text:
        return True
    
    text_lower = text.lower()
    for word in BLACKLIST_WORDS:
        if word in text_lower:
            return False
    return True

def create_chart(data: Dict, max_width: int = 10) -> str:
    """Создание текстовой диаграммы"""
    if not data:
        return "📊 No data"
    
    max_value = max(data.values()) if data.values() else 1
    result = []
    
    for key, value in sorted(data.items()):
        if max_value > 0:
            width = int((value / max_value) * max_width)
        else:
            width = 0
        bar = "█" * width + "░" * (max_width - width)
        result.append(f"{key}: {bar} {value}")
    
    return "\n".join(result)

# ====== КЛАВИАТУРЫ ======
def main_keyboard(is_admin: bool = False, lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Основная клавиатура"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    buttons = [
        types.KeyboardButton(t(lang, 'btn_my_link')),
        types.KeyboardButton(t(lang, 'btn_profile')),
        types.KeyboardButton(t(lang, 'btn_stats')),
        types.KeyboardButton(t(lang, 'btn_settings')),
        types.KeyboardButton(t(lang, 'btn_qr')),
        types.KeyboardButton(t(lang, 'btn_help')),
        types.KeyboardButton(t(lang, 'btn_support')),
        types.KeyboardButton(t(lang, 'btn_history'))
    ]
    
    if is_admin:
        buttons.append(types.KeyboardButton(t(lang, 'btn_admin')))
    
    keyboard.add(*buttons)
    return keyboard

def settings_keyboard(lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Клавиатура настроек"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'btn_turn_on')),
        types.KeyboardButton(t(lang, 'btn_turn_off')),
        types.KeyboardButton(t(lang, 'btn_language')),
        types.KeyboardButton(t(lang, 'btn_back'))
    ]
    keyboard.add(*buttons)
    return keyboard

def admin_keyboard(lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Админская клавиатура"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'btn_admin_stats')),
        types.KeyboardButton(t(lang, 'btn_admin_broadcast')),
        types.KeyboardButton(t(lang, 'btn_admin_find')),
        types.KeyboardButton(t(lang, 'btn_admin_logs')),
        types.KeyboardButton(t(lang, 'btn_admin_tickets')),
        types.KeyboardButton(t(lang, 'btn_admin_settings')),
        types.KeyboardButton(t(lang, 'btn_admin_block')),
        types.KeyboardButton(t(lang, 'btn_admin_backup')),
        types.KeyboardButton(t(lang, 'btn_admin_export')),
        types.KeyboardButton(t(lang, 'btn_back'))
    ]
    keyboard.add(*buttons)
    return keyboard

def cancel_keyboard(lang: str = 'ru') -> types.ReplyKeyboardMarkup:
    """Клавиатура отмены"""
    return types.ReplyKeyboardMarkup(resize_keyboard=True).add(t(lang, 'btn_cancel'))

def language_keyboard() -> types.InlineKeyboardMarkup:
    """Клавиатура выбора языка"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    )
    return keyboard

def get_message_reply_keyboard(message_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для ответа на сообщение"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply'), callback_data=f"reply_{message_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_ignore'), callback_data="ignore")
    )
    return keyboard

def get_admin_ticket_keyboard(ticket_id: int, user_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для тикета"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply_ticket'), callback_data=f"support_reply_{ticket_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_close_ticket'), callback_data=f"support_close_{ticket_id}")
    )
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_profile'), callback_data=f"admin_user_{user_id}"),
        types.InlineKeyboardButton(t(lang, 'btn_block'), callback_data=f"admin_block_{user_id}")
    )
    return keyboard

def get_admin_user_keyboard(user_id: int, is_blocked: bool, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура управления пользователем"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    if is_blocked:
        keyboard.add(
            types.InlineKeyboardButton(t(lang, 'btn_unblock'), callback_data=f"admin_unblock_{user_id}"),
            types.InlineKeyboardButton(t(lang, 'btn_message'), callback_data=f"admin_msg_{user_id}")
        )
    else:
        keyboard.add(
            types.InlineKeyboardButton(t(lang, 'btn_block'), callback_data=f"admin_block_{user_id}"),
            types.InlineKeyboardButton(t(lang, 'btn_message'), callback_data=f"admin_msg_{user_id}")
        )
    return keyboard

def get_admin_log_keyboard(show_text: bool, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для логов"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_refresh'), callback_data="refresh_logs"),
        types.InlineKeyboardButton(t(lang, 'btn_hide_text') if show_text else t(lang, 'btn_show_text'), 
                                 callback_data="toggle_text")
    )
    return keyboard

def export_keyboard(lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для экспорта"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'export_users'), callback_data="export_users"),
        types.InlineKeyboardButton(t(lang, 'export_messages'), callback_data="export_messages"),
        types.InlineKeyboardButton(t(lang, 'export_stats'), callback_data="export_stats"),
        types.InlineKeyboardButton(t(lang, 'btn_cancel'), callback_data="export_cancel")
    )
    return keyboard

# ====== БАЗА ДАННЫХ ======
class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._stats_cache = {}
        self._stats_cache_time = {}
        self._user_cache = {}
        self._user_cache_time = {}
        self.init_db()
    
    @contextmanager
    def get_connection(self):
        """Контекстный менеджер для подключения к БД"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"DB error: {e}")
            raise
        finally:
            conn.close()
    
    def init_db(self):
        """Инициализация базы данных"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Пользователи
            c.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    language TEXT DEFAULT 'ru',
                    created_at INTEGER,
                    last_active INTEGER,
                    messages_received INTEGER DEFAULT 0,
                    messages_sent INTEGER DEFAULT 0,
                    link_clicks INTEGER DEFAULT 0,
                    receive_messages INTEGER DEFAULT 1,
                    is_premium INTEGER DEFAULT 0,
                    is_blocked INTEGER DEFAULT 0
                )
            ''')
            
            # Сообщения
            c.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER,
                    receiver_id INTEGER,
                    message_type TEXT,
                    text TEXT,
                    file_id TEXT,
                    file_unique_id TEXT,
                    file_size INTEGER,
                    timestamp INTEGER,
                    replied_to INTEGER DEFAULT 0,
                    is_read INTEGER DEFAULT 0,
                    moderated INTEGER DEFAULT 1
                )
            ''')
            
            # Поддержка
            c.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    file_id TEXT,
                    file_unique_id TEXT,
                    message_type TEXT,
                    status TEXT DEFAULT 'open',
                    created_at INTEGER,
                    admin_id INTEGER,
                    admin_reply TEXT,
                    replied_at INTEGER,
                    priority INTEGER DEFAULT 1
                )
            ''')
            
            # История сообщений пользователя
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_history (
                    user_id INTEGER,
                    partner_id INTEGER,
                    message_id INTEGER,
                    direction TEXT,
                    timestamp INTEGER,
                    preview TEXT,
                    PRIMARY KEY (user_id, message_id)
                )
            ''')
            
            # Индексы
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)')
            
            logger.info("✅ Database initialized with indexes")
    
    def _get_cached_user(self, user_id: int):
        """Получение пользователя с кэшированием"""
        now = time.time()
        if user_id in self._user_cache:
            if now - self._user_cache_time.get(user_id, 0) < 60:
                return self._user_cache[user_id]
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            user = dict(row) if row else None
            
            if user:
                self._user_cache[user_id] = user
                self._user_cache_time[user_id] = now
            
            return user
    
    def _get_cached_user_by_username(self, username: str):
        """Получение пользователя по username с кэшированием"""
        now = time.time()
        cache_key = f"username:{username}"
        
        if cache_key in self._user_cache:
            if now - self._user_cache_time.get(cache_key, 0) < 60:
                return self._user_cache[cache_key]
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users WHERE username = ?', (username,))
            row = c.fetchone()
            user = dict(row) if row else None
            
            if user:
                self._user_cache[cache_key] = user
                self._user_cache_time[cache_key] = now
            
            return user
    
    def get_user(self, user_id: int):
        """Получение пользователя"""
        return self._get_cached_user(user_id)
    
    def get_user_by_username(self, username: str):
        """Получение пользователя по username"""
        return self._get_cached_user_by_username(username)
    
    def _clear_user_cache(self, user_id: int = None, username: str = None):
        """Очистка кэша пользователя"""
        if user_id:
            if user_id in self._user_cache:
                del self._user_cache[user_id]
            if user_id in self._user_cache_time:
                del self._user_cache_time[user_id]
        
        if username:
            cache_key = f"username:{username}"
            if cache_key in self._user_cache:
                del self._user_cache[cache_key]
            if cache_key in self._user_cache_time:
                del self._user_cache_time[cache_key]
    
    def get_admin_stats(self):
        """Получение статистики админа"""
        now = time.time()
        if 'admin_stats' in self._stats_cache:
            if now - self._stats_cache_time.get('admin_stats', 0) < 60:
                return self._stats_cache['admin_stats']
        
        stats = self._get_admin_stats_impl()
        self._stats_cache['admin_stats'] = stats
        self._stats_cache_time['admin_stats'] = now
        return stats
    
    def _get_admin_stats_impl(self):
        """Реализация получения статистики админа"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            c.execute('SELECT COUNT(*) FROM users')
            total_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages')
            total_messages = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM users WHERE is_blocked = 1')
            blocked_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM support_tickets WHERE status = "open"')
            open_tickets = c.fetchone()[0]
            
            today_start = int(time.time()) - 86400
            c.execute('SELECT COUNT(DISTINCT user_id) FROM users WHERE last_active > ?', (today_start,))
            today_active = c.fetchone()[0]
            
            # Статистика за 24 часа
            c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 86400,))
            messages_24h = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM users WHERE created_at > ?', 
                     (int(time.time()) - 86400,))
            new_users_24h = c.fetchone()[0]
            
            # Средняя активность в час
            c.execute('SELECT COUNT(*) / 24.0 FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 86400,))
            avg_hourly_result = c.fetchone()[0]
            avg_hourly = round(avg_hourly_result, 2) if avg_hourly_result else 0
            
            # Пользователи за неделю
            c.execute('SELECT COUNT(*) FROM users WHERE created_at > ?', 
                     (int(time.time()) - 604800,))
            users_week = c.fetchone()[0]
            
            # Сообщения за неделю
            c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 604800,))
            messages_week = c.fetchone()[0]
            
            # Активные за неделю
            c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 604800,))
            active_week = c.fetchone()[0]
            
            # Удерживание
            c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 2592000,))
            active_30d = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM users WHERE created_at < ?', 
                     (int(time.time()) - 2592000,))
            old_users = c.fetchone()[0]
            
            retention_30d = round((active_30d / old_users * 100), 2) if old_users > 0 else 100
            
            # Конверсия
            c.execute('SELECT COUNT(DISTINCT sender_id) FROM messages')
            users_with_messages = c.fetchone()[0]
            
            conversion_rate = round((users_with_messages / total_users * 100), 2) if total_users > 0 else 0
            
            return {
                'total_users': total_users,
                'total_messages': total_messages,
                'blocked_users': blocked_users,
                'open_tickets': open_tickets,
                'today_active': today_active,
                'messages_24h': messages_24h,
                'new_users_24h': new_users_24h,
                'avg_hourly': avg_hourly,
                'users_week': users_week,
                'messages_week': messages_week,
                'active_week': active_week,
                'retention_30d': retention_30d,
                'conversion_rate': conversion_rate
            }
    
    def register_user(self, user_id: int, username: str, first_name: str):
        """Регистрация пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            
            c.execute('''
                INSERT OR IGNORE INTO users 
                (user_id, username, first_name, created_at, last_active) 
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, username, first_name, now, now))
            
            c.execute('''
                UPDATE users SET 
                username = ?, 
                first_name = ?,
                last_active = ?
                WHERE user_id = ?
            ''', (username, first_name, now, user_id))
            
            self._clear_user_cache(user_id, username)
    
    def update_last_active(self, user_id: int):
        """Обновление времени последней активности"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET last_active = ? WHERE user_id = ?', 
                     (int(time.time()), user_id))
            self._clear_user_cache(user_id)
    
    def increment_stat(self, user_id: int, field: str):
        """Инкремент статистики пользователя"""
        valid_fields = {'messages_received', 'messages_sent', 'link_clicks'}
        if field not in valid_fields:
            return
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute(f'UPDATE users SET {field} = {field} + 1 WHERE user_id = ?', 
                     (user_id,))
            self._clear_user_cache(user_id)
    
    def set_receive_messages(self, user_id: int, status: bool):
        """Установка статуса приёма сообщений"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET receive_messages = ? WHERE user_id = ?',
                     (1 if status else 0, user_id))
            self._clear_user_cache(user_id)
    
    def set_language(self, user_id: int, language: str):
        """Установка языка"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET language = ? WHERE user_id = ?',
                     (language, user_id))
            self._clear_user_cache(user_id)
    
    def get_all_users_list(self) -> List[int]:
        """Получение списка всех пользователей"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id FROM users WHERE is_blocked = 0')
            rows = c.fetchall()
            return [row[0] for row in rows]
    
    def get_all_users_count(self) -> int:
        """Получение количества всех пользователей"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM users')
            return c.fetchone()[0]
    
    def save_message(self, sender_id: int, receiver_id: int, message_type: str, 
                    text: str = "", file_id: Optional[str] = None, 
                    file_unique_id: Optional[str] = None, file_size: int = 0,
                    replied_to: int = 0, moderated: bool = True) -> int:
        """Сохранение сообщения"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO messages 
                (sender_id, receiver_id, message_type, text, file_id, file_unique_id, 
                 file_size, timestamp, replied_to, moderated) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (sender_id, receiver_id, message_type, text, file_id, file_unique_id,
                  file_size, int(time.time()), replied_to, 1 if moderated else 0))
            message_id = c.lastrowid
            
            # Добавляем в историю
            preview = text[:50] if text else f"[{message_type}]"
            
            # История для отправителя
            c.execute('''
                INSERT OR REPLACE INTO user_history 
                (user_id, partner_id, message_id, direction, timestamp, preview) 
                VALUES (?, ?, ?, 'outgoing', ?, ?)
            ''', (sender_id, receiver_id, message_id, int(time.time()), preview))
            
            # История для получателя
            c.execute('''
                INSERT OR REPLACE INTO user_history 
                (user_id, partner_id, message_id, direction, timestamp, preview) 
                VALUES (?, ?, ?, 'incoming', ?, ?)
            ''', (receiver_id, sender_id, message_id, int(time.time()), preview))
            
            return message_id
    
    def get_user_messages_stats(self, user_id: int) -> Dict[str, int]:
        """Статистика сообщений пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT messages_received, messages_sent, link_clicks FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            
            if row:
                return {
                    'messages_received': row['messages_received'],
                    'messages_sent': row['messages_sent'],
                    'link_clicks': row['link_clicks']
                }
            return {'messages_received': 0, 'messages_sent': 0, 'link_clicks': 0}
    
    def get_user_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        """История сообщений пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT h.*, u.first_name as partner_name, u.username as partner_username
                FROM user_history h
                LEFT JOIN users u ON h.partner_id = u.user_id
                WHERE h.user_id = ?
                ORDER BY h.timestamp DESC
                LIMIT ?
            ''', (user_id, limit))
            
            rows = c.fetchall()
            history = []
            for row in rows:
                history.append({
                    'message_id': row['message_id'],
                    'partner_id': row['partner_id'],
                    'partner_name': row['partner_name'],
                    'partner_username': row['partner_username'],
                    'direction': row['direction'],
                    'timestamp': row['timestamp'],
                    'preview': row['preview']
                })
            return history
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Проверка блокировки пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT is_blocked FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            return row['is_blocked'] == 1 if row else False
    
    def block_user(self, user_id: int, admin_id: int, reason: str = "") -> bool:
        """Блокировка пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET is_blocked = 1 WHERE user_id = ?', (user_id,))
            self._clear_user_cache(user_id)
            return True
    
    def unblock_user(self, user_id: int) -> bool:
        """Разблокировка пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('UPDATE users SET is_blocked = 0 WHERE user_id = ?', (user_id,))
            success = c.rowcount > 0
            if success:
                self._clear_user_cache(user_id)
            return success
    
    def create_support_ticket(self, user_id: int, message: str, file_id: Optional[str] = None,
                            file_unique_id: Optional[str] = None, message_type: str = "text") -> int:
        """Создание тикета поддержки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                INSERT INTO support_tickets 
                (user_id, message, file_id, file_unique_id, message_type, created_at) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, message, file_id, file_unique_id, message_type, now))
            return c.lastrowid
    
    def get_open_support_tickets(self) -> List[Dict]:
        """Получение открытых тикетов"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT s.*, u.first_name, u.username 
                FROM support_tickets s
                LEFT JOIN users u ON s.user_id = u.user_id
                WHERE s.status = 'open'
                ORDER BY s.created_at DESC
            ''')
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    def update_support_ticket(self, ticket_id: int, admin_id: int, 
                            reply_text: str, status: str = 'answered'):
        """Обновление тикета поддержки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                UPDATE support_tickets 
                SET admin_id = ?, admin_reply = ?, replied_at = ?, status = ?
                WHERE id = ?
            ''', (admin_id, reply_text, now, status, ticket_id))
    
    def get_recent_messages(self, limit: int = 10, include_text: bool = True) -> List[Dict]:
        """Последние сообщения"""
        with self.get_connection() as conn:
            c = conn.cursor()
            query = '''
                SELECT m.*, u1.first_name as sender_name, u1.username as sender_username,
                       u2.first_name as receiver_name, u2.username as receiver_username
                FROM messages m
                LEFT JOIN users u1 ON m.sender_id = u1.user_id
                LEFT JOIN users u2 ON m.receiver_id = u2.user_id
                ORDER BY m.timestamp DESC LIMIT ?
            '''
            c.execute(query, (limit,))
            rows = c.fetchall()
            messages = []
            for row in rows:
                msg = dict(row)
                if not include_text:
                    msg['text'] = '[HIDDEN]' if msg['text'] else ''
                messages.append(msg)
            return messages

    def export_users_data(self) -> str:
        """Экспорт данных пользователей в CSV"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT user_id, username, first_name, language, 
                       created_at, last_active, messages_received, 
                       messages_sent, link_clicks, receive_messages, is_blocked
                FROM users ORDER BY user_id
            ''')
            rows = c.fetchall()
            
            csv_content = "ID;Username;First Name;Language;Created At;Last Active;Messages Received;Messages Sent;Link Clicks;Receive Messages;Is Blocked\n"
            for row in rows:
                created = datetime.fromtimestamp(row['created_at']).strftime('%Y-%m-%d %H:%M')
                last_active = datetime.fromtimestamp(row['last_active']).strftime('%Y-%m-%d %H:%M') if row['last_active'] else "Never"
                csv_content += f"{row['user_id']};{row['username'] or ''};{row['first_name'] or ''};{row['language']};"
                csv_content += f"{created};{last_active};{row['messages_received']};{row['messages_sent']};"
                csv_content += f"{row['link_clicks']};{row['receive_messages']};{row['is_blocked']}\n"
            
            return csv_content

    def export_messages_data(self) -> str:
        """Экспорт данных сообщений в CSV"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, sender_id, receiver_id, message_type, text, timestamp
                FROM messages ORDER BY timestamp DESC LIMIT 1000
            ''')
            rows = c.fetchall()
            
            csv_content = "ID;Sender ID;Receiver ID;Type;Text;Timestamp\n"
            for row in rows:
                timestamp = datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M')
                text = (row['text'] or '').replace(';', ',').replace('\n', ' ').replace('\r', '')
                csv_content += f"{row['id']};{row['sender_id']};{row['receiver_id']};{row['message_type']};{text};{timestamp}\n"
            
            return csv_content

db = Database()

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start'])
def start_command(message):
    """Обработчик команды /start"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"Start from user_id={user_id}")
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    # Регистрация пользователя
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    # Обновление сессии
    session_timestamps[user_id] = time.time()
    
    args = message.text.split()
    
    # Обработка реферальной ссылки
    if len(args) > 1 and args[1].isdigit():
        target_id = int(args[1])
        handle_link_click(user_id, target_id)
        return
    
    # Стандартное приветствие
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    link = generate_link(user_id)
    
    bot.send_message(user_id, t(lang, 'start', link=link), 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def handle_link_click(clicker_id: int, target_id: int):
    """Обработка клика по ссылке"""
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, t('ru', 'user_not_found'))
        return
    
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, t('ru', 'messages_disabled'))
        return
    
    user_sessions[clicker_id] = {
        'target_id': target_id,
        'mode': 'anonymous'
    }
    db.increment_stat(target_id, 'link_clicks')
    
    user = db.get_user(clicker_id)
    lang = user['language'] if user else 'ru'
    
    bot.send_message(
        clicker_id,
        t(lang, 'start_ref'),
        reply_markup=cancel_keyboard(lang)
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    """Обработчик callback запросов"""
    user_id = call.from_user.id
    data = call.data
    
    try:
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        
        if data == "ignore":
            bot.answer_callback_query(call.id, "✅ OK")
            return
        
        elif data == "refresh_logs":
            if user_id == ADMIN_ID:
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, t(lang, 'btn_refresh'))
            return
        
        elif data == "toggle_text":
            if user_id == ADMIN_ID:
                current = admin_modes.get(user_id, {}).get('show_text', True)
                admin_modes[user_id] = {'show_text': not current}
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, t(lang, 'settings'))
            return
        
        elif data.startswith("lang_"):
            language = data.split("_")[1]
            db.set_language(user_id, language)
            bot.answer_callback_query(call.id, t(language, 'language_changed'))
            
            link = generate_link(user_id)
            bot.send_message(user_id, t(language, 'start', link=link), 
                           reply_markup=main_keyboard(user_id == ADMIN_ID, language))
            return
        
        elif data.startswith("reply_"):
            message_id = int(data.split("_")[1])
            
            # Получаем информацию о сообщении
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('SELECT sender_id, receiver_id FROM messages WHERE id = ?', (message_id,))
                msg = c.fetchone()
                
                if msg and msg['receiver_id'] == user_id:
                    user_sessions[user_id] = {
                        'target_id': msg['sender_id'],
                        'mode': 'anonymous',
                        'reply_to': message_id
                    }
                    
                    bot.send_message(user_id, "💌 Введите ваш ответ:",
                                    reply_markup=cancel_keyboard(lang))
                    bot.answer_callback_query(call.id)
                else:
                    bot.answer_callback_query(call.id, "❌ Ошибка")
        
        elif data.startswith("admin_block_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            if db.block_user(target_id, ADMIN_ID, "Admin panel"):
                bot.answer_callback_query(call.id, t(lang, 'block_user'))
                
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + f"\n\n{t(lang, 'user_blocked')}",
                        reply_markup=get_admin_user_keyboard(target_id, True, lang)
                    )
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, t(lang, 'user_already_blocked'))
        
        elif data.startswith("admin_unblock_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            if db.unblock_user(target_id):
                bot.answer_callback_query(call.id, t(lang, 'unblock_user'))
                
                try:
                    bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=call.message.text + "\n\n✅ Unblocked",
                        reply_markup=get_admin_user_keyboard(target_id, False, lang)
                    )
                except:
                    pass
            else:
                bot.answer_callback_query(call.id, t(lang, 'user_not_blocked_msg'))
        
        elif data.startswith("admin_msg_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            admin_modes[user_id] = f'direct_msg_{target_id}'
            
            bot.send_message(user_id, t(lang, 'direct_message', user_id=target_id),
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_reply_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            ticket_id = int(data.split("_")[2])
            admin_modes[user_id] = f'support_reply_{ticket_id}'
            
            bot.send_message(user_id, f"📝 {t(lang, 'reply_to_ticket')} #{ticket_id}",
                           reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("support_close_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            ticket_id = int(data.split("_")[2])
            db.update_support_ticket(ticket_id, user_id, "Closed", "closed")
            bot.answer_callback_query(call.id, "✅ Closed")
            
            try:
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=call.message.text + "\n\n✅ Ticket closed"
                )
            except:
                pass
        
        elif data.startswith("admin_user_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            find_user_info(admin_id=user_id, query=str(target_id))
            bot.answer_callback_query(call.id)
        
        elif data == "export_users":
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            export_users_data(admin_id=user_id, lang=lang)
            bot.answer_callback_query(call.id, t(lang, 'export_processing'))
        
        elif data == "export_messages":
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            export_messages_data(admin_id=user_id, lang=lang)
            bot.answer_callback_query(call.id, t(lang, 'export_processing'))
        
        elif data == "export_stats":
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            export_stats_data(admin_id=user_id, lang=lang)
            bot.answer_callback_query(call.id, t(lang, 'export_processing'))
        
        elif data == "export_cancel":
            bot.answer_callback_query(call.id, t(lang, 'canceled'))
            bot.send_message(user_id, t(lang, 'main_menu'), 
                           reply_markup=admin_keyboard(lang))
        
        else:
            bot.answer_callback_query(call.id, "⚠️ Unknown command")
        
    except Exception as e:
        logger.error(f"Callback error: {e}")
        bot.answer_callback_query(call.id, "❌ Error")

# ====== ОСНОВНОЙ ОБРАБОТЧИК ======
@bot.message_handler(content_types=['text', 'photo', 'video', 'audio', 'voice', 'document', 'sticker'])
def handle_message(message):
    """Основной обработчик сообщений"""
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    # Игнорирование команд
    if message.text and message.text.startswith('/'):
        return
    
    # Проверка блокировки
    if db.is_user_blocked(user_id):
        bot.send_message(user_id, t('ru', 'blocked'))
        return
    
    # Проверка ограничения скорости
    allowed, wait_time = check_rate_limit(user_id)
    if not allowed:
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'rate_limit_exceeded', seconds=wait_time))
        return
    
    # Проверка сессии
    if not check_session_timeout(user_id):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'session_expired'))
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    db.update_last_active(user_id)
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    
    # Обработка кнопки "Отмена"
    if text == t(lang, 'btn_cancel'):
        clear_user_state(user_id)
        bot.send_message(user_id, t(lang, 'canceled'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    # Обработка кнопки "Админ"
    if text == t(lang, 'btn_admin') and user_id == ADMIN_ID:
        bot.send_message(user_id, t(lang, 'admin_panel'), 
                        reply_markup=admin_keyboard(lang))
        return
    
    # Обработка админских режимов
    if user_id == ADMIN_ID and user_id in admin_modes:
        mode = admin_modes[user_id]
        
        if isinstance(mode, str):
            if mode.startswith('direct_msg_'):
                target_id = int(mode.split('_')[2])
                send_direct_admin_message(message, target_id, lang)
                if user_id in admin_modes:
                    del admin_modes[user_id]
                return
            
            elif mode.startswith('support_reply_'):
                ticket_id = int(mode.split('_')[2])
                reply_to_support_ticket(message, ticket_id, lang)
                if user_id in admin_modes:
                    del admin_modes[user_id]
                return
    
    # Обработка кнопки "Поддержка"
    if text == t(lang, 'btn_support'):
        handle_support_request(message, lang)
        return
    
    # Обработка анонимных сообщений
    if user_id in user_sessions and user_sessions[user_id]['mode'] == 'anonymous':
        target_id = user_sessions[user_id]['target_id']
        send_anonymous_message(user_id, target_id, message, lang)
        return
    
    # Обработка тикетов поддержки
    if user_id in admin_modes and admin_modes[user_id] == 'support':
        create_support_ticket(message, lang)
        if user_id in admin_modes:
            del admin_modes[user_id]
        return
    
    # Обработка текстовых кнопок
    if message_type == 'text':
        handle_text_button(user_id, text, lang)

def clear_user_state(user_id: int):
    """Очистка состояния пользователя"""
    if user_id in user_sessions:
        del user_sessions[user_id]
    if user_id in admin_modes:
        del admin_modes[user_id]

def handle_text_button(user_id: int, text: str, lang: str):
    """Обработка текстовых кнопок"""
    is_admin = user_id == ADMIN_ID
    
    if text == t(lang, 'btn_my_link'):
        link = generate_link(user_id)
        bot.send_message(user_id, t(lang, 'my_link', link=link),
                        reply_markup=main_keyboard(is_admin, lang))
    
    elif text == t(lang, 'btn_profile'):
        show_profile(user_id, lang)
    
    elif text == t(lang, 'btn_stats'):
        show_user_stats(user_id, lang)
    
    elif text == t(lang, 'btn_settings'):
        bot.send_message(user_id, t(lang, 'settings'),
                        reply_markup=settings_keyboard(lang))
    
    elif text == t(lang, 'btn_qr'):
        generate_qr_code(user_id, lang)
    
    elif text == t(lang, 'btn_help'):
        show_help(user_id, lang)
    
    elif text == t(lang, 'btn_history'):
        show_user_history(user_id, lang)
    
    elif text == t(lang, 'btn_turn_on'):
        db.set_receive_messages(user_id, True)
        bot.send_message(user_id, t(lang, 'turn_on'),
                        reply_markup=settings_keyboard(lang))
    
    elif text == t(lang, 'btn_turn_off'):
        db.set_receive_messages(user_id, False)
        bot.send_message(user_id, t(lang, 'turn_off'),
                        reply_markup=settings_keyboard(lang))
    
    elif text == t(lang, 'btn_language'):
        bot.send_message(user_id, t(lang, 'language'),
                        reply_markup=language_keyboard())
    
    elif text == t(lang, 'btn_back'):
        bot.send_message(user_id, t(lang, 'main_menu'),
                        reply_markup=main_keyboard(is_admin, lang))
    
    elif is_admin:
        handle_admin_command(user_id, text, lang)

def show_profile(user_id: int, lang: str):
    """Показ профиля пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ Profile not found", 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    
    receive_status = "✅ Enabled" if user['receive_messages'] else "❌ Disabled"
    username = f"@{user['username']}" if user['username'] else "❌ none"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=stats['messages_received'],
                    sent=stats['messages_sent'],
                    clicks=stats['link_clicks'],
                    receive_status=receive_status,
                    language=user['language'].upper(),
                    last_active=format_time(user['last_active'], lang),
                    registered=format_time(user['created_at'], lang),
                    link=generate_link(user_id))
    
    bot.send_message(user_id, profile_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_stats(user_id: int, lang: str):
    """Показ статистики пользователя"""
    user = db.get_user(user_id)
    
    if not user:
        bot.send_message(user_id, "❌ User not found", 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    stats = db.get_user_messages_stats(user_id)
    
    stats_text = f"""📊 <b>Ваша статистика</b>

<b>📈 Основные метрики:</b>
├ 📨 Получено: <b>{stats['messages_received']}</b> сообщений
├ 📤 Отправлено: <b>{stats['messages_sent']}</b> сообщений
└ 🔗 Переходов: <b>{stats['link_clicks']}</b> раз

<b>📅 Активность:</b>
├ 📆 Зарегистрирован: <b>{format_time(user['created_at'], lang)}</b>
└ 📅 Последняя активность: <b>{format_time(user['last_active'], lang)}</b>

<b>⚙️ Настройки:</b>
├ Приём сообщений: {'✅ Включен' if user['receive_messages'] else '❌ Выключен'}
└ Язык: {'🇷🇺 Русский' if user['language'] == 'ru' else '🇺🇸 English'}"""
    
    bot.send_message(user_id, stats_text, 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def show_user_history(user_id: int, lang: str):
    """Показ истории сообщений"""
    history = db.get_user_history(user_id, limit=20)
    
    if not history:
        bot.send_message(user_id, t(lang, 'history_empty'),
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    history_text = t(lang, 'history') + "\n\n"
    
    for i, item in enumerate(history, 1):
        direction = t(lang, 'history_incoming') if item['direction'] == 'incoming' else t(lang, 'history_outgoing')
        name = item['partner_name'] or f"ID: {item['partner_id']}"
        time_str = format_time(item['timestamp'], lang)
        
        history_text += t(lang, 'history_item',
                         index=i,
                         direction=direction,
                         name=name,
                         time=time_str,
                         preview=item['preview']) + "\n\n"
    
    bot.send_message(user_id, history_text,
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

def send_anonymous_message(sender_id: int, receiver_id: int, message, lang: str):
    """Отправка анонимного сообщения"""
    try:
        # Проверка получателя
        receiver = db.get_user(receiver_id)
        if not receiver or receiver['receive_messages'] == 0:
            bot.send_message(sender_id, t(lang, 'messages_disabled'))
            return
        
        message_type = message.content_type
        text = message.text or message.caption or ""
        
        # Проверка длины сообщения
        if len(text) > MAX_MESSAGE_LENGTH:
            bot.send_message(sender_id, t(lang, 'message_too_long', max_length=MAX_MESSAGE_LENGTH))
            return
        
        # Проверка модерации
        if not check_content_moderation(text):
            bot.send_message(sender_id, t(lang, 'content_blocked'))
            return
        
        file_id = None
        file_unique_id = None
        file_size = 0
        
        # Обработка файлов
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
            file_unique_id = message.photo[-1].file_unique_id
            file_size = message.photo[-1].file_size or 0
        elif message_type == 'video':
            file_id = message.video.file_id
            file_unique_id = message.video.file_unique_id
            file_size = message.video.file_size or 0
        elif message_type == 'audio':
            file_id = message.audio.file_id
            file_unique_id = message.audio.file_unique_id
            file_size = message.audio.file_size or 0
        elif message_type == 'voice':
            file_id = message.voice.file_id
            file_unique_id = message.voice.file_unique_id
            file_size = message.voice.file_size or 0
        elif message_type == 'document':
            file_id = message.document.file_id
            file_unique_id = message.document.file_unique_id
            file_size = message.document.file_size or 0
        elif message_type == 'sticker':
            file_id = message.sticker.file_id
            file_unique_id = message.sticker.file_unique_id
        
        # Проверка размера файла
        if file_size > MAX_FILE_SIZE:
            max_size_mb = MAX_FILE_SIZE // (1024 * 1024)
            bot.send_message(sender_id, t(lang, 'file_too_large', max_size=max_size_mb))
            return
        
        # Сохранение сообщения
        replied_to = 0
        if sender_id in user_sessions and 'reply_to' in user_sessions[sender_id]:
            replied_to = user_sessions[sender_id]['reply_to']
        
        message_id = db.save_message(sender_id, receiver_id, message_type, 
                       text, file_id, file_unique_id, file_size, replied_to)
        
        # Обновление статистики
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Формирование сообщения для получателя
        receiver_lang = receiver['language'] if receiver else 'ru'
        
        if text:
            message_content = f"💬 {text}"
        else:
            message_content = "📎 Файл"
        
        # Отправка получателю
        try:
            if message_type == 'text':
                msg = bot.send_message(receiver_id, 
                    t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'photo':
                msg = bot.send_photo(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'video':
                msg = bot.send_video(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'audio':
                msg = bot.send_audio(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'voice':
                msg = bot.send_voice(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'document':
                msg = bot.send_document(receiver_id, file_id,
                    caption=t(receiver_lang, 'anonymous_message', message_content=message_content),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
            
            elif message_type == 'sticker':
                bot.send_message(receiver_id,
                    t(receiver_lang, 'anonymous_message', message_content="😜 Стикер"),
                    reply_markup=get_message_reply_keyboard(message_id, receiver_lang))
                msg = bot.send_sticker(receiver_id, file_id)
        
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(sender_id, t(lang, 'user_blocked_bot'))
                return
            elif e.error_code == 400:
                bot.send_message(sender_id, "❌ Error: invalid message format")
            else:
                logger.error(f"Send error: {e}")
                bot.send_message(sender_id, t(lang, 'system_error'))
            return
        
        # Уведомление отправителю
        bot.send_message(sender_id, t(lang, 'message_sent'),
                        reply_markup=cancel_keyboard(lang))
        
        # Логирование в канал
        if CHANNEL and CHANNEL != "":
            try:
                sender = db.get_user(sender_id)
                log_msg = f"""📨 Новое анонимное сообщение

👤 Отправитель: {sender_id}
🎯 Получатель: {receiver_id}
📝 Тип: {message_type}"""
                
                if text:
                    log_msg += f"\n💬 Текст: {text[:100]}"
                
                if file_id and message_type in ['photo', 'video']:
                    if message_type == 'photo':
                        bot.send_photo(CHANNEL, file_id, caption=log_msg)
                    elif message_type == 'video':
                        bot.send_video(CHANNEL, file_id, caption=log_msg)
                else:
                    bot.send_message(CHANNEL, log_msg)
            except Exception as e:
                logger.error(f"Channel error: {e}")
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.send_message(sender_id, t(lang, 'system_error'))

def handle_support_request(message, lang: str):
    """Обработка запроса в поддержку"""
    user_id = message.from_user.id
    bot.send_message(user_id, t(lang, 'support'), reply_markup=cancel_keyboard(lang))
    admin_modes[user_id] = 'support'

def create_support_ticket(message, lang: str):
    """Создание тикета поддержки"""
    user_id = message.from_user.id
    message_type = message.content_type
    text = message.text or message.caption or ""
    
    if not text and message_type == 'text':
        bot.send_message(user_id, "❌ Введите текст")
        return
    
    try:
        file_id = None
        file_unique_id = None
        
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
            file_unique_id = message.photo[-1].file_unique_id
        elif message_type == 'video':
            file_id = message.video.file_id
            file_unique_id = message.video.file_unique_id
        elif message_type == 'document':
            file_id = message.document.file_id
            file_unique_id = message.document.file_unique_id
        
        ticket_id = db.create_support_ticket(user_id, text, file_id, file_unique_id, message_type)
        
        bot.send_message(user_id, t(lang, 'support_sent', ticket_id=ticket_id),
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        
        notify_admin_about_ticket(ticket_id, user_id, message_type, text, file_id)
        
    except Exception as e:
        logger.error(f"Ticket error: {e}")
        bot.send_message(user_id, "❌ Ошибка создания тикета")

def notify_admin_about_ticket(ticket_id: int, user_id: int, message_type: str, 
                            text: str, file_id: Optional[str]):
    """Уведомление админа о новом тикете"""
    user = db.get_user(user_id)
    
    notification = f"""🆘 Новый тикет #{ticket_id}

👤 Пользователь: {user['first_name'] if user else '?'}
📱 Username: {f'@{user['username']}' if user and user['username'] else 'нет'}
📅 Время: {format_time(int(time.time()))}
📝 Тип: {message_type}"""
    
    if text:
        notification += f"\n💬 Сообщение: {text[:200]}"
    
    try:
        if file_id and message_type in ['photo', 'video']:
            if message_type == 'photo':
                msg = bot.send_photo(ADMIN_ID, file_id, caption=notification, 
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'ru'))
            elif message_type == 'video':
                msg = bot.send_video(ADMIN_ID, file_id, caption=notification,
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'ru'))
        else:
            msg = bot.send_message(ADMIN_ID, notification,
                                 reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'ru'))
        
        if CHANNEL and CHANNEL != str(ADMIN_ID) and CHANNEL != "":
            try:
                if file_id and message_type in ['photo', 'video']:
                    if message_type == 'photo':
                        bot.send_photo(CHANNEL, file_id, caption=notification)
                    elif message_type == 'video':
                        bot.send_video(CHANNEL, file_id, caption=notification)
                else:
                    bot.send_message(CHANNEL, notification)
            except:
                pass
                
    except Exception as e:
        logger.error(f"Notify error: {e}")

def reply_to_support_ticket(message, ticket_id: int, lang: str):
    """Ответ на тикет поддержки"""
    try:
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT user_id, message FROM support_tickets WHERE id = ?', (ticket_id,))
            row = c.fetchone()
            
            if not row:
                bot.send_message(ADMIN_ID, "❌ Ticket not found.")
                return
            
            user_id, user_message = row
        
        message_type = message.content_type
        reply_text = message.text or message.caption or ""
        
        if not reply_text and message_type == 'text':
            bot.send_message(ADMIN_ID, "❌ Enter text")
            return
        
        file_id = None
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        
        db.update_support_ticket(ticket_id, ADMIN_ID, reply_text, 'answered')
        
        user_reply = f"""🆘 Support response

Your message:
{user_message[:500]}

Our response:
{reply_text}

<i>Best regards, bot team 🤖</i>"""
        
        try:
            if message_type == 'text':
                bot.send_message(user_id, user_reply)
            elif message_type == 'photo':
                bot.send_photo(user_id, file_id, caption=user_reply)
            elif message_type == 'video':
                bot.send_video(user_id, file_id, caption=user_reply)
            elif message_type == 'document':
                bot.send_document(user_id, file_id, caption=user_reply)
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ User {user_id} blocked the bot.")
            else:
                raise
        
        bot.send_message(ADMIN_ID, f"✅ Response to ticket #{ticket_id} sent",
                        reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Reply error: {e}")
        bot.send_message(ADMIN_ID, "❌ Response sending error")

def send_direct_admin_message(message, target_user_id: int, lang: str):
    """Отправка прямого сообщения от админа"""
    try:
        message_type = message.content_type
        text = message.text or message.caption or ""
        
        if not text and message_type == 'text':
            bot.send_message(ADMIN_ID, "❌ Enter text")
            return
        
        file_id = None
        if message_type == 'photo':
            file_id = message.photo[-1].file_id
        elif message_type == 'video':
            file_id = message.video.file_id
        elif message_type == 'document':
            file_id = message.document.file_id
        elif message_type == 'sticker':
            file_id = message.sticker.file_id
        
        # Формирование сообщения
        user_message = f"""📢 Important notification

{text}

<i>Best regards, bot team 🤖</i>"""
        
        try:
            # Отправка пользователю
            if message_type == 'text':
                bot.send_message(target_user_id, user_message)
            elif message_type == 'photo':
                bot.send_photo(target_user_id, file_id, caption=user_message)
            elif message_type == 'video':
                bot.send_video(target_user_id, file_id, caption=user_message)
            elif message_type == 'document':
                bot.send_document(target_user_id, file_id, caption=user_message)
            elif message_type == 'sticker':
                bot.send_message(target_user_id, user_message)
                bot.send_sticker(target_user_id, file_id)
        except ApiTelegramException as e:
            if e.error_code == 403:
                bot.send_message(ADMIN_ID, f"❌ User {target_user_id} blocked the bot.")
                return
            else:
                raise
        
        # Уведомление админа
        bot.send_message(ADMIN_ID, t(lang, 'message_sent_admin', user_id=target_user_id, message_type=message_type),
                        reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        bot.send_message(ADMIN_ID, "❌ Sending error")

def generate_qr_code(user_id: int, lang: str):
    """Генерация QR-кода"""
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(
            version=1,
            box_size=6,
            border=2,
            error_correction=qrcode.constants.ERROR_CORRECT_L
        )
        qr.add_data(link)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        bio = BytesIO()
        img.save(bio, 'PNG', optimize=True, quality=85)
        bio.seek(0)
        
        bot.send_photo(user_id, photo=bio, caption=t(lang, 'qr_code', link=link),
                      reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
    except Exception as e:
        logger.error(f"QR error: {e}")
        bot.send_message(user_id, "❌ QR code generation error")

def show_help(user_id: int, lang: str):
    """Показ помощи"""
    bot.send_message(user_id, t(lang, 'help'), 
                    reply_markup=main_keyboard(user_id == ADMIN_ID, lang))

# ====== АДМИНСКИЕ ФУНКЦИИ ======
def handle_admin_command(admin_id: int, text: str, lang: str):
    """Обработка админских команд"""
    
    if text == t(lang, 'btn_admin_stats'):
        show_admin_stats(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_broadcast'):
        admin_modes[admin_id] = 'broadcast'
        bot.send_message(admin_id, t(lang, 'broadcast_start'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_find'):
        admin_modes[admin_id] = 'find_user'
        bot.send_message(admin_id, t(lang, 'find_user'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_logs'):
        show_message_logs(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_tickets'):
        show_support_tickets(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_settings'):
        show_admin_settings(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_block'):
        admin_modes[admin_id] = 'block_user'
        bot.send_message(admin_id, t(lang, 'block_instruction'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_backup'):
        create_backup(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_export'):
        bot.send_message(admin_id, t(lang, 'export_instruction'), reply_markup=export_keyboard(lang))
    
    elif text == t(lang, 'btn_back'):
        bot.send_message(admin_id, t(lang, 'main_menu'), reply_markup=main_keyboard(True, lang))
    
    elif admin_id in admin_modes:
        mode = admin_modes[admin_id]
        
        if mode == 'broadcast':
            start_broadcast(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'find_user':
            find_user_info(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'block_user':
            handle_block_user(admin_id, text, lang)
            if admin_id in admin_modes:
                del admin_modes[admin_id]

def show_admin_stats(admin_id: int, lang: str):
    """Показ статистики админа"""
    stats = db.get_admin_stats()
    
    stats_text = t(lang, 'admin_stats',
                   total_users=stats['total_users'],
                   today_active=stats['today_active'],
                   total_messages=stats['total_messages'],
                   messages_24h=stats['messages_24h'],
                   new_users_24h=stats['new_users_24h'],
                   blocked_users=stats['blocked_users'],
                   open_tickets=stats['open_tickets'],
                   avg_hourly=stats['avg_hourly'],
                   users_week=stats['users_week'],
                   messages_week=stats['messages_week'],
                   active_week=stats['active_week'],
                   retention_30d=stats['retention_30d'],
                   conversion_rate=stats['conversion_rate'])
    
    bot.send_message(admin_id, stats_text, reply_markup=admin_keyboard(lang))

def start_broadcast(admin_id: int, message, lang: str):
    """Запуск рассылки"""
    try:
        if isinstance(message, str):
            text = message
        else:
            text = message.text or message.caption or ""
            
        if not text:
            bot.send_message(admin_id, "❌ Enter broadcast text")
            return
        
        users = db.get_all_users_list()
        total = len(users)
        
        if total == 0:
            bot.send_message(admin_id, "❌ No users found")
            return
        
        sent = 0
        failed = 0
        blocked = 0
        
        progress_msg = bot.send_message(admin_id, t(lang, 'broadcast_progress', total=total))
        
        for user_id in users:
            try:
                if db.is_user_blocked(user_id):
                    blocked += 1
                    continue
                
                bot.send_message(user_id, text, parse_mode="HTML")
                sent += 1
                time.sleep(0.05)
            except:
                failed += 1
        
        bot.edit_message_text(
            chat_id=admin_id,
            message_id=progress_msg.message_id,
            text=t(lang, 'broadcast_result', total=total, sent=sent, failed=failed, blocked=blocked)
        )
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        bot.send_message(admin_id, f"❌ Error: {e}")

def find_user_info(admin_id: int, query: str, lang: str):
    """Поиск информации о пользователе"""
    try:
        user = None
        
        if query.isdigit():
            user_id = int(query)
            user = db.get_user(user_id)
        else:
            username = query.lstrip('@')
            user = db.get_user_by_username(username)
        
        if not user:
            bot.send_message(admin_id, t(lang, 'user_not_found'), reply_markup=admin_keyboard(lang))
            return
        
        stats = db.get_user_messages_stats(user['user_id'])
        is_blocked = db.is_user_blocked(user['user_id'])
        
        username = f"@{user['username']}" if user['username'] else "❌ нет"
        receive_status = "✅ Enabled" if user['receive_messages'] else "❌ Disabled"
        block_status = "🔴 BLOCKED" if is_blocked else "🟢 ACTIVE"
        
        user_info = t(lang, 'user_info',
                     user_id=user['user_id'],
                     first_name=user['first_name'],
                     username=username,
                     registered=format_time(user['created_at'], lang),
                     last_active=format_time(user['last_active'], lang),
                     received=stats['messages_received'],
                     sent=stats['messages_sent'],
                     clicks=user['link_clicks'],
                     receive_status=receive_status,
                     block_status=block_status)
        
        bot.send_message(admin_id, user_info, 
                        reply_markup=get_admin_user_keyboard(user['user_id'], is_blocked, lang))
        
    except Exception as e:
        logger.error(f"Find user error: {e}")
        bot.send_message(admin_id, f"❌ Error: {e}", reply_markup=admin_keyboard(lang))

def handle_block_user(admin_id: int, query: str, lang: str):
    """Обработка блокировки пользователя"""
    try:
        user = None
        
        if query.isdigit():
            user_id = int(query)
            user = db.get_user(user_id)
        else:
            username = query.lstrip('@')
            user = db.get_user_by_username(username)
        
        if not user:
            bot.send_message(admin_id, t(lang, 'user_not_found'), reply_markup=admin_keyboard(lang))
            return
        
        is_blocked = db.is_user_blocked(user['user_id'])
        
        if is_blocked:
            if db.unblock_user(user['user_id']):
                bot.send_message(admin_id, t(lang, 'unblock_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'user_not_blocked_msg'),
                               reply_markup=admin_keyboard(lang))
        else:
            if db.block_user(user['user_id'], admin_id, "Block panel"):
                bot.send_message(admin_id, t(lang, 'block_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'user_already_blocked'),
                               reply_markup=admin_keyboard(lang))
        
    except Exception as e:
        logger.error(f"Block user error: {e}")
        bot.send_message(admin_id, f"❌ Error: {e}", reply_markup=admin_keyboard(lang))

def show_message_logs(admin_id: int, lang: str):
    """Показ логов сообщений"""
    show_text = admin_modes.get(admin_id, {}).get('show_text', True) if isinstance(admin_modes.get(admin_id), dict) else True
    messages = db.get_recent_messages(limit=10, include_text=show_text)
    
    if not messages:
        bot.send_message(admin_id, t(lang, 'no_logs'), reply_markup=get_admin_log_keyboard(show_text, lang))
        return
    
    logs_text = f"{t(lang, 'logs')}:\n\n"
    
    for i, msg in enumerate(messages, 1):
        sender_name = msg.get('sender_name', '?')
        receiver_name = msg.get('receiver_name', '?')
        
        logs_text += f"{i}. {format_time(msg['timestamp'], lang)}\n"
        logs_text += f"   👤 Отправитель: {msg['sender_id']} - {sender_name}\n"
        logs_text += f"   🎯 Получатель: {msg['receiver_id']} - {receiver_name}\n"
        logs_text += f"   📝 Тип: {msg['message_type']}\n"
        
        if msg['text']:
            logs_text += f"   💬 Текст: {msg['text']}\n"
        
        logs_text += "\n"
    
    bot.send_message(admin_id, logs_text, reply_markup=get_admin_log_keyboard(show_text, lang))

def show_support_tickets(admin_id: int, lang: str):
    """Показ тикетов поддержки"""
    tickets = db.get_open_support_tickets()
    
    if not tickets:
        bot.send_message(admin_id, t(lang, 'no_tickets'), reply_markup=admin_keyboard(lang))
        return
    
    tickets_text = f"{t(lang, 'tickets')} ({len(tickets)}):\n\n"
    
    for i, ticket in enumerate(tickets, 1):
        tickets_text += f"{i}. Тикет #{ticket['id']}\n"
        tickets_text += f"   👤 Пользователь: {ticket['user_id']} - {ticket['first_name']}\n"
        tickets_text += f"   📱 Username: {f'@{ticket['username']}' if ticket['username'] else 'нет'}\n"
        tickets_text += f"   📅 Создан: {format_time(ticket['created_at'], lang)}\n"
        
        if ticket['message']:
            preview = ticket['message'][:100] + "..." if len(ticket['message']) > 100 else ticket['message']
            tickets_text += f"   💬 Сообщение: {preview}\n"
        
        tickets_text += f"   📝 Тип: {ticket['message_type']}\n\n"
    
    bot.send_message(admin_id, tickets_text, reply_markup=admin_keyboard(lang))

def show_admin_settings(admin_id: int, lang: str):
    """Показ настроек админа"""
    channel_status = "✅ Настроен" if CHANNEL and CHANNEL != "" else "❌ Не настроен"
    
    settings_text = t(lang, 'admin_settings',
                     notifications="✅ Включены",
                     channel_status=channel_status,
                     antispam=ANTISPAM_INTERVAL)
    
    bot.send_message(admin_id, settings_text, reply_markup=admin_keyboard(lang))

def create_backup(admin_id: int, lang: str):
    """Создание бэкапа базы данных"""
    try:
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        with open(DB_PATH, 'rb') as f:
            db_content = f.read()
        
        bio = BytesIO(db_content)
        bio.name = backup_filename
        
        bot.send_document(admin_id, bio, 
                         caption=f"💾 Database backup\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        bot.send_message(admin_id, f"❌ Backup error: {e}")

def export_users_data(admin_id: int, lang: str):
    """Экспорт данных пользователей"""
    try:
        csv_content = db.export_users_data()
        bio = BytesIO(csv_content.encode('utf-8'))
        bio.name = f"users_export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        bot.send_document(admin_id, bio, caption=t(lang, 'export_complete'))
        
    except Exception as e:
        logger.error(f"Export users error: {e}")
        bot.send_message(admin_id, f"❌ Export error: {e}")

def export_messages_data(admin_id: int, lang: str):
    """Экспорт данных сообщений"""
    try:
        csv_content = db.export_messages_data()
        bio = BytesIO(csv_content.encode('utf-8'))
        bio.name = f"messages_export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        bot.send_document(admin_id, bio, caption=t(lang, 'export_complete'))
        
    except Exception as e:
        logger.error(f"Export messages error: {e}")
        bot.send_message(admin_id, f"❌ Export error: {e}")

def export_stats_data(admin_id: int, lang: str):
    """Экспорт статистики"""
    try:
        stats = db.get_admin_stats()
        
        stats_text = f"""📊 Anony SMS Bot Statistics
📅 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}

Main metrics:
├ Total users: {stats['total_users']}
├ Active today: {stats['today_active']}
├ Total messages: {stats['total_messages']}
├ Messages in 24h: {stats['messages_24h']}
├ New in 24h: {stats['new_users_24h']}
├ Blocked: {stats['blocked_users']}
├ Open tickets: {stats['open_tickets']}
└ Avg. activity per hour: {stats['avg_hourly']}

Detailed statistics:
├ Users this week: {stats['users_week']}
├ Messages this week: {stats['messages_week']}
├ Active this week: {stats['active_week']}
├ Retention (30 days): {stats['retention_30d']}%
└ Conversion to messages: {stats['conversion_rate']}%
"""
        
        bio = BytesIO(stats_text.encode('utf-8'))
        bio.name = f"stats_export_{datetime.now().strftime('%Y%m%d')}.txt"
        
        bot.send_document(admin_id, bio, caption=t(lang, 'export_complete'))
        
    except Exception as e:
        logger.error(f"Export stats error: {e}")
        bot.send_message(admin_id, f"❌ Export error: {e}")

# ====== FLASK РОУТЫ ======
@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик вебхука Telegram"""
    try:
        if request.headers.get('content-type') == 'application/json':
            json_string = request.get_data(as_text=True)
            update = types.Update.de_json(json_string)
            bot.process_new_updates([update])
            return 'OK', 200
        return 'Invalid content type', 400
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return 'ERROR', 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка здоровья приложения"""
    try:
        stats = db.get_admin_stats()
        return jsonify({
            'status': 'ok', 
            'time': datetime.now().isoformat(),
            'bot': 'Anony SMS',
            'version': '10.0',
            'users': stats['total_users'],
            'messages': stats['total_messages'],
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    """Пинг для поддержания активности"""
    return jsonify({'status': 'active', 'timestamp': time.time()})

# ====== МОНИТОРИНГ ======
def monitor_bot():
    """Мониторинг состояния бота"""
    while True:
        try:
            # Проверка целостности БД
            try:
                with db.get_connection() as conn:
                    c = conn.cursor()
                    c.execute('PRAGMA integrity_check')
                    result = c.fetchone()
                    if result[0] != 'ok':
                        logger.warning(f"DB integrity issue: {result[0]}")
            except Exception as e:
                logger.error(f"DB check error: {e}")
            
            # Очистка старых кэшей
            current_time = time.time()
            keys_to_delete = []
            for key, timestamp in session_timestamps.items():
                if current_time - timestamp > SESSION_TIMEOUT * 2:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del session_timestamps[key]
                if key in user_sessions:
                    del user_sessions[key]
                if key in admin_modes:
                    del admin_modes[key]
            
            time.sleep(3600)  # Проверка каждый час
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(300)

# ====== ЗАПУСК БОТА ======
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Anony SMS Bot v10.0 - Ultimate Professional Edition")
    logger.info("=" * 60)
    
    # Проверка токена
    if not TOKEN:
        logger.error("❌ Bot token not found! Set PLAY environment variable.")
        sys.exit(1)
    
    try:
        bot_info = bot.get_me()
        logger.info(f"🤖 Bot: @{bot_info.username} ({bot_info.first_name})")
        logger.info(f"👑 Admin ID: {ADMIN_ID}")
        logger.info(f"📢 Channel: {CHANNEL if CHANNEL else 'Not configured'}")
        logger.info(f"🌐 Webhook: {WEBHOOK_HOST if WEBHOOK_HOST else 'Polling mode'}")
        logger.info(f"💾 Database: {DB_PATH}")
    except Exception as e:
        logger.error(f"❌ Bot initialization error: {e}")
        sys.exit(1)
    
    # Запуск мониторинга
    try:
        monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
        monitor_thread.start()
        logger.info("✅ Monitoring started")
    except Exception as e:
        logger.error(f"❌ Background services error: {e}")
    
    # Запуск бота
    try:
        if WEBHOOK_HOST:
            logger.info(f"🌐 Setting up webhook for {WEBHOOK_HOST}")
            
            try:
                bot.remove_webhook()
                time.sleep(1)
            except:
                pass
            
            bot.set_webhook(
                url=f"{WEBHOOK_HOST}/webhook",
                max_connections=100,
                timeout=60,
                drop_pending_updates=True,
                allowed_updates=None
            )
            logger.info("✅ Webhook configured successfully")
            
            # Запуск Flask
            app.run(
                host='0.0.0.0',
                port=PORT,
                debug=False,
                threaded=True,
                use_reloader=False
            )
            
        else:
            logger.info("🔄 Starting in polling mode")
            bot.remove_webhook()
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=20,
                long_polling_timeout=20,
                logger_level=logging.INFO
            )
            
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
