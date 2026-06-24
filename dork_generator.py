"""Генерация OSINT-дорков через Groq Llama-3.3-70b."""
import json
import logging
import os
from groq import Groq
from config import GROQ_MODEL

logger = logging.getLogger(__name__)

# Универсальный промпт для ГЛОБАЛЬНОГО поиска
DORK_SYSTEM_PROMPT = """You are an elite OSINT analyst specializing in advanced search operators for SearXNG.
Generate 3-5 precise search dorks based on the user's query and context.

RULES:
- Use operators: site:, intitle:, intext:, filetype:, OR, "", -
- For Telegram: site:t.me OR site:teletype.in
- Always generate variants in relevant languages (en + original language)
- NEVER use date operators
- Return ONLY valid JSON with this EXACT structure:
  {"label": "short topic tag max 30 chars", "dorks": ["dork1", "dork2"]}
- "label" must be a concise summary of the search intent in Russian/Ukrainian (e.g., "КПП Краковец", "Фронт Покровск")
- No explanations, just raw JSON"""


async def generate_dorks(query: str, context: str = "") -> list[str]:
    """
    Генерирует поисковые дорки через LLM.
    
    Args:
        query: Поисковый запрос пользователя
        context: Дополнительный контекст (ключевые слова цели, регион и т.д.)
    
    Returns:
        Список готовых дорков для SearXNG
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("❌ GROQ_API_KEY не найден в переменных окружения")
        return [query]  # Фолбэк на сырой запрос
    
    client = Groq(api_key=api_key)
    user_prompt = f"Query: {query}\nContext: {context}" if context else f"Query: {query}"
    
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": DORK_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=400,
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content.strip()
        data = json.loads(content)
        dorks = data.get("dorks", [])
        
        if not dorks:
            logger.warning(f"⚠️ LLM вернул пустой список дорков для: {query}")
            return [query]
            
        logger.info(f"🧠 Сгенерировано {len(dorks)} дорков для '{query}':")
        for d in dorks:
            logger.debug(f"   → {d}")
            
        return dorks
        
    except json.JSONDecodeError as e:
        logger.error(f"❌ Невалидный JSON от LLM: {e}\nRaw: {content[:200]}")
        return [query]
    except Exception as e:
        logger.error(f"❌ Ошибка генерации дорков: {e}")
        return [query]
