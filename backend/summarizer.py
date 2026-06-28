"""RAG-поиск: SearXNG дорки → реальный контент → Groq саммари."""
import asyncio
import aiohttp
import os
import base64
import fitz
import logging
from io import BytesIO
from PIL import Image
from datetime import datetime
from dotenv import load_dotenv
from config import GROQ_MODEL
from db import get_cached_results, save_to_cache
from dork_generator import generate_dorks

load_dotenv()
logger = logging.getLogger(__name__)

SEARXNG_URL = "http://localhost:8304/search"

# === ПРОМПТЫ ===
ON_DEMAND_SYSTEM = """Ты элитный OSINT-аналитик. Тебе даны РЕАЛЬНЫЕ результаты поиска.
Сформируй структурированную сводку с Evidence Tree.

ПРАВИЛА:
- Используй ТОЛЬКО предоставленные источники. НЕ выдумывай.
- Если данных нет — прямо скажи "По данному запросу свежих данных не найдено".
- Формат ответа (строго Markdown):

🧠 **Ключевые выводы:**
• [Вывод 1]
• [Вывод 2]

📎 **Evidence Tree (подтверждение):**
> 💬 "[Цитата из источника]"
> 🌐 [Название источника](URL)

⚠️ **Что НЕ удалось подтвердить:**
• [Факты, которые искали, но не нашли]

Отвечай ТОЛЬКО отчётом, без вводных слов."""

ON_DEMAND_USER = """Запрос: {query}
Дата: {date}

РЕЗУЛЬТАТЫ ПОИСКА:
{context}

Сформируй сводку по этим данным."""

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


# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def _searxng_search(query: str, num_results: int = 5) -> list[dict]:
    """Поиск через локальный SearXNG."""
    params = {
        "q": query,
        "format": "json",
        "number_of_results": num_results,
        "categories": "general,news",
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
                    result_item = {
                        "title": r.get("title", ""),
                        "content": r.get("content", ""),
                        "url": r.get("url", ""),
                    }
    
                    # === PDF EXTRACTION ===
                    url = r.get("url", "")
                    if url.lower().endswith(".pdf"):
                        pdf_text = await _extract_pdf_content(url)
                        if pdf_text:
                            result_item["content"] = f"[PDF CONTENT]\n{pdf_text}\n\n[SNIPPET]\n{result_item['content']}"
       
                    results.append(result_item)
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


def _filter_relevant_results(results: list[dict], query: str) -> list[dict]:
    """Убирает мусор из выдачи SearXNG по базовым ключевым словам."""
    keywords = [w.lower() for w in query.split() if len(w) >= 3]
    if not keywords:
        return results
        
    filtered = []
    for r in results:
        text = f"{r.get('title', '')} {r.get('content', '')}".lower()
        if any(kw in text for kw in keywords):
            filtered.append(r)
    
    removed = len(results) - len(filtered)
    if removed > 0:
        logger.info(f"🗑️ Отфильтровано {removed} нерелевантных результатов")
    return filtered


# === ОСНОВНЫЕ ФУНКЦИИ ===

async def _extract_pdf_content(url: str) -> str | None:
    """Извлекает текст с первой страницы PDF через Groq Vision."""
    try:
        # 1. Скачиваем PDF (только первые 5 МБ для безопасности)
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200 or resp.content_length > 5 * 1024 * 1024:
                    return None
                pdf_bytes = await resp.read()

        # 2. Конвертируем первую страницу в картинку
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        doc.close()

        # 3. Отправляем в Groq Vision
        api_key = os.getenv("GROQ_API_KEY")
        payload = {
            "model": "llama-3.2-11b-vision-preview",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Extract key facts, dates, names, and figures from this document page. Return ONLY structured text, no commentary."},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_base64}"}}
                ]
            }],
            "max_tokens": 1000
        }
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    extracted = data["choices"][0]["message"]["content"]
                    logger.info(f"📄 Извлечено {len(extracted)} символов из PDF: {url[:60]}...")
                    return extracted
                return None
    except Exception as e:
        logger.warning(f"⚠️ Не удалось извлечь PDF {url[:60]}: {e}")
        return None


async def search_on_demand_direct(dork: str) -> dict:
    """Прямой поиск по готовому дорку БЕЗ LLM-генерации."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"summary": "⚠️ GROQ_API_KEY не задан", "label": dork[:25]}

    label = dork[:25]  # Для дорков label = сам дорк (обрезанный)

    # Проверяем кэш
    cached = get_cached_results(dork)
    if cached is not None:
        logger.info(f"💾 Используем кэш для прямого дорка: {dork[:40]}...")
        all_results = cached
    else:
        logger.info(f"🔎 Прямой поиск по дорку: {dork}")
        results = await _searxng_search(dork, num_results=10)
        all_results = results
        if all_results:
            save_to_cache(dork, all_results, is_news=False)

    # Фильтрация и контекст
    relevant = _filter_relevant_results(all_results, dork)
    context_text = _build_context(relevant[:10])

    prompt = ON_DEMAND_USER.format(
        query=dork,
        date=datetime.now().strftime("%d %B %Y"),
        context=context_text
    )

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
                    error_text = await resp.text()
                    logger.error(f"Groq error (direct): {error_text}")
                    return {"summary": f"⚠️ Ошибка Groq: {resp.status}", "label": label}
                data = await resp.json()
                summary = data["choices"][0]["message"]["content"]
                return {"summary": summary, "label": label}
    except Exception as e:
        logger.error(f"Ошибка Groq (direct): {e}")
        return {"summary": f"⚠️ Ошибка генерации: {e}", "label": label}


async def search_on_demand(query: str, context: str = "") -> dict:
    """RAG-поиск с кэшированием: кэш → LLM-дорки → SearXNG → Groq саммари."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return {"summary": "⚠️ GROQ_API_KEY не задан", "label": query[:25]}

    # 1. Проверяем Search Memory
    cached = get_cached_results(query)
    label = query[:25]  # Фолбэк для label
    
    if cached is not None:
        logger.info(f"💾 Используем кэш для: {query}")
        all_results = cached
    else:
        # 2. Генерируем дорки и ищем
        logger.info(f"🧠 Генерация дорков для: {query}")
        gen_result = await generate_dorks(query, context)
        
        # Распаковка: generate_dorks может вернуть tuple или list
        if isinstance(gen_result, tuple):
            label, dorks = gen_result
        else:
            dorks = gen_result

        all_results = []
        seen_urls = set()

        for dork in dorks:
            logger.info(f"🔎 Поиск по дорку: {dork}")
            results = await _searxng_search(dork, num_results=5)
            for r in results:
                if r["url"] not in seen_urls:
                    seen_urls.add(r["url"])
                    all_results.append(r)
            await asyncio.sleep(1.5)

        # Сохраняем в кэш только если есть результаты
        if all_results:
            save_to_cache(query, all_results, is_news=True)

    # 3. Фильтрация и формирование контекста
    relevant_results = _filter_relevant_results(all_results, query)
    context_text = _build_context(relevant_results[:10])

    # 4. Отправка в Groq
    prompt = ON_DEMAND_USER.format(
        query=query,
        date=datetime.now().strftime("%d %B %Y"),
        context=context_text
    )

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
                    error_text = await resp.text()
                    logger.error(f"Groq error: {error_text}")
                    return {"summary": f"⚠️ Ошибка Groq: {resp.status}", "label": label}
                data = await resp.json()
                summary = data["choices"][0]["message"]["content"]
                return {"summary": summary, "label": label}
    except Exception as e:
        logger.error(f"Ошибка Groq: {e}")
        return {"summary": f"⚠️ Ошибка генерации: {e}", "label": label}


async def generate_summary(item: dict) -> str:
    """Генерирует MINT OSINT саммари для RSS-алертов."""
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
