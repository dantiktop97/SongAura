import os
import random
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ===================== Конфигурация =====================
TOKEN = os.getenv("Song")  # Твой токен бота Telegram

# ===================== Локальная база цитат =====================
QUOTES = [
    "Жизнь — это то, что с тобой происходит, пока ты строишь планы. — Джон Леннон",
    "Не откладывай на завтра то, что можно сделать сегодня.",
    "Счастье — это когда то, что ты думаешь, что ты говоришь, и что ты делаешь, совпадает. — Махатма Ганди",
    "Смелость — это сопротивление страху, а не отсутствие страха.",
    "Учись на ошибках других. Ты не сможешь прожить достаточно долго, чтобы сделать их все сам."
]

# ===================== Команды =====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я QuoteBot.\n"
        "Используй команду /quote, чтобы получить случайную цитату."
    )

async def quote_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    quote = random.choice(QUOTES)
    await update.message.reply_text(f"💬 {quote}")

# ===================== MAIN =====================
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("quote", quote_command))

    # Запуск через polling (для теста локально)
    print("Бот запущен...")
    app.run_polling()
