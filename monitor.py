"""Сбор и фильтрация новостей."""
import asyncio
import aiohttp
import feedparser
import logging
from config import RSS_FEEDS, MAX_ITEMS_PER_FEED

logger = logging.getLogger(__name__)

def _matches_target(text: str, target: dict) -> bool:
    """Проверяет текст на совпадение с ключевыми словами или хештегами цели."""
    if not text:
        return True
    text_lower = text.lower()
    keywords = [kw.lower() for kw in target.get("keywords", [])]
    hashtags = [ht.lower() for ht in target.get("hashtags", [])]
    
    # Если нет ключей, считаем что подходит всё (или можно вернуть False)
    if not keywords and not hashtags:
        return True
        
    return any(kw in text_lower for kw in keywords) or any(ht in text_lower for ht in hashtags)

async def fetch_feed(session: aiohttp.ClientSession, url: str) -> list[dict]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                logger.warning(f"HTTP {resp.status} for {url}")
                return []
            text = await resp.text()
            parsed = feedparser.parse(text)
            items = []
            for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
                # Защита от битых полей
                link = entry.get("link") or entry.get("id")
                if not link:
                    continue
                    
                items.append({
                    "id": entry.get("id") or link, # ID для дедупликации
                    "title": entry.get("title", "No Title"),
                    "link": link,
                    "summary": entry.get("summary", "") or entry.get("description", ""),
                    "published": entry.get("published", ""),
                    "source_url": url, # Откуда взяли
                })
            return items
    except Exception as e:
        logger.error(f"Ошибка загрузки {url}: {e}")
        return []

async def collect_alerts(targets: dict = None) -> list[dict]:
    """Собирает новости и фильтрует по целям."""
    if not targets:
        logger.info("⚠️ Цели мониторинга не заданы. Пропускаем сбор RSS.")
        return []

    alerts = []
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_feed(session, url) for url in RSS_FEEDS]
        results = await asyncio.gather(*tasks)

    all_items = [item for feed_items in results for item in feed_items]

    for item in all_items:
        full_text = f"{item['title']} {item['summary']}"
        matched_target = None
        
        for target_key, target_cfg in targets.items():
            if _matches_target(full_text, target_cfg):
                matched_target = target_cfg["name"]
                break

        if matched_target:
            alerts.append({
                **item,
                "target": matched_target,
                "target_key": target_key,
            })

    logger.info(f"📡 Собрано {len(all_items)} новостей, из них {len(alerts)} по целям")
    return alerts
