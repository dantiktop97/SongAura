#!/usr/bin/env python3
"""
Anony SMS Bot - Ultimate Professional Version v7.0
Fully functional with all security features and optimizations
Total lines: 3500+
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
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import requests
import base64
from typing import Dict, List, Optional, Any, Tuple

from flask import Flask, request, jsonify, Response
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
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_MESSAGE_LENGTH = 4000
SESSION_TIMEOUT = 300  # 5 минут

# Капча конфиг
CAPTCHA_ENABLED = True
CAPTCHA_AFTER_ATTEMPTS = 5

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
captcha_data = {}
user_attempts = {}
rate_limit_cache = {}
achievements_cache = {}
file_cache = {}
session_timestamps = {}

# ====== ПЕРЕВОДЫ (ПОЛНЫЕ) ======
TRANSLATIONS = {
    'ru': {
        # Основные
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
        
        'my_link': """🔗 <b>Твоя уникальная ссылка для анонимок:</b>

<code>{link}</code>

<i>📤 Поделись с друзьями в:
• Чатах 💬
• Соцсетях 🌐
• Сторис 📲

🎭 Каждый переход — новый анонимный отправитель!
🔥 Чем больше делишься, тем больше тайн узнаёшь 😏</i>""",
        
        'profile': """👤 <b>Твой профиль</b>

<b>📊 Идентификация:</b>
├ ID: <code>{user_id}</code>
├ Имя: <b>{first_name}</b>
└ Юзернейм: {username}

<b>📈 Статистика:</b>
├ 📨 Получено: <b>{received}</b>
├ 📤 Отправлено: <b>{sent}</b>
├ 🔗 Переходов: <b>{clicks}</b>
└ ⏱️ Сред. время ответа: <b>{response_time}</b>

<b>⚙️ Настройки:</b>
├ Приём сообщений: {receive_status}
├ Язык: {language}
└ Последняя активность: {last_active}

<b>📊 Детальная статистика:</b>
├ Пик активности: <b>{peak_hour}:00</b>
├ Самый активный день: <b>{active_day}</b>
└ Любимый тип: <b>{fav_type}</b>

<b>🏆 Достижения:</b>
{achievements}

<b>🔗 Твоя ссылка:</b>
<code>{link}</code>""",
        
        'anonymous_message': """📨 <b>Ты получил анонимное сообщение!</b>

<i>💭 Кто-то отправил тебе тайное послание...</i>

{text}

<i>🎭 Отправитель останется неизвестным...</i>

<b>💌 Хочешь ответить анонимно?</b>
Нажми кнопку «Ответить» ниже 👇""",
        
        'message_sent': """✅ <b>Сообщение отправлено анонимно!</b>

<i>🎯 Получатель: <b>{receiver_name}</b>
🔒 Твоя личность: <b>скрыта</b>
💭 Сообщение доставлено успешно!</i>

<b>Хочешь отправить ещё?</b>
Просто продолжай писать ✍️""",
        
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
        'qr_code': """📱 <b>Твой персональный QR-код</b>

<i>Сканируй и отправляй анонимные сообщения мгновенно! ⚡</i>

<b>🔗 Ссылка:</b>
<code>{link}</code>""",
        
        # Статистика пользователя
        'user_stats': """📊 <b>Твоя детальная статистика</b>

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
└ Конверсия в сообщения: <b>{conversion_rate}%</b>

<b>📱 ПОЛЬЗОВАТЕЛИ ПО ДНЯМ:</b>
{users_by_day}

<b>📨 СООБЩЕНИЯ ПО ДНЯМ:</b>
{messages_by_day}

<b>👥 ТОП-10 АКТИВНЫХ ПОЛЬЗОВАТЕЛЕЙ:</b>
{top_users}""",
        
        'broadcast_start': """📢 <b>Создание рассылки</b>

<i>Отправь сообщение которое будет отправлено всем пользователям.</i>

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
        
        'direct_message': """✉️ <b>Отправь сообщение для пользователя</b> <code>{user_id}</code>

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
        'send_anonymous_to': "Отправь анонимное сообщение",
        'send_anonymous_description': "Напиши сообщение, фото, видео или голосовое сообщение",
        'send_reply': "Отправь ответное сообщение",
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
        
        # Языки
        'lang_ru': "🇷🇺 Русский",
        'lang_en': "🇺🇸 English",
        
        # Блокировка
        'block_instruction': "🚫 <b>Блокировка/Разблокировка пользователя</b>\n\nВведите ID пользователя или юзернейм (без @):",
        'block_success': "✅ Пользователь <code>{user_id}</code> заблокирован.",
        'unblock_success': "✅ Пользователь <code>{user_id}</code> разблокирован.",
        'block_already': "✅ Пользователь уже заблокирован.",
        'user_not_blocked_msg': "✅ Пользователь не был заблокирован.",
        
        # История
        'history': "📜 <b>История сообщений</b>\n\n<i>Последние 20 сообщений:</i>",
        'history_empty': "📜 <b>У тебя пока нет сообщений</b>\n\n<i>Начни общение, отправив первую анонимку!</i>",
        'history_item': """<b>{index}. {direction} {name}</b> <i>({time})</i>
💬 <i>{preview}</i>""",
        'history_incoming': "⬇️ От",
        'history_outgoing': "⬆️ Кому",
        
        # Экспорт
        'export_instruction': "📤 <b>Экспорт данных</b>\n\n<i>Выберите что экспортировать:</i>",
        'export_users': "👥 Экспорт пользователей",
        'export_messages': "📨 Экспорт сообщений",
        'export_stats': "📊 Экспорт статистики",
        'export_processing': "⏳ <b>Экспорт данных...</b>\n\n<i>Пожалуйста, подождите.</i>",
        'export_complete': "✅ <b>Экспорт завершен!</b>\n\n<i>Данные успешно сохранены.</i>",
        
        # Капча
        'captcha_required': """🔒 <b>Требуется проверка безопасности</b>

<i>Введите текст с картинки ниже:</i>
<i>Попытка {attempt}/{max_attempts}</i>""",
        'captcha_correct': "✅ Капча пройдена!",
        'captcha_incorrect': "❌ Неверная капча, попробуйте снова.",
        'captcha_failed': "❌ Вы превысили максимальное количество попыток. Попробуйте позже.",
        'captcha_timeout': "⏰ Время на ввод капчи истекло.",
        
        # Ошибки
        'file_too_large': "❌ Файл слишком большой (максимум {max_size}MB).",
        'message_too_long': "❌ Сообщение слишком длинное (максимум {max_length} символов).",
        'rate_limit_exceeded': "⏳ Слишком много запросов. Подождите {seconds} секунд.",
        'content_blocked': "❌ Сообщение содержит запрещённые слова.",
        'session_expired': "⏰ Сессия истекла. Начните заново.",
        
        # Достижения
        'achievement_first_message': "🎯 Первый шаг - Отправил первое сообщение",
        'achievement_first_received': "💌 Первое послание - Получил первое сообщение",
        'achievement_popular_10': "⭐ Популярный - Получил 10+ сообщений",
        'achievement_popular_50': "🌟 Очень популярный - Получил 50+ сообщений",
        'achievement_popular_100': "🏆 Суперзвезда - Получил 100+ сообщений",
        'achievement_active_10': "⚡ Активный - Отправил 10+ сообщений",
        'achievement_active_50': "🔥 Очень активный - Отправил 50+ сообщений",
        'achievement_active_100': "🚀 Мастер общения - Отправил 100+ сообщений",
        'achievement_sharer_10': "📤 Делюсь - 10+ переходов по ссылке",
        'achievement_sharer_50': "📢 Активно делюсь - 50+ переходов",
        'achievement_sharer_100': "🎯 Вирусная ссылка - 100+ переходов",
        'achievement_veteran_7': "🛡️ Ветеран - Использует бота 7+ дней",
        'achievement_veteran_30': "🛡️ Опытный - Использует бота 30+ дней",
        'achievement_veteran_90': "🛡️ Легенда - Использует бота 90+ дней",
        'achievement_fast_reply': "⚡ Быстрый ответ - Ответил менее чем за 1 минуту",
        'achievement_all_types': "🎭 Разносторонний - Отправил все типы сообщений",
        
        # Модерация
        'moderation_warning': "⚠️ Ваше сообщение было заблокировано системой модерации.",
        'moderation_alert_admin': "🚨 Обнаружено подозрительное сообщение от пользователя {user_id}",
        
        # Системные
        'system_error': "❌ Произошла системная ошибка. Пожалуйста, попробуйте позже.",
        'maintenance': "🔧 Бот находится на техническом обслуживании. Приносим извинения за неудобства.",
        'update_available': "🔄 Доступно обновление бота. Некоторые функции могут быть временно недоступны.",
    },
    
    'en': {
        # Main
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
        
        'my_link': """🔗 <b>Your unique link for anonymous messages:</b>

<code>{link}</code>

<i>📤 Share with friends in:
• Chats 💬
• Social networks 🌐
• Stories 📲

🎭 Every click — a new anonymous sender!
🔥 The more you share, the more secrets you discover 😏</i>""",
        
        'profile': """👤 <b>Your profile</b>

<b>📊 Identification:</b>
├ ID: <code>{user_id}</code>
├ Name: <b>{first_name}</b>
└ Username: {username}

<b>📈 Statistics:</b>
├ 📨 Received: <b>{received}</b>
├ 📤 Sent: <b>{sent}</b>
├ 🔗 Clicks: <b>{clicks}</b>
└ ⏱️ Avg. response time: <b>{response_time}</b>

<b>⚙️ Settings:</b>
├ Receive messages: {receive_status}
├ Language: {language}
└ Last active: {last_active}

<b>📊 Detailed statistics:</b>
├ Peak activity: <b>{peak_hour}:00</b>
├ Most active day: <b>{active_day}</b>
└ Favorite type: <b>{fav_type}</b>

<b>🏆 Achievements:</b>
{achievements}

<b>🔗 Your link:</b>
<code>{link}</code>""",
        
        'anonymous_message': """📨 <b>You received an anonymous message!</b>

<i>💭 Someone sent you a secret message...</i>

{text}

<i>🎭 The sender will remain unknown...</i>

<b>💌 Want to reply anonymously?</b>
Click the "Reply" button below 👇""",
        
        'message_sent': """✅ <b>Message sent anonymously!</b>

<i>🎯 Recipient: <b>{receiver_name}</b>
🔒 Your identity: <b>hidden</b>
💭 Message delivered successfully!</i>

<b>Want to send more?</b>
Just keep writing ✍️""",
        
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
└ Conversion to messages: <b>{conversion_rate}%</b>

<b>📱 USERS BY DAY:</b>
{users_by_day}

<b>📨 MESSAGES BY DAY:</b>
{messages_by_day}

<b>👥 TOP 10 ACTIVE USERS:</b>
{top_users}""",
        
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
        
        # Languages
        'lang_ru': "🇷🇺 Russian",
        'lang_en': "🇺🇸 English",
        
        # Block
        'block_instruction': "🚫 <b>Block/Unblock user</b>\n\nEnter user ID or username (without @):",
        'block_success': "✅ User <code>{user_id}</code> blocked.",
        'unblock_success': "✅ User <code>{user_id}</code> unblocked.",
        'block_already': "✅ User already blocked.",
        'user_not_blocked_msg': "✅ User was not blocked.",
        
        # History
        'history': "📜 <b>Message history</b>\n\n<i>Last 20 messages:</i>",
        'history_empty': "📜 <b>You don't have messages yet</b>\n\n<i>Start communication by sending your first anonymous message!</i>",
        'history_item': """<b>{index}. {direction} {name}</b> <i>({time})</i>
💬 <i>{preview}</i>""",
        'history_incoming': "⬇️ From",
        'history_outgoing': "⬆️ To",
        
        # Export
        'export_instruction': "📤 <b>Export data</b>\n\n<i>Choose what to export:</i>",
        'export_users': "👥 Export users",
        'export_messages': "📨 Export messages",
        'export_stats': "📊 Export statistics",
        'export_processing': "⏳ <b>Exporting data...</b>\n\n<i>Please wait.</i>",
        'export_complete': "✅ <b>Export completed!</b>\n\n<i>Data successfully saved.</i>",
        
        # Captcha
        'captcha_required': """🔒 <b>Security verification required</b>

<i>Enter the text from the image below:</i>
<i>Attempt {attempt}/{max_attempts}</i>""",
        'captcha_correct': "✅ Captcha passed!",
        'captcha_incorrect': "❌ Incorrect captcha, try again.",
        'captcha_failed': "❌ You have exceeded the maximum number of attempts. Try again later.",
        'captcha_timeout': "⏰ Time to enter captcha has expired.",
        
        # Errors
        'file_too_large': "❌ File is too large (maximum {max_size}MB).",
        'message_too_long': "❌ Message is too long (maximum {max_length} characters).",
        'rate_limit_exceeded': "⏳ Too many requests. Wait {seconds} seconds.",
        'content_blocked': "❌ Message contains forbidden words.",
        'session_expired': "⏰ Session expired. Start over.",
        
        # Achievements
        'achievement_first_message': "🎯 First Step - Sent first message",
        'achievement_first_received': "💌 First Message - Received first message",
        'achievement_popular_10': "⭐ Popular - Received 10+ messages",
        'achievement_popular_50': "🌟 Very Popular - Received 50+ messages",
        'achievement_popular_100': "🏆 Superstar - Received 100+ messages",
        'achievement_active_10': "⚡ Active - Sent 10+ messages",
        'achievement_active_50': "🔥 Very Active - Sent 50+ messages",
        'achievement_active_100': "🚀 Communication Master - Sent 100+ messages",
        'achievement_sharer_10': "📤 Sharer - 10+ link clicks",
        'achievement_sharer_50': "📢 Active Sharer - 50+ link clicks",
        'achievement_sharer_100': "🎯 Viral Link - 100+ link clicks",
        'achievement_veteran_7': "🛡️ Veteran - Using bot 7+ days",
        'achievement_veteran_30': "🛡️ Experienced - Using bot 30+ days",
        'achievement_veteran_90': "🛡️ Legend - Using bot 90+ days",
        'achievement_fast_reply': "⚡ Fast Reply - Replied in less than 1 minute",
        'achievement_all_types': "🎭 Versatile - Sent all message types",
        
        # Moderation
        'moderation_warning': "⚠️ Your message has been blocked by the moderation system.",
        'moderation_alert_admin': "🚨 Suspicious message detected from user {user_id}",
        
        # System
        'system_error': "❌ A system error occurred. Please try again later.",
        'maintenance': "🔧 The bot is under maintenance. We apologize for the inconvenience.",
        'update_available': "🔄 Bot update available. Some features may be temporarily unavailable.",
    }
}

# ====== УТИЛИТЫ ======
def t(lang: str, key: str, **kwargs) -> str:
    """Функция перевода с fallback на русский"""
    if lang not in TRANSLATIONS:
        lang = 'ru'
    if key not in TRANSLATIONS[lang]:
        if 'ru' in TRANSLATIONS and key in TRANSLATIONS['ru']:
            return TRANSLATIONS['ru'][key].format(**kwargs) if kwargs else TRANSLATIONS['ru'][key]
        return key
    return TRANSLATIONS[lang][key].format(**kwargs) if kwargs else TRANSLATIONS[lang][key]

def format_time(timestamp: Optional[int], lang: str = 'ru') -> str:
    """Форматирование времени"""
    if not timestamp:
        return t(lang, 'never')
    
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
    elif diff.days < 7:
        return t(lang, 'days_ago', days=diff.days)
    else:
        return dt.strftime("%d.%m.%Y")

def generate_link(user_id: int) -> str:
    """Генерация ссылки на бота с user_id"""
    try:
        bot_username = bot.get_me().username
        return f"https://t.me/{bot_username}?start={user_id}"
    except:
        return f"https://t.me/{bot.get_me().username}?start={user_id}"

def check_rate_limit(user_id: int) -> Tuple[bool, int]:
    """Проверка ограничения скорости запросов"""
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

def generate_captcha() -> Tuple[Image.Image, str]:
    """Генерация капчи"""
    # Создаем простую текстовую капчу
    captcha_text = ''.join(random.choices('ABCDEFGHJKLMNPQRSTUVWXYZ23456789', k=6))
    
    # Создаем изображение
    image = Image.new('RGB', (200, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    
    # Добавляем текст
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except:
        font = ImageFont.load_default()
    
    # Накладываем шум
    for _ in range(100):
        x = random.randint(0, 200)
        y = random.randint(0, 80)
        draw.point((x, y), fill=(
            random.randint(150, 255),
            random.randint(150, 255),
            random.randint(150, 255)
        ))
    
    # Рисуем текст со смещением
    for i, char in enumerate(captcha_text):
        x = 20 + i * 30 + random.randint(-5, 5)
        y = 20 + random.randint(-5, 5)
        draw.text((x, y), char, font=font, fill=(
            random.randint(0, 100),
            random.randint(0, 100),
            random.randint(0, 100)
        ))
    
    # Добавляем линии
    for _ in range(5):
        x1 = random.randint(0, 200)
        y1 = random.randint(0, 80)
        x2 = random.randint(0, 200)
        y2 = random.randint(0, 80)
        draw.line((x1, y1, x2, y2), fill=(
            random.randint(100, 200),
            random.randint(100, 200),
            random.randint(100, 200)
        ), width=1)
    
    return image, captcha_text

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
        types.KeyboardButton(t(lang, 'btn_admin_block')),
        types.KeyboardButton(t(lang, 'btn_admin_logs')),
        types.KeyboardButton(t(lang, 'btn_admin_tickets')),
        types.KeyboardButton(t(lang, 'btn_admin_settings')),
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

def get_message_reply_keyboard(target_id: int, lang: str = 'ru') -> types.InlineKeyboardMarkup:
    """Клавиатура для ответа на сообщение"""
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(t(lang, 'btn_reply'), callback_data=f"reply_{target_id}"),
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
        types.InlineKeyboardButton(t(lang, 'btn_toggle_text') if show_text else t(lang, 'btn_show_text'), 
                                 callback_data="toggle_text")
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
        conn.execute('PRAGMA cache_size=-10000')
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
                    is_premium INTEGER DEFAULT 0
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
            
            # Блокировки
            c.execute('''
                CREATE TABLE IF NOT EXISTS blocked_users (
                    user_id INTEGER PRIMARY KEY,
                    blocked_at INTEGER,
                    blocked_by INTEGER,
                    reason TEXT,
                    UNIQUE(user_id)
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
            
            # Логи для админа
            c.execute('''
                CREATE TABLE IF NOT EXISTS admin_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    log_type TEXT,
                    user_id INTEGER,
                    target_id INTEGER,
                    details TEXT,
                    timestamp INTEGER,
                    ip_address TEXT
                )
            ''')
            
            # Настройки бота
            c.execute('''
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at INTEGER
                )
            ''')
            
            c.execute('''
                INSERT OR IGNORE INTO bot_settings (key, value, updated_at) 
                VALUES ('notifications_enabled', '1', ?)
            ''', (int(time.time()),))
            
            # Статистика пользователя
            c.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    messages_by_hour TEXT DEFAULT '{}',
                    messages_by_day TEXT DEFAULT '{}',
                    message_types TEXT DEFAULT '{}',
                    total_time_spent INTEGER DEFAULT 0,
                    last_session_start INTEGER,
                    achievements TEXT DEFAULT '[]',
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
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
            
            # Клики по ссылкам
            c.execute('''
                CREATE TABLE IF NOT EXISTS link_clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    clicker_id INTEGER,
                    timestamp INTEGER,
                    user_agent TEXT
                )
            ''')
            
            # Капчи
            c.execute('''
                CREATE TABLE IF NOT EXISTS captcha_attempts (
                    user_id INTEGER PRIMARY KEY,
                    attempts INTEGER DEFAULT 0,
                    last_attempt INTEGER,
                    captcha_text TEXT
                )
            ''')
            
            # Модерация
            c.execute('''
                CREATE TABLE IF NOT EXISTS moderation_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message TEXT,
                    reason TEXT,
                    action TEXT,
                    timestamp INTEGER
                )
            ''')
            
            # Индексы для производительности
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_receiver ON messages(receiver_id)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_users_created ON users(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_status ON support_tickets(status)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_tickets_created ON support_tickets(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_blocked_users ON blocked_users(user_id)')
            
            logger.info("✅ Database initialized with indexes")
    
    def _get_cached_user(self, user_id: int):
        """Получение пользователя с кэшированием"""
        now = time.time()
        if user_id in self._user_cache:
            if now - self._user_cache_time.get(user_id, 0) < 60:  # TTL 60 секунд
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
        """Получение статистики админа с кэшированием"""
        now = time.time()
        if 'admin_stats' in self._stats_cache:
            if now - self._stats_cache_time.get('admin_stats', 0) < 60:  # TTL 60 секунд
                return self._stats_cache['admin_stats']
        
        stats = self._get_admin_stats_impl()
        self._stats_cache['admin_stats'] = stats
        self._stats_cache_time['admin_stats'] = now
        return stats
    
    def _get_admin_stats_impl(self):
        """Реализация получения статистики админа"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Основные метрики
            c.execute('SELECT COUNT(*) FROM users')
            total_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages')
            total_messages = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM blocked_users')
            blocked_users = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM users WHERE created_at > ?', 
                     (int(time.time()) - 86400,))
            new_users_24h = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 86400,))
            messages_24h = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM support_tickets WHERE status = "open"')
            open_tickets = c.fetchone()[0]
            
            # Активные сегодня
            today_start = int(time.time()) - 86400
            c.execute('SELECT COUNT(DISTINCT user_id) FROM users WHERE last_active > ?', (today_start,))
            today_active = c.fetchone()[0]
            
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
            
            # Средняя активность в час
            c.execute('SELECT COUNT(*) / 24.0 FROM messages WHERE timestamp > ?', 
                     (int(time.time()) - 86400,))
            avg_hourly_result = c.fetchone()[0]
            avg_hourly = round(avg_hourly_result, 2) if avg_hourly_result else 0
            
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
            
            # Пользователи по дням
            users_by_day_data = {}
            for i in range(7):
                day_start = int(time.time()) - (i * 86400) - 86400
                day_end = int(time.time()) - (i * 86400)
                c.execute('SELECT COUNT(*) FROM users WHERE created_at BETWEEN ? AND ?', 
                         (day_start, day_end))
                count = c.fetchone()[0]
                day_name = (datetime.fromtimestamp(day_end)).strftime('%d.%m')
                users_by_day_data[day_name] = count
            
            users_by_day = "\n".join([f"├ {day}: <b>{count}</b>" for day, count in users_by_day_data.items()])
            
            # Сообщения по дням
            messages_by_day_data = {}
            for i in range(7):
                day_start = int(time.time()) - (i * 86400) - 86400
                day_end = int(time.time()) - (i * 86400)
                c.execute('SELECT COUNT(*) FROM messages WHERE timestamp BETWEEN ? AND ?', 
                         (day_start, day_end))
                count = c.fetchone()[0]
                day_name = (datetime.fromtimestamp(day_end)).strftime('%d.%m')
                messages_by_day_data[day_name] = count
            
            messages_by_day = "\n".join([f"├ {day}: <b>{count}</b>" for day, count in messages_by_day_data.items()])
            
            # Топ-10 активных пользователей
            c.execute('''
                SELECT u.user_id, u.first_name, u.username, 
                       COUNT(m.id) as message_count
                FROM users u
                LEFT JOIN messages m ON u.user_id = m.sender_id OR u.user_id = m.receiver_id
                GROUP BY u.user_id
                ORDER BY message_count DESC
                LIMIT 10
            ''')
            top_users_rows = c.fetchall()
            
            top_users_lines = []
            for i, row in enumerate(top_users_rows, 1):
                username = f"@{row['username']}" if row['username'] else "no"
                top_users_lines.append(f"{i}. {row['first_name']} ({username}): {row['message_count']} msgs")
            
            top_users = "\n".join(top_users_lines) if top_users_lines else "No data"
            
            return {
                'total_users': total_users,
                'today_active': today_active,
                'total_messages': total_messages,
                'messages_24h': messages_24h,
                'new_users_24h': new_users_24h,
                'blocked_users': blocked_users,
                'open_tickets': open_tickets,
                'users_week': users_week,
                'messages_week': messages_week,
                'active_week': active_week,
                'avg_hourly': avg_hourly,
                'retention_30d': retention_30d,
                'conversion_rate': conversion_rate,
                'users_by_day': users_by_day,
                'messages_by_day': messages_by_day,
                'top_users': top_users
            }
    
    # ====== ОСНОВНЫЕ МЕТОДЫ ======
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
            
            # Очищаем кэш
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
            # Используем параметризованный запрос для безопасности
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
            c.execute('SELECT user_id FROM users')
            rows = c.fetchall()
            return [row[0] for row in rows]
    
    def get_all_users_count(self) -> int:
        """Получение количества всех пользователей"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM users')
            return c.fetchone()[0]
    
    def get_today_active_users(self) -> int:
        """Получение количества активных сегодня пользователей"""
        with self.get_connection() as conn:
            c = conn.cursor()
            today = int(time.time()) - 86400
            c.execute('SELECT COUNT(DISTINCT user_id) FROM messages WHERE timestamp > ?', (today,))
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
            
            # Обновляем статистику
            self.update_user_stats(sender_id, message_type)
            self.update_user_stats(receiver_id, message_type)
            
            # Проверяем достижения
            self.check_achievements(sender_id)
            self.check_achievements(receiver_id)
            
            return message_id
    
    def update_user_stats(self, user_id: int, message_type: str):
        """Обновление статистики пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = datetime.now()
            hour = now.hour
            day = now.strftime('%A')
            
            c.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            
            if not row:
                messages_by_hour = {str(hour): 1}
                messages_by_day = {day: 1}
                message_types = {message_type: 1}
                
                c.execute('''
                    INSERT INTO user_stats 
                    (user_id, messages_by_hour, messages_by_day, message_types, last_session_start) 
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, json.dumps(messages_by_hour), json.dumps(messages_by_day), 
                      json.dumps(message_types), int(time.time())))
            else:
                messages_by_hour = json.loads(row['messages_by_hour'])
                messages_by_day = json.loads(row['messages_by_day'])
                message_types = json.loads(row['message_types'])
                
                hour_key = str(hour)
                messages_by_hour[hour_key] = messages_by_hour.get(hour_key, 0) + 1
                messages_by_day[day] = messages_by_day.get(day, 0) + 1
                message_types[message_type] = message_types.get(message_type, 0) + 1
                
                if row['last_session_start']:
                    session_time = int(time.time()) - row['last_session_start']
                    total_time = row['total_time_spent'] + min(session_time, 3600)
                else:
                    total_time = row['total_time_spent']
                
                c.execute('''
                    UPDATE user_stats 
                    SET messages_by_hour = ?, messages_by_day = ?, message_types = ?, 
                        total_time_spent = ?, last_session_start = ?
                    WHERE user_id = ?
                ''', (json.dumps(messages_by_hour), json.dumps(messages_by_day), 
                      json.dumps(message_types), total_time, int(time.time()), user_id))
    
    def check_achievements(self, user_id: int):
        """Проверка и выдача достижений"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            # Получаем текущие достижения
            c.execute('SELECT achievements FROM user_stats WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            current_achievements = json.loads(row['achievements']) if row and row['achievements'] else []
            
            # Получаем статистику пользователя
            user = self.get_user(user_id)
            if not user:
                return
            
            # Статистика сообщений
            c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ?', (user_id,))
            sent_count = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE receiver_id = ?', (user_id,))
            received_count = c.fetchone()[0]
            
            # Проверяем каждое достижение
            new_achievements = []
            achievement_map = {
                'first_message': sent_count >= 1,
                'first_received': received_count >= 1,
                'popular_10': received_count >= 10,
                'popular_50': received_count >= 50,
                'popular_100': received_count >= 100,
                'active_10': sent_count >= 10,
                'active_50': sent_count >= 50,
                'active_100': sent_count >= 100,
                'sharer_10': user['link_clicks'] >= 10,
                'sharer_50': user['link_clicks'] >= 50,
                'sharer_100': user['link_clicks'] >= 100,
                'veteran_7': time.time() - user['created_at'] >= 604800,  # 7 дней
                'veteran_30': time.time() - user['created_at'] >= 2592000,  # 30 дней
                'veteran_90': time.time() - user['created_at'] >= 7776000,  # 90 дней
            }
            
            for achievement, condition in achievement_map.items():
                if condition and achievement not in current_achievements:
                    new_achievements.append(achievement)
            
            if new_achievements:
                # Добавляем новые достижения
                all_achievements = current_achievements + new_achievements
                c.execute('UPDATE user_stats SET achievements = ? WHERE user_id = ?',
                         (json.dumps(all_achievements), user_id))
                
                # Возвращаем новые достижения для уведомления
                return new_achievements
            
            return None
    
    def get_user_achievements(self, user_id: int) -> List[str]:
        """Получение достижений пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT achievements FROM user_stats WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if row and row['achievements']:
                return json.loads(row['achievements'])
            return []
    
    def get_user_messages_stats(self, user_id: int) -> Dict[str, int]:
        """Статистика сообщений пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            
            c.execute('SELECT COUNT(*) FROM messages WHERE sender_id = ?', (user_id,))
            sent_count = c.fetchone()[0]
            
            c.execute('SELECT COUNT(*) FROM messages WHERE receiver_id = ?', (user_id,))
            received_count = c.fetchone()[0]
            
            return {
                'messages_sent': sent_count,
                'messages_received': received_count
            }
    
    def get_user_detailed_stats(self, user_id: int) -> Optional[Dict]:
        """Детальная статистика пользователя"""
        user = self.get_user(user_id)
        if not user:
            return None
        
        with self.get_connection() as conn:
            c = conn.cursor()
            
            c.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,))
            stats_row = c.fetchone()
            
            stats = {
                'user': user,
                'messages_by_hour': {},
                'messages_by_day': {},
                'message_types': {},
                'total_time_spent': 0,
                'avg_response_time': 0,
                'achievements': []
            }
            
            if stats_row:
                stats['messages_by_hour'] = json.loads(stats_row['messages_by_hour'])
                stats['messages_by_day'] = json.loads(stats_row['messages_by_day'])
                stats['message_types'] = json.loads(stats_row['message_types'])
                stats['total_time_spent'] = stats_row['total_time_spent']
                
                if stats_row['achievements']:
                    stats['achievements'] = json.loads(stats_row['achievements'])
            
            # Время ответа
            c.execute('''
                SELECT m1.timestamp as sent_time, m2.timestamp as reply_time
                FROM messages m1
                JOIN messages m2 ON m2.replied_to = m1.id
                WHERE m1.receiver_id = ? AND m2.sender_id = ?
                ORDER BY m1.timestamp
            ''', (user_id, user_id))
            
            response_times = []
            for row in c.fetchall():
                response_time = row['reply_time'] - row['sent_time']
                if 0 < response_time < 3600:
                    response_times.append(response_time)
            
            if response_times:
                stats['avg_response_time'] = sum(response_times) / len(response_times)
            
            return stats
    
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
    
    def is_user_blocked(self, user_id: int) -> bool:
        """Проверка блокировки пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT 1 FROM blocked_users WHERE user_id = ?', (user_id,))
            return c.fetchone() is not None
    
    def block_user(self, user_id: int, admin_id: int, reason: str = "") -> bool:
        """Блокировка пользователя"""
        if user_id == ADMIN_ID:
            return False
        
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            try:
                c.execute('''
                    INSERT OR IGNORE INTO blocked_users (user_id, blocked_at, blocked_by, reason)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, now, admin_id, reason))
                self._clear_user_cache(user_id)
                return True
            except:
                return False
    
    def unblock_user(self, user_id: int) -> bool:
        """Разблокировка пользователя"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM blocked_users WHERE user_id = ?', (user_id,))
            success = c.rowcount > 0
            if success:
                self._clear_user_cache(user_id)
            return success
    
    def get_blocked_users_count(self) -> int:
        """Количество заблокированных пользователей"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM blocked_users')
            return c.fetchone()[0]
    
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
    
    def add_admin_log(self, log_type: str, user_id: int, target_id: Optional[int] = None,
                     details: str = "", ip_address: str = ""):
        """Добавление лога админа"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO admin_logs (log_type, user_id, target_id, details, timestamp, ip_address)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (log_type, user_id, target_id, details, int(time.time()), ip_address))
    
    def get_recent_logs(self, limit: int = 50) -> List[Dict]:
        """Получение последних логов"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT l.*, u.username, u.first_name 
                FROM admin_logs l
                LEFT JOIN users u ON l.user_id = u.user_id
                ORDER BY l.timestamp DESC LIMIT ?
            ''', (limit,))
            rows = c.fetchall()
            return [dict(row) for row in rows]
    
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Получение настройки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT value FROM bot_settings WHERE key = ?', (key,))
            row = c.fetchone()
            return row[0] if row else default
    
    def set_setting(self, key: str, value: str):
        """Установка настройки"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('INSERT OR REPLACE INTO bot_settings (key, value, updated_at) VALUES (?, ?, ?)', 
                     (key, value, int(time.time())))
    
    def track_link_click(self, user_id: int, clicker_id: int, user_agent: str = ""):
        """Отслеживание кликов по ссылке"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO link_clicks (user_id, clicker_id, timestamp, user_agent)
                VALUES (?, ?, ?, ?)
            ''', (user_id, clicker_id, int(time.time()), user_agent))
    
    def get_link_clicks_stats(self, user_id: int) -> Dict[str, int]:
        """Статистика кликов по ссылке"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM link_clicks WHERE user_id = ?', (user_id,))
            total_clicks = c.fetchone()[0]
            
            c.execute('SELECT COUNT(DISTINCT clicker_id) FROM link_clicks WHERE user_id = ?', (user_id,))
            unique_clickers = c.fetchone()[0]
            
            return {
                'total_clicks': total_clicks,
                'unique_clickers': unique_clickers
            }
    
    def add_captcha_attempt(self, user_id: int, captcha_text: str = ""):
        """Добавление попытки капчи"""
        with self.get_connection() as conn:
            c = conn.cursor()
            now = int(time.time())
            c.execute('''
                INSERT OR REPLACE INTO captcha_attempts 
                (user_id, attempts, last_attempt, captcha_text)
                VALUES (?, COALESCE((SELECT attempts FROM captcha_attempts WHERE user_id = ?), 0) + 1, ?, ?)
            ''', (user_id, user_id, now, captcha_text))
    
    def get_captcha_attempts(self, user_id: int) -> Tuple[int, Optional[str]]:
        """Получение попыток капчи"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT attempts, captcha_text FROM captcha_attempts WHERE user_id = ?', (user_id,))
            row = c.fetchone()
            if row:
                return row['attempts'], row['captcha_text']
            return 0, None
    
    def reset_captcha_attempts(self, user_id: int):
        """Сброс попыток капчи"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('DELETE FROM captcha_attempts WHERE user_id = ?', (user_id,))
    
    def add_moderation_log(self, user_id: int, message: str, reason: str, action: str):
        """Добавление лога модерации"""
        with self.get_connection() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO moderation_logs (user_id, message, reason, action, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, message, reason, action, int(time.time())))

db = Database()

# ====== ОБРАБОТЧИКИ КОМАНД ======
@bot.message_handler(commands=['start', 'lang', 'menu', 'stats', 'history', 'help', 'support'])
def start_command(message):
    """Обработчик команды /start и других"""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    logger.info(f"COMMAND: {message.text} from user_id={user_id}")
    
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
    
    # Регистрация/обновление пользователя
    db.register_user(user_id, username, first_name)
    db.update_last_active(user_id)
    
    # Обновление сессии
    session_timestamps[user_id] = time.time()
    
    args = message.text.split()
    
    # Обработка команды /lang
    if message.text.startswith('/lang'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'language'), reply_markup=language_keyboard())
        return
    
    # Обработка команды /menu
    if message.text.startswith('/menu'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    # Обработка команды /stats
    if message.text.startswith('/stats'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_user_stats(user_id, lang)
        return
    
    # Обработка команды /history
    if message.text.startswith('/history'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_user_history(user_id, lang)
        return
    
    # Обработка команды /help
    if message.text.startswith('/help'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        show_help(user_id, lang)
        return
    
    # Обработка команды /support
    if message.text.startswith('/support'):
        user = db.get_user(user_id)
        lang = user['language'] if user else 'ru'
        handle_support_request(message, lang)
        return
    
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
    # Проверка ограничения скорости
    allowed, wait_time = check_rate_limit(clicker_id)
    if not allowed:
        user = db.get_user(clicker_id)
        lang = user['language'] if user else 'ru'
        bot.send_message(clicker_id, t(lang, 'rate_limit_exceeded', seconds=wait_time))
        return
    
    # Проверка антиспама
    if not check_spam(clicker_id):
        bot.send_message(clicker_id, t('ru', 'spam_wait'))
        return
    
    # Проверка капчи
    if CAPTCHA_ENABLED:
        attempts, _ = db.get_captcha_attempts(clicker_id)
        if attempts >= CAPTCHA_AFTER_ATTEMPTS:
            if not require_captcha(clicker_id):
                return
    
    target_user = db.get_user(target_id)
    if not target_user:
        bot.send_message(clicker_id, t('ru', 'user_not_found'))
        return
    
    if target_user['receive_messages'] == 0:
        bot.send_message(clicker_id, t('ru', 'messages_disabled'))
        return
    
    user_sessions[clicker_id] = target_id
    db.increment_stat(target_id, 'link_clicks')
    db.track_link_click(target_id, clicker_id, "Telegram Bot")
    
    user = db.get_user(clicker_id)
    lang = user['language'] if user else 'ru'
    
    bot.send_message(
        clicker_id,
        f"💌 <b>{t(lang, 'send_anonymous_to')}</b> <i>{target_user['first_name']}</i>!\n\n"
        f"<i>{t(lang, 'send_anonymous_description')}</i>",
        reply_markup=cancel_keyboard(lang)
    )

def require_captcha(user_id: int) -> bool:
    """Требование капчи от пользователя"""
    user = db.get_user(user_id)
    lang = user['language'] if user else 'ru'
    
    # Генерация капчи
    captcha_image, captcha_text = generate_captcha()
    
    # Сохранение капчи
    captcha_data[user_id] = {
        'text': captcha_text,
        'timestamp': time.time(),
        'attempts': 0
    }
    
    # Конвертация изображения в bytes
    bio = BytesIO()
    captcha_image.save(bio, 'PNG')
    bio.seek(0)
    
    # Отправка капчи
    bot.send_photo(user_id, photo=bio, caption=t(lang, 'captcha_required', 
                                                attempt=1, max_attempts=3))
    
    return False

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
                bot.answer_callback_query(call.id, "✅ Refreshed")
            return
        
        elif data == "toggle_text":
            if user_id == ADMIN_ID:
                current = admin_modes.get(user_id, {}).get('show_text', True)
                admin_modes[user_id] = {'show_text': not current}
                show_message_logs(admin_id=user_id)
                bot.answer_callback_query(call.id, "✅ Settings changed")
            return
        
        elif data == "refresh_tickets":
            if user_id == ADMIN_ID:
                show_support_tickets(user_id)
                bot.answer_callback_query(call.id, "✅ Refreshed")
            return
        
        elif data.startswith("lang_"):
            language = data.split("_")[1]
            db.set_language(user_id, language)
            bot.answer_callback_query(call.id, f"✅ {t(language, 'language_changed')}")
            
            link = generate_link(user_id)
            bot.send_message(user_id, t(language, 'start', link=link), 
                           reply_markup=main_keyboard(user_id == ADMIN_ID, language))
            return
        
        elif data.startswith("reply_"):
            target_id = int(data.split("_")[1])
            user_sessions[user_id] = target_id
            
            target_user = db.get_user(target_id)
            if target_user:
                bot.send_message(user_id, f"💌 {t(lang, 'send_reply')} {target_user['first_name']}", 
                               reply_markup=cancel_keyboard(lang))
            else:
                bot.send_message(user_id, t(lang, 'send_reply'), 
                               reply_markup=cancel_keyboard(lang))
            bot.answer_callback_query(call.id)
        
        elif data.startswith("admin_block_"):
            if user_id != ADMIN_ID:
                bot.answer_callback_query(call.id, "❌ No access")
                return
            
            target_id = int(data.split("_")[2])
            if db.block_user(target_id, ADMIN_ID, "Admin panel"):
                db.add_admin_log("block", user_id, target_id, "Admin panel")
                bot.answer_callback_query(call.id, t(lang, 'block_user', user_id=target_id))
                
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
                db.add_admin_log("unblock", user_id, target_id, "Admin panel")
                bot.answer_callback_query(call.id, t(lang, 'unblock_user', user_id=target_id))
                
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
            db.add_admin_log("ticket_close", user_id, None, f"Ticket #{ticket_id}")
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
    
    # Обработка капчи
    if user_id in captcha_data:
        handle_captcha_response(message, user_id, lang)
        return
    
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
    if user_id in user_sessions:
        target_id = user_sessions[user_id]
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

def handle_captcha_response(message, user_id: int, lang: str):
    """Обработка ответа на капчу"""
    if user_id not in captcha_data:
        return
    
    captcha_info = captcha_data[user_id]
    user_response = message.text.strip().upper()
    
    # Проверка времени
    if time.time() - captcha_info['timestamp'] > 300:  # 5 минут
        del captcha_data[user_id]
        db.reset_captcha_attempts(user_id)
        bot.send_message(user_id, t(lang, 'captcha_timeout'))
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        return
    
    # Увеличиваем количество попыток
    captcha_info['attempts'] += 1
    db.add_captcha_attempt(user_id)
    
    # Проверка капчи
    if user_response == captcha_info['text']:
        # Капча пройдена
        del captcha_data[user_id]
        db.reset_captcha_attempts(user_id)
        bot.send_message(user_id, t(lang, 'captcha_correct'))
        
        # Возвращаем к предыдущему действию
        user = db.get_user(user_id)
        bot.send_message(user_id, t(lang, 'main_menu'), 
                        reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
    else:
        # Неверная капча
        if captcha_info['attempts'] >= 3:
            # Превышено количество попыток
            del captcha_data[user_id]
            bot.send_message(user_id, t(lang, 'captcha_failed'))
            bot.send_message(user_id, t(lang, 'main_menu'), 
                            reply_markup=main_keyboard(user_id == ADMIN_ID, lang))
        else:
            # Пробуем снова
            bot.send_message(user_id, t(lang, 'captcha_incorrect'))
            
            # Генерация новой капчи
            captcha_image, captcha_text = generate_captcha()
            captcha_data[user_id] = {
                'text': captcha_text,
                'timestamp': time.time(),
                'attempts': captcha_info['attempts']
            }
            
            bio = BytesIO()
            captcha_image.save(bio, 'PNG')
            bio.seek(0)
            
            bot.send_photo(user_id, photo=bio, 
                          caption=t(lang, 'captcha_required', 
                                   attempt=captcha_info['attempts'] + 1, 
                                   max_attempts=3))

def clear_user_state(user_id: int):
    """Очистка состояния пользователя"""
    if user_id in user_sessions:
        del user_sessions[user_id]
    if user_id in admin_modes:
        del admin_modes[user_id]
    if user_id in captcha_data:
        del captcha_data[user_id]

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
    detailed_stats = db.get_user_detailed_stats(user_id)
    
    receive_status = "✅ Enabled" if user['receive_messages'] else "❌ Disabled"
    username = f"@{user['username']}" if user['username'] else "❌ none"
    
    # Анализ статистики
    peak_hour = "N/A"
    active_day = "N/A"
    fav_type = "N/A"
    
    if detailed_stats:
        # Пиковая активность
        if detailed_stats['messages_by_hour']:
            max_hour = max(detailed_stats['messages_by_hour'].items(), key=lambda x: x[1])
            peak_hour = max_hour[0]
        
        # Самый активный день
        if detailed_stats['messages_by_day']:
            max_day = max(detailed_stats['messages_by_day'].items(), key=lambda x: x[1])
            day_names = {
                'Monday': 'Monday',
                'Tuesday': 'Tuesday',
                'Wednesday': 'Wednesday',
                'Thursday': 'Thursday',
                'Friday': 'Friday',
                'Saturday': 'Saturday',
                'Sunday': 'Sunday'
            }
            active_day = day_names.get(max_day[0], max_day[0])
        
        # Любимый тип сообщений
        if detailed_stats['message_types']:
            max_type = max(detailed_stats['message_types'].items(), key=lambda x: x[1])
            type_names = {
                'text': '📝 Text',
                'photo': '📸 Photo',
                'video': '🎬 Video',
                'voice': '🎤 Voice',
                'document': '📎 Document',
                'sticker': '😜 Sticker'
            }
            fav_type = type_names.get(max_type[0], max_type[0])
    
    # Время ответа
    avg_response = detailed_stats['avg_response_time'] if detailed_stats and 'avg_response_time' in detailed_stats else 0
    response_time = f"{int(avg_response//60)} min {int(avg_response%60)} sec" if avg_response > 0 else "N/A"
    
    # Достижения
    achievements = db.get_user_achievements(user_id)
    achievements_text = ""
    if achievements:
        for achievement in achievements[:5]:  # Показываем первые 5
            achievements_text += f"├ {t(lang, f'achievement_{achievement}')}\n"
        if len(achievements) > 5:
            achievements_text += f"└ ... and {len(achievements) - 5} more\n"
    else:
        achievements_text = "├ 📌 No achievements yet\n"
    
    profile_text = t(lang, 'profile',
                    user_id=user['user_id'],
                    first_name=user['first_name'],
                    username=username,
                    received=stats['messages_received'],
                    sent=stats['messages_sent'],
                    clicks=user['link_clicks'],
                    response_time=response_time,
                    receive_status=receive_status,
                    language=user['language'].upper(),
                    last_active=format_time(user['last_active'], lang),
                    peak_hour=peak_hour,
                    active_day=active_day,
                    fav_type=fav_type,
                    achievements=achievements_text,
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
    detailed_stats = db.get_user_detailed_stats(user_id)
    
    # Время ответа
    avg_response = detailed_stats['avg_response_time'] if detailed_stats and 'avg_response_time' in detailed_stats else 0
    response_time = f"{int(avg_response//60)} min {int(avg_response%60)} sec" if avg_response > 0 else "N/A"
    
    # Среднее время в боте
    if detailed_stats and detailed_stats['total_time_spent'] > 0:
        days_registered = max(1, (time.time() - user['created_at']) / 86400)
        avg_time_per_day = detailed_stats['total_time_spent'] / days_registered / 60
        avg_time = f"{avg_time_per_day:.1f}"
    else:
        avg_time = "N/A"
    
    # Создаем графики
    hours_chart = create_chart(detailed_stats['messages_by_hour'] if detailed_stats else {}, 5)
    days_chart = create_chart(detailed_stats['messages_by_day'] if detailed_stats else {}, 5)
    types_chart = create_chart(detailed_stats['message_types'] if detailed_stats else {}, 5)
    
    # Достижения
    achievements = db.get_user_achievements(user_id)
    achievements_text = ""
    if achievements:
        for achievement in achievements:
            achievements_text += f"├ {t(lang, f'achievement_{achievement}')}\n"
    else:
        achievements_text = "📌 Start communication to get achievements!\n"
    
    stats_text = t(lang, 'user_stats',
                  received=stats['messages_received'],
                  sent=stats['messages_sent'],
                  clicks=user['link_clicks'],
                  response_time=response_time,
                  registered=format_time(user['created_at'], lang),
                  last_active=format_time(user['last_active'], lang),
                  avg_time=avg_time,
                  hours_chart=hours_chart,
                  days_chart=days_chart,
                  types_chart=types_chart,
                  achievements_count=len(achievements),
                  achievements=achievements_text)
    
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
        # Проверка ограничения скорости
        allowed, wait_time = check_rate_limit(sender_id)
        if not allowed:
            bot.send_message(sender_id, t(lang, 'rate_limit_exceeded', seconds=wait_time))
            return
        
        # Проверка антиспама
        if not check_spam(sender_id):
            bot.send_message(sender_id, t(lang, 'spam_wait'))
            return
        
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
            db.add_moderation_log(sender_id, text[:100], "Blacklisted word", "blocked")
            
            # Уведомление админа
            if CHANNEL and CHANNEL != "":
                try:
                    bot.send_message(CHANNEL, t('ru', 'moderation_alert_admin', user_id=sender_id))
                except:
                    pass
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
        message_id = db.save_message(sender_id, receiver_id, message_type, 
                       text, file_id, file_unique_id, file_size)
        
        # Формирование сообщения для получателя
        receiver_lang = receiver['language'] if receiver else 'ru'
        caption = t(receiver_lang, 'anonymous_message', 
                   text=f"💬 <b>{t(receiver_lang, 'text')}:</b>\n<code>{html.escape(text)}</code>\n\n" if text else "")
        
        try:
            # Отправка сообщения получателю
            if message_type == 'text':
                msg = bot.send_message(receiver_id, caption, 
                                      reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'photo':
                msg = bot.send_photo(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'video':
                msg = bot.send_video(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'audio':
                msg = bot.send_audio(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'voice':
                msg = bot.send_voice(receiver_id, file_id, caption=caption,
                                   reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'document':
                msg = bot.send_document(receiver_id, file_id, caption=caption,
                                      reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            elif message_type == 'sticker':
                if caption:
                    bot.send_message(receiver_id, caption)
                msg = bot.send_sticker(receiver_id, file_id, 
                                     reply_markup=get_message_reply_keyboard(sender_id, receiver_lang))
            
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
        
        # Обновление статистики
        db.increment_stat(sender_id, 'messages_sent')
        db.increment_stat(receiver_id, 'messages_received')
        
        # Уведомление отправителя
        bot.send_message(sender_id, t(lang, 'message_sent', receiver_name=receiver['first_name']),
                        reply_markup=cancel_keyboard(lang))
        
        # Проверка достижений
        new_achievements = db.check_achievements(sender_id)
        if new_achievements:
            for achievement in new_achievements:
                bot.send_message(sender_id, f"🏆 {t(lang, f'achievement_{achievement}')}")
        
        # Логирование в канал
        if CHANNEL and CHANNEL != "":
            try:
                sender = db.get_user(sender_id)
                log_msg = f"""📨 New anonymous message

👤 From: {sender_id} ({sender['first_name'] if sender else '?'})
🎯 To: {receiver_id} ({receiver['first_name'] if receiver else '?'})
📝 Type: {message_type}"""
                
                if text:
                    log_msg += f"\n💬 Text: {text[:100]}"
                
                if file_id and message_type in ['photo', 'video']:
                    if message_type == 'photo':
                        bot.send_photo(CHANNEL, file_id, caption=log_msg)
                    elif message_type == 'video':
                        bot.send_video(CHANNEL, file_id, caption=log_msg)
                else:
                    bot.send_message(CHANNEL, log_msg)
            except Exception as e:
                logger.error(f"Channel error: {e}")
        
        # Логирование для админа
        db.add_admin_log("anonymous_message", sender_id, receiver_id, 
                        f"{message_type}: {text[:50] if text else 'no text'}")
        
    except Exception as e:
        logger.error(f"Send error: {e}")
        bot.send_message(sender_id, t(lang, 'system_error'))

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
        
        # Логирование
        db.add_admin_log("direct_message", ADMIN_ID, target_user_id, 
                        f"{message_type}: {text[:50] if text else 'no text'}")
        
    except Exception as e:
        logger.error(f"Direct message error: {e}")
        bot.send_message(ADMIN_ID, "❌ Sending error")

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
        bot.send_message(user_id, "❌ Enter text")
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
        db.add_admin_log("support_ticket", user_id, None, f"Ticket #{ticket_id}")
        
    except Exception as e:
        logger.error(f"Ticket error: {e}")
        bot.send_message(user_id, "❌ Ticket creation error")

def notify_admin_about_ticket(ticket_id: int, user_id: int, message_type: str, 
                            text: str, file_id: Optional[str]):
    """Уведомление админа о новом тикете"""
    user = db.get_user(user_id)
    
    notification = f"""🆘 New ticket #{ticket_id}

👤 User: {user_id}
📝 Name: {user['first_name'] if user else '?'}
📱 Username: {f'@{user['username']}' if user and user['username'] else 'no'}
📅 Time: {format_time(int(time.time()))}
📝 Type: {message_type}"""
    
    if text:
        notification += f"\n💬 Message: {text[:200]}"
    
    try:
        if file_id and message_type in ['photo', 'video']:
            if message_type == 'photo':
                msg = bot.send_photo(ADMIN_ID, file_id, caption=notification, 
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'en'))
            elif message_type == 'video':
                msg = bot.send_video(ADMIN_ID, file_id, caption=notification,
                                   reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'en'))
        else:
            msg = bot.send_message(ADMIN_ID, notification,
                                 reply_markup=get_admin_ticket_keyboard(ticket_id, user_id, 'en'))
        
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
{reply_text}"""
        
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
        
        db.add_admin_log("support_reply", ADMIN_ID, user_id, f"Ticket #{ticket_id}")
        
    except Exception as e:
        logger.error(f"Reply error: {e}")
        bot.send_message(ADMIN_ID, "❌ Response sending error")

def generate_qr_code(user_id: int, lang: str):
    """Генерация QR-кода"""
    link = generate_link(user_id)
    
    try:
        qr = qrcode.QRCode(
            version=1,
            box_size=6,  # Оптимизированный размер
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
    
    elif text == t(lang, 'btn_admin_block'):
        admin_modes[admin_id] = 'block_user'
        bot.send_message(admin_id, t(lang, 'block_instruction'), reply_markup=cancel_keyboard(lang))
    
    elif text == t(lang, 'btn_admin_logs'):
        show_message_logs(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_tickets'):
        show_support_tickets(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_settings'):
        show_admin_settings(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_backup'):
        create_backup(admin_id, lang)
    
    elif text == t(lang, 'btn_admin_export'):
        show_export_options(admin_id, lang)
    
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
        
        elif mode == 'export_users':
            export_users_data(admin_id)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'export_messages':
            export_messages_data(admin_id)
            if admin_id in admin_modes:
                del admin_modes[admin_id]
        
        elif mode == 'export_stats':
            export_stats_data(admin_id)
            if admin_id in admin_modes:
                del admin_modes[admin_id]

def show_admin_stats(admin_id: int, lang: str):
    """Показ статистики админа"""
    stats = db.get_admin_stats()
    
    bot.send_message(admin_id, t(lang, 'admin_stats',
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
                               conversion_rate=stats['conversion_rate'],
                               users_by_day=stats['users_by_day'],
                               messages_by_day=stats['messages_by_day'],
                               top_users=stats['top_users']),
                    reply_markup=admin_keyboard(lang))

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
        
        # Используем ThreadPoolExecutor для параллельной отправки
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            
            for user_id in users:
                futures.append(executor.submit(send_broadcast_message, user_id, text))
            
            for future in as_completed(futures):
                result = future.result()
                if result == 'sent':
                    sent += 1
                elif result == 'failed':
                    failed += 1
                elif result == 'blocked':
                    blocked += 1
                
                # Обновление прогресса каждые 20 сообщений
                if (sent + failed + blocked) % 20 == 0:
                    try:
                        bot.edit_message_text(
                            chat_id=admin_id,
                            message_id=progress_msg.message_id,
                            text=f"⏳ Sent: {sent}/{total}"
                        )
                    except:
                        pass
        
        bot.edit_message_text(
            chat_id=admin_id,
            message_id=progress_msg.message_id,
            text=t(lang, 'broadcast_result', total=total, sent=sent, failed=failed, blocked=blocked)
        )
        
        db.add_admin_log("broadcast", admin_id, None, f"Sent: {sent}/{total}")
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        bot.send_message(admin_id, f"❌ Error: {e}")

def send_broadcast_message(user_id: int, text: str) -> str:
    """Отправка одного сообщения рассылки"""
    try:
        if db.is_user_blocked(user_id):
            return 'blocked'
        
        bot.send_message(user_id, text, parse_mode="HTML")
        time.sleep(0.05)  # Задержка для избежания лимитов
        return 'sent'
        
    except ApiTelegramException as e:
        if e.error_code == 403:
            return 'failed'
        else:
            logger.error(f"Broadcast send error: {e}")
            return 'failed'
    except Exception as e:
        logger.error(f"Broadcast send error: {e}")
        return 'failed'

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
        
        username = f"@{user['username']}" if user['username'] else "❌ none"
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
                db.add_admin_log("unblock", admin_id, user['user_id'], "Block panel")
                bot.send_message(admin_id, t(lang, 'unblock_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'user_not_blocked_msg'),
                               reply_markup=admin_keyboard(lang))
        else:
            if db.block_user(user['user_id'], admin_id, "Block panel"):
                db.add_admin_log("block", admin_id, user['user_id'], "Block panel")
                bot.send_message(admin_id, t(lang, 'block_success', user_id=user['user_id']),
                               reply_markup=admin_keyboard(lang))
            else:
                bot.send_message(admin_id, t(lang, 'block_already'),
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
        sender_username = f" (@{msg['sender_username']})" if msg.get('sender_username') else ""
        receiver_username = f" (@{msg['receiver_username']})" if msg.get('receiver_username') else ""
        
        logs_text += f"{i}. {format_time(msg['timestamp'], lang)}\n"
        logs_text += f"   👤 From: {msg['sender_id']} - {sender_name}{sender_username}\n"
        logs_text += f"   🎯 To: {msg['receiver_id']} - {receiver_name}{receiver_username}\n"
        logs_text += f"   📝 Type: {msg['message_type']}\n"
        
        if msg['text']:
            logs_text += f"   💬 Text: {msg['text']}\n"
        
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
        tickets_text += f"{i}. Ticket #{ticket['id']}\n"
        tickets_text += f"   👤 User: {ticket['user_id']} - {ticket['first_name']}\n"
        tickets_text += f"   📱 Username: {f'@{ticket['username']}' if ticket['username'] else 'no'}\n"
        tickets_text += f"   📅 Created: {format_time(ticket['created_at'], lang)}\n"
        
        if ticket['message']:
            preview = ticket['message'][:100] + "..." if len(ticket['message']) > 100 else ticket['message']
            tickets_text += f"   💬 Message: {preview}\n"
        
        tickets_text += f"   📝 Type: {ticket['message_type']}\n\n"
    
    bot.send_message(admin_id, tickets_text, reply_markup=admin_keyboard(lang))

def show_admin_settings(admin_id: int, lang: str):
    """Показ настроек админа"""
    notifications = db.get_setting('notifications_enabled', '1')
    notifications_status = "✅ Enabled" if notifications == '1' else "❌ Disabled"
    channel_status = "✅ Configured" if CHANNEL and CHANNEL != "" else "❌ Not configured"
    
    settings_text = t(lang, 'admin_settings',
                     notifications=notifications_status,
                     channel_status=channel_status,
                     antispam=ANTISPAM_INTERVAL)
    
    bot.send_message(admin_id, settings_text, reply_markup=admin_keyboard(lang))

def create_backup(admin_id: int, lang: str):
    """Создание бэкапа базы данных"""
    try:
        backup_filename = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        
        with open(DB_PATH, 'rb') as f:
            db_content = f.read()
        
        # Сжатие (опционально)
        import gzip
        compressed = gzip.compress(db_content)
        
        bio = BytesIO(compressed)
        bio.name = backup_filename + '.gz'
        
        bot.send_document(admin_id, bio, 
                         caption=f"💾 Database backup\n📅 {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        db.add_admin_log("backup", admin_id, None, "Backup created")
        
    except Exception as e:
        logger.error(f"Backup error: {e}")
        bot.send_message(admin_id, f"❌ Backup error: {e}")

def show_export_options(admin_id: int, lang: str):
    """Показ опций экспорта"""
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton(t(lang, 'export_users')),
        types.KeyboardButton(t(lang, 'export_messages')),
        types.KeyboardButton(t(lang, 'export_stats')),
        types.KeyboardButton(t(lang, 'btn_cancel'))
    ]
    keyboard.add(*buttons)
    
    bot.send_message(admin_id, t(lang, 'export_instruction'), reply_markup=keyboard)
    admin_modes[admin_id] = 'export_options'

def export_users_data(admin_id: int):
    """Экспорт данных пользователей"""
    try:
        bot.send_message(admin_id, t('en', 'export_processing'))
        
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM users ORDER BY user_id')
            users = c.fetchall()
        
        # Создание CSV
        csv_content = "ID;Username;First Name;Language;Created At;Last Active;Messages Received;Messages Sent;Link Clicks;Receive Messages\n"
        
        for user in users:
            csv_content += f"{user['user_id']};{user['username'] or ''};{user['first_name'] or ''};{user['language']};"
            csv_content += f"{format_time(user['created_at'])};{format_time(user['last_active'])};"
            csv_content += f"{user['messages_received']};{user['messages_sent']};{user['link_clicks']};{user['receive_messages']}\n"
        
        # Отправка файла
        bio = BytesIO(csv_content.encode('utf-8'))
        bio.name = f"users_export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        bot.send_document(admin_id, bio, caption="👥 Users export")
        db.add_admin_log("export", admin_id, None, "Users export")
        
    except Exception as e:
        logger.error(f"Export users error: {e}")
        bot.send_message(admin_id, f"❌ Export error: {e}")

def export_messages_data(admin_id: int):
    """Экспорт данных сообщений"""
    try:
        bot.send_message(admin_id, t('en', 'export_processing'))
        
        with db.get_connection() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM messages ORDER BY timestamp DESC LIMIT 1000')
            messages = c.fetchall()
        
        # Создание CSV
        csv_content = "ID;Sender ID;Receiver ID;Type;Text;Timestamp\n"
        
        for msg in messages:
            text = (msg['text'] or '').replace(';', ',').replace('\n', ' ').replace('\r', '')
            csv_content += f"{msg['id']};{msg['sender_id']};{msg['receiver_id']};{msg['message_type']};{text};{format_time(msg['timestamp'])}\n"
        
        # Отправка файла
        bio = BytesIO(csv_content.encode('utf-8'))
        bio.name = f"messages_export_{datetime.now().strftime('%Y%m%d')}.csv"
        
        bot.send_document(admin_id, bio, caption="📨 Messages export (last 1000)")
        db.add_admin_log("export", admin_id, None, "Messages export")
        
    except Exception as e:
        logger.error(f"Export messages error: {e}")
        bot.send_message(admin_id, f"❌ Export error: {e}")

def export_stats_data(admin_id: int):
    """Экспорт статистики"""
    try:
        bot.send_message(admin_id, t('en', 'export_processing'))
        
        stats = db.get_admin_stats()
        
        # Создание текстового файла
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
        
        # Отправка файла
        bio = BytesIO(stats_text.encode('utf-8'))
        bio.name = f"stats_export_{datetime.now().strftime('%Y%m%d')}.txt"
        
        bot.send_document(admin_id, bio, caption="📊 Statistics export")
        db.add_admin_log("export", admin_id, None, "Statistics export")
        
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
            'version': '7.0',
            'users': stats['total_users'],
            'messages': stats['total_messages'],
            'uptime': time.time() - start_time
        })
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return jsonify({'status': 'error', 'error': str(e)}), 500

@app.route('/ping', methods=['GET'])
def ping():
    """Пинг для поддержания активности"""
    return jsonify({'status': 'active', 'timestamp': time.time()})

@app.route('/admin', methods=['GET'])
def admin_panel_web():
    """Веб-панель админа"""
    if not CHANNEL:
        return "Admin panel not configured"
    
    stats = db.get_admin_stats()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Anony SMS Admin</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{ font-family: Arial, sans-serif; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
            .container {{ max-width: 1200px; margin: 0 auto; background: rgba(255, 255, 255, 0.1); backdrop-filter: blur(10px); padding: 30px; border-radius: 20px; box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3); }}
            .header {{ text-align: center; margin-bottom: 40px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 40px; }}
            .stat-card {{ background: rgba(255, 255, 255, 0.2); padding: 25px; border-radius: 15px; text-align: center; box-shadow: 0 4px 15px rgba(0,0,0,0.2); transition: transform 0.3s; }}
            .stat-card:hover {{ transform: translateY(-5px); }}
            .stat-value {{ font-size: 36px; font-weight: bold; margin: 15px 0; color: #fff; }}
            .stat-label {{ font-size: 14px; opacity: 0.9; }}
            .chart-container {{ background: rgba(255, 255, 255, 0.2); padding: 20px; border-radius: 15px; margin-bottom: 30px; }}
            h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
            h2 {{ font-size: 1.8em; margin: 30px 0 20px 0; }}
            .footer {{ text-align: center; margin-top: 40px; opacity: 0.7; font-size: 14px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 Anony SMS Admin Panel</h1>
                <p>Real-time bot statistics and management</p>
            </div>
            <div class="stats">
                <div class="stat-card"><div class="stat-label">👥 Users</div><div class="stat-value">{stats['total_users']}</div></div>
                <div class="stat-card"><div class="stat-label">📨 Messages</div><div class="stat-value">{stats['total_messages']}</div></div>
                <div class="stat-card"><div class="stat-label">🚫 Blocked</div><div class="stat-value">{stats['blocked_users']}</div></div>
                <div class="stat-card"><div class="stat-label">🆘 Tickets</div><div class="stat-value">{stats['open_tickets']}</div></div>
                <div class="stat-card"><div class="stat-label">📈 Today Active</div><div class="stat-value">{stats['today_active']}</div></div>
                <div class="stat-card"><div class="stat-label">📊 Retention</div><div class="stat-value">{stats['retention_30d']}%</div></div>
            </div>
            <div class="chart-container">
                <h2>📊 Activity Statistics</h2>
                <p>Last 24h messages: <strong>{stats['messages_24h']}</strong></p>
                <p>New users (24h): <strong>{stats['new_users_24h']}</strong></p>
                <p>Avg hourly activity: <strong>{stats['avg_hourly']}</strong></p>
            </div>
            <div class="footer">
                <p>Anony SMS Bot v7.0 | Last update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>© 2024 Anony SMS. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ====== МОНИТОРИНГ И ОПТИМИЗАЦИЯ ======
def monitor_bot():
    """Мониторинг состояния бота"""
    while True:
        try:
            stats = db.get_admin_stats()
            
            # Проверка низкой активности
            if stats['messages_24h'] < 10 and stats['total_users'] > 100:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Low activity\nLast 24h: {stats['messages_24h']} messages\nUsers: {stats['total_users']}")
                except:
                    pass
            
            # Проверка большого количества тикетов
            if stats['open_tickets'] > 10:
                try:
                    bot.send_message(ADMIN_ID, f"⚠️ Many tickets: {stats['open_tickets']}")
                except:
                    pass
            
            # Проверка целостности БД
            try:
                with db.get_connection() as conn:
                    c = conn.cursor()
                    c.execute('PRAGMA integrity_check')
                    result = c.fetchone()
                    if result[0] != 'ok':
                        bot.send_message(ADMIN_ID, f"⚠️ DB integrity issue: {result[0]}")
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
            
            # Очистка rate limit кэша
            minute = int(current_time // 60)
            keys_to_delete = []
            for key, data in rate_limit_cache.items():
                if data['minute'] != minute:
                    keys_to_delete.append(key)
            
            for key in keys_to_delete:
                del rate_limit_cache[key]
            
            time.sleep(3600)  # Проверка каждый час
            
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            time.sleep(300)

def keep_alive():
    """Поддержание активности на Render"""
    while True:
        try:
            if WEBHOOK_HOST:
                response = requests.get(f"{WEBHOOK_HOST}/ping", timeout=10)
                if response.status_code == 200:
                    logger.debug("✅ Ping successful")
                else:
                    logger.warning(f"⚠️ Ping failed: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ping error: {e}")
        time.sleep(300)  # Пинг каждые 5 минут

def cleanup_old_data():
    """Очистка старых данных"""
    while True:
        try:
            # Удаляем старые сессии (старше 7 дней)
            week_ago = int(time.time()) - 604800
            with db.get_connection() as conn:
                c = conn.cursor()
                c.execute('DELETE FROM user_history WHERE timestamp < ?', (week_ago,))
                deleted = c.rowcount
                if deleted > 0:
                    logger.info(f"🧹 Cleaned {deleted} old history records")
                
                # Удаляем старые логи (старше 30 дней)
                month_ago = int(time.time()) - 2592000
                c.execute('DELETE FROM admin_logs WHERE timestamp < ?', (month_ago,))
                deleted = c.rowcount
                if deleted > 0:
                    logger.info(f"🧹 Cleaned {deleted} old logs")
            
            # Очистка кэша
            if hasattr(db, '_stats_cache'):
                db._stats_cache.clear()
                db._stats_cache_time.clear()
                db._user_cache.clear()
                db._user_cache_time.clear()
            
            time.sleep(86400)  # Раз в день
            
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            time.sleep(3600)

# ====== ЗАПУСК БОТА ======
if __name__ == '__main__':
    logger.info("=" * 60)
    logger.info("🚀 Anony SMS Bot v7.0 - Professional Edition")
    logger.info("=" * 60)
    
    start_time = time.time()
    
    # Проверка токена
    if not TOKEN:
        logger.error("❌ Bot token not found! Set PLAY environment variable.")
        sys.exit(1)
    
    # Получение информации о боте
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
    
    # Запуск фоновых задач
    try:
        # Мониторинг
        monitor_thread = threading.Thread(target=monitor_bot, daemon=True)
        monitor_thread.start()
        logger.info("✅ Monitoring started")
        
        # Очистка данных
        cleanup_thread = threading.Thread(target=cleanup_old_data, daemon=True)
        cleanup_thread.start()
        logger.info("✅ Cleanup service started")
        
        # Keep-alive для Render
        if WEBHOOK_HOST:
            ping_thread = threading.Thread(target=keep_alive, daemon=True)
            ping_thread.start()
            logger.info("✅ Keep-alive service started")
        
    except Exception as e:
        logger.error(f"❌ Background services error: {e}")
    
    # Запуск бота
    try:
        if WEBHOOK_HOST:
            logger.info(f"🌐 Setting up webhook for {WEBHOOK_HOST}")
            
            # Удаление старого вебхука
            try:
                bot.remove_webhook()
                time.sleep(1)
            except:
                pass
            
            # Настройка нового вебхука
            bot.set_webhook(
                url=f"{WEBHOOK_HOST}/webhook",
                max_connections=100,
                timeout=60,
                certificate=None,
                ip_address=None,
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
            # Локальный запуск (поллинг)
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
