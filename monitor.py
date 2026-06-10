"""Сбор и фильтрация новостей."""
import asyncio
import aiohttp
import feedparser
import logging
from config import TARGETS, RSS_FEEDS, MAX_ITEMS_PER_FEED

logger = logging.getLogger(__name__)

def _matches_target(text: str, target: dict) -> bool:
    """Проверяет текст на совпадение с ключевыми словами или хештегами цели."""
    text_lower = text.lower()
    keywords = [kw.lower() for kw in target["keywords"]]
    hashtags = [ht.lower() for ht in target["hashtags"]]
    return any(kw in text_lower for kw in keywords) or any(ht in text_lower for ht in hashtags)

async def fetch_feed(session: aiohttp.ClientSession, url: str) -> list[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return []
            text = await resp.text()
            parsed = feedparser.parse(text)
            items = []
            for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
                items.append({
                    "id": entry.get("id") or entry.get("link"),
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", ""),
                    "published": entry.get("published", ""),
                })
            return items
    except Exception as e:
        logger.error(f"Ошибка загрузки {url}: {e}")
        return []

async def collect_alerts(targets: dict = None) -> list[dict]:
    """Собирает новости и фильтрует по целям."""
    targets = targets or TARGETS
    alerts = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_feed(session, url) for url in RSS_FEEDS]
        results = await asyncio.gather(*tasks)

    all_items = [item for feed_items in results for item in feed_items]

    for item in all_items:
        full_text = f"{item['title']} {item['summary']}"
        for target_key, target_cfg in targets.items():
            if _matches_target(full_text, target_cfg):
                alerts.append({
                    **item,
                    "target": target_cfg["name"],
                    "target_key": target_key,
                })
                break  # Одна новость = одна цель (без дублей)

    logger.info(f"📡 Собрано {len(all_items)} новостей, из них {len(alerts)} по целям")
    return alerts
