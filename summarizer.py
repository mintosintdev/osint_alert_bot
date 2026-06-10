"""RAG-поиск: SearXNG дорки → реальный контент → Groq саммари."""
import aiohttp
import os
import logging
from urllib.parse import quote_plus
from dotenv import load_dotenv
from config import GROQ_MODEL

load_dotenv()
logger = logging.getLogger(__name__)

# Локальный SearXNG (как в geo_monitor)
SEARXNG_URL = "http://localhost:8304/search"

ON_DEMAND_SYSTEM = """Ты OSINT-аналитик. Тебе даны РЕАЛЬНЫЕ результаты поиска по запросу пользователя.
Проанализируй их и сформируй краткую сводку.

ПРАВИЛА:
- Используй ТОЛЬКО предоставленные источники. НЕ выдумывай факты.
- Если в источниках нет ответа — прямо скажи "По данному запросу свежих данных не найдено".
- Указывай ссылки на источники.
- Формат: Markdown, структурированно, без воды."""

ON_DEMAND_USER = """Запрос: {query}
Дата: 10 июня 2026

РЕЗУЛЬТАТЫ ПОИСКА:
{context}

Сформируй сводку по этим данным."""


async def _searxng_search(query: str, num_results: int = 5) -> list[dict]:
    """Поиск через локальный SearXNG."""
    params = {
        "q": query,
        "format": "json",
        "number_of_results": num_results,
        "language": "ru",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(SEARXNG_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.error(f"SearXNG error: {resp.status}")
                    return []
                data = await resp.json()
                results = []
                for r in data.get("results", [])[:num_results]:
                    results.append({
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "url": r.get("url", ""),
                    })
                logger.info(f"🔎 SearXNG: найдено {len(results)} результатов по '{query}'")
                return results
    except Exception as e:
        logger.error(f"❌ Ошибка SearXNG: {e}")
        return []


def _build_context(results: list[dict]) -> str:
    """Формирует контекст из результатов поиска для LLM."""
    if not results:
        return "Результаты поиска отсутствуют."
    
    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] {r['title']}\n{r['content']}\nИсточник: {r['url']}")
    return "\n\n---\n\n".join(parts)


async def search_on_demand(query: str) -> str:
    """RAG-поиск: дорки → реальный контент → Groq саммари."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "⚠️ GROQ_API_KEY не задан"

    # 1. Реальный поиск через SearXNG
    logger.info(f"🔎 Этап 1: Поиск через SearXNG: {query}")
    results = await _searxng_search(query)
    
    # 2. Формируем контекст
    context = _build_context(results)
    
    # 3. Скармливаем в Groq
    logger.info(f"🧠 Этап 2: Анализ {len(results)} источников через Groq...")
    prompt = ON_DEMAND_USER.format(query=query, context=context)
    
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": ON_DEMAND_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Groq error: {await resp.text()}")
                    return f"⚠️ Ошибка Groq: {resp.status}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Ошибка Groq: {e}")
        return f"⚠️ Ошибка генерации: {e}"


# MINT_PROMPT и generate_summary оставляем как есть (они работают для алертов)
MINT_PROMPT = """Ты OSINT-аналитик. Сформируй краткий отчёт в формате MINT OSINT по следующей новости:

ЗАГОЛОВОК: {title}
ТЕКСТ: {summary}
ССЫЛКА: {link}
ЦЕЛЬ МОНИТОРИНГА: {target}

ФОРМАТ ОТВЕТА (строго Markdown):
🔴 **Что произошло:** [1-2 предложения]
📍 **Где:** [населённый пункт, район]
🕐 **Когда:** [время/дата из текста или "уточняется"]
🔗 **Источник:** [{title}]({link})
⚠️ **Достоверность:** [низкая/средняя/высокая] — [почему]
💡 **Рекомендация:** [что делать / за чем следить дальше]

Отвечай ТОЛЬКО отчётом, без вводных слов."""


async def generate_summary(item: dict) -> str:
    """Генерирует MINT OSINT саммари для алерта."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "⚠️ GROQ_API_KEY не задан"

    prompt = MINT_PROMPT.format(**item)
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 1200,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Groq error: {await resp.text()}")
                    return f"⚠️ Ошибка Groq: {resp.status}"
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"Ошибка Groq: {e}")
        return f"⚠️ Ошибка генерации: {e}"
