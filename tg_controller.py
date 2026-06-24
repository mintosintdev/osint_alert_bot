"""Telegram-контроллер: команды, on-demand поиск и inline-кнопки."""
import logging
import os
from dotenv import load_dotenv
from telegram.request import HTTPXRequest
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from summarizer import search_on_demand, search_on_demand_direct

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def _safe_refine_button(query: str) -> InlineKeyboardMarkup:
    """Делает кнопку 'Уточнить' безопасной длины для Telegram (макс 64 байта)."""
    # Кириллица весит больше латиницы, поэтому режем до 25 символов с запасом
    safe_q = query[:25]
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Уточнить поиск", callback_data=f"refine:{safe_q}")]
    ])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Приветствие с inline-меню."""
    keyboard = [
        [InlineKeyboardButton("🔍 Быстрый поиск", callback_data="action_search")],
        [InlineKeyboardButton("📋 Активные цели", callback_data="action_list")],
        [InlineKeyboardButton("❓ Помощь", callback_data="action_help")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "👋 *OSINT Alert Bot*\n\n"
        "Я нахожу свежие новости и аналитику через AI-дорки.\n"
        "Выбери действие ниже или просто напиши запрос:",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на inline-кнопки."""
    query = update.callback_query
    await query.answer()  # Убираем «часики» на кнопке

    if query.data == "action_help":
        help_text = (
            "🤖 *Как пользоваться:*\n\n"
            "• Просто напиши тему: `Донецк фронт`\n"
            "• Или используй /search <запрос>\n"
            "• Бот генерирует умные дорки через LLM\n"
            "• Ищет через SearXNG по всему вебу\n"
            "• Делает MINT-саммари с источниками\n\n"
            "💡 *Совет:* Чем конкретнее запрос, тем лучше результат."
        )
        await query.edit_message_text(help_text, parse_mode="Markdown")

    elif query.data == "action_list":
        from config import TARGETS
        targets = "\n".join([f"• {v['name']}" for v in TARGETS.values()])
        await query.edit_message_text(f"📋 *Активные цели:*\n{targets}", parse_mode="Markdown")

    elif query.data == "action_search":
        await query.edit_message_text("✏️ Напиши запрос следующим сообщением:")

    elif query.data.startswith("refine:"):
        original_query = query.data.split(":", 1)[1]
        await query.edit_message_text(
            f"🔄 *Уточняю поиск по:* `{original_query}`\n⏳ Генерирую новые дорки...",
            parse_mode="Markdown"
        )
        result = await search_on_demand(original_query)
        await query.edit_message_text(
            result, 
            parse_mode="Markdown", 
            reply_markup=_safe_refine_button(original_query)
        )


async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /search <запрос>."""
    query = " ".join(context.args) if context.args else ""
    if not query:
        await update.message.reply_text("⚠️ Использование: /search <запрос>\nПример: /search Донецк приліт")
        return

    status_msg = await update.message.reply_text(
        f"🔎 *Ищу:* `{query}`\n⏳ Генерирую дорки и ищу...", 
        parse_mode="Markdown"
    )

    result_data = await search_on_demand(query)
    try:
        await status_msg.edit_text(
            result_data["summary"],
            parse_mode="Markdown",
            reply_markup=_safe_refine_button(result_data["label"])
        )
    except Exception as e:
        logger.warning(f"⚠️ Ошибка парсинга Markdown, отправляю без форматирования: {e}")
        import re
        clean_text = re.sub(r'[*_`\[\]]', '', result_data["summary"])
        await status_msg.edit_text(
            clean_text,
            reply_markup=_safe_refine_button(result_data["label"])
        )    


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if len(query) < 3:
        return

    # === ПРОПУСКАЕМ LLM-ГЕНЕРАЦИЮ ДЛЯ ГОТОВЫХ ДОРКОВ ===
    is_raw_dork = query.startswith("/dork ") or any(op in query for op in ["site:", "filetype:", "intitle:", "intext:"])
    
    status_msg = await update.message.reply_text(
        f"🔎 *Ищу:* `{query[:50]}...`\n⏳ {'Прямой поиск по дорку' if is_raw_dork else 'Генерирую дорки и ищу'}...", 
        parse_mode="Markdown"
    )

    if is_raw_dork:
        # Прямой поиск без LLM-генерации
        clean_query = query.replace("/dork ", "").strip()
        result_data = await search_on_demand_direct(clean_query)
    else:
        result_data = await search_on_demand(query)
    
    try:
        await status_msg.edit_text(
            result_data["summary"],
            parse_mode="Markdown",
            reply_markup=_safe_refine_button(result_data["label"])
        )
    except Exception as e:
        logger.warning(f"⚠️ Ошибка парсинга Markdown, отправляю без форматирования: {e}")
        import re
        clean_text = re.sub(r'[*_`\[\]]', '', result_data["summary"])
        await status_msg.edit_text(
            clean_text,
            reply_markup=_safe_refine_button(result_data["label"])
        )


def run_bot():
    """Запуск TG-бота в режиме long polling."""
    token = os.getenv("TG_BOT_TOKEN")
    if not token:
        logger.error("❌ TG_BOT_TOKEN не задан в .env")
        return

    # Принудительно используем IPv4 и увеличиваем таймауты
    from telegram.request import HTTPXRequest
    
    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
        # Если есть проблемы с IPv6, можно попробовать отключить его явно, 
        # но обычно достаточно увеличить таймаут
    )

    app = ApplicationBuilder().token(token).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("🤖 TG-бот запущен (long polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    run_bot()
