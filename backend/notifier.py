"""Отправка уведомлений в Telegram."""
import aiohttp
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

async def send_telegram(text: str):
    bot_token = os.getenv("TG_BOT_TOKEN")
    chat_id = os.getenv("TG_CHAT_ID")
    if not bot_token or not chat_id:
        logger.error("❌ TG_BOT_TOKEN или TG_CHAT_ID не заданы в .env")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    logger.info("✅ Сообщение отправлено в TG")
                    return True
                else:
                    logger.error(f"❌ TG API error: {await resp.text()}")
                    return False
    except Exception as e:
        logger.error(f"❌ Ошибка отправки TG: {e}")
        return False
