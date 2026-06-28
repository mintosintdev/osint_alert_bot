"""Search Memory: кэширование результатов поиска в SQLite."""
import sqlite3
import json
import hashlib
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path("search_memory.db")

# TTL в секундах: новости = 6ч, общее = 24ч
TTL_NEWS = 6 * 3600
TTL_DEFAULT = 24 * 3600


def _get_conn() -> sqlite3.Connection:
    """Создает подключение и таблицу, если её нет."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS search_cache (
            query_hash TEXT PRIMARY KEY,
            results_json TEXT NOT NULL,
            created_at REAL NOT NULL,
            ttl REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def _make_hash(query: str) -> str:
    """Детерминированный хеш запроса."""
    normalized = " ".join(query.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def get_cached_results(query: str) -> list[dict] | None:
    """Возвращает кэшированные результаты или None, если кэш истёк/отсутствует."""
    try:
        conn = _get_conn()
        cursor = conn.execute(
            "SELECT results_json, created_at, ttl FROM search_cache WHERE query_hash = ?",
            (_make_hash(query),)
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        results_json, created_at, ttl = row
        if time.time() - created_at > ttl:
            logger.info(f"⏰ Кэш истёк для: {query[:40]}...")
            return None

        results = json.loads(results_json)
        logger.info(f"💾 Кэш найден ({len(results)} рез.) для: {query[:40]}...")
        return results

    except Exception as e:
        logger.error(f"❌ Ошибка чтения кэша: {e}")
        return None


def save_to_cache(query: str, results: list[dict], is_news: bool = False):
    """Сохраняет результаты поиска в кэш."""
    try:
        ttl = TTL_NEWS if is_news else TTL_DEFAULT
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO search_cache (query_hash, results_json, created_at, ttl) VALUES (?, ?, ?, ?)",
            (_make_hash(query), json.dumps(results, ensure_ascii=False), time.time(), ttl)
        )
        conn.commit()
        conn.close()
        logger.info(f"✅ Сохранено в кэш ({len(results)} рез.): {query[:40]}...")
    except Exception as e:
        logger.error(f"❌ Ошибка записи в кэш: {e}")
