"""Telegram-контроллер: команды и on-demand поиск."""
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from summarizer import search_on_demand

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

HELP_TEXT = """🤖 *OSINT Alert Bot — Команды:*

/start — Приветствие и меню
/add <запрос> — Добавить временную цель мониторинга
/list — Показать активные цели
/search <запрос> — Мгновенный поиск новостей по теме
/help — Эта справка

💡 *Пример:* `/search Донецк приліт`
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я OSINT Alert Bot.\n\n"
        "Напиши /help чтобы увидеть все команды.\n"
        "Или просто напиши тему — я найду свежие новости!",
        parse_mode="Markdown"
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def list_targets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # TODO: Подключить к динамическому списку целей
    from config import TARGETS
    targets = "\n".join([f"• {v['name']}" for v in TARGETS.values()])
    await update.message.reply_text(f"📋 *Активные цели из конфига:*\n{targets}", parse_mode="Markdown")


async def add_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("⚠️ Использование: /add <запрос>\nПример: /add Харьков обстріл")
        return
    # TODO: Сохранять в runtime-state или файл
    await update.message.reply_text(f"✅ Цель добавлена (временно): *{query}*\n\n⚠️ Пока работает только в текущей сессии.", parse_mode="Markdown")


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("⚠️ Использование: /search <запрос>\nПример: /search Донецк приліт")
        return
    
    await update.message.reply_text(f"🔎 Ищу по запросу: *{query}*...\n⏳ Подожди пару секунд.", parse_mode="Markdown")
    result = await search_on_demand(query)
    await update.message.reply_text(result, parse_mode="Markdown")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка обычного текста как on-demand поиска."""
    query = update.message.text.strip()
    if len(query) < 3:
        return
    
    await update.message.reply_text(f"🔎 Ищу: *{query}*...", parse_mode="Markdown")
    result = await search_on_demand(query)
    await update.message.reply_text(result, parse_mode="Markdown")


def run_bot():
    """Запуск TG-бота в режиме long polling."""
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    token = os.getenv("TG_BOT_TOKEN")
    if not token:
        logger.error("❌ TG_BOT_TOKEN не задан в .env")
        return
    
    app = ApplicationBuilder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("list", list_targets))
    app.add_handler(CommandHandler("add", add_target))
    app.add_handler(CommandHandler("search", search_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    
    logger.info("🤖 TG-бот запущен (long polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
