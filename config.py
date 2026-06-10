"""Конфигурация мониторинга."""
from pathlib import Path

# === ЦЕЛИ МОНИТОРИНГА ===
TARGETS = {
    "donetsk_region": {
        "name": "Донецкая область",
        "keywords": ["Донецк", "Маріуполь", "Бахмут", "Авдіївка", "Покровськ", "обстріл", "приліт", "вибух", "Путин"],
        "hashtags": ["#Донецк", "#Донбас", "#Donetsk", "#Avdiivka"],
    },
    # Легко добавить новую цель:
    # "kharkiv_region": { ... }
}

# === ИСТОЧНИКИ (RSS) ===
RSS_FEEDS = [
    "https://rss.dw.com/xml/rss-ru-all",
    "https://www.radiosvoboda.org/api/zqkue-qmm-k",  # Радіо Свобода
    "https://www.ukrinform.ua/rss/block-lastnews",
    "https://armyinform.com.ua/feed/",
    "https://sprotyv.mod.gov.ua/feed/",
 # "https://susilne.news/rss/",                     # Суспільне
]

# === НАСТРОЙКИ ===
STATE_FILE = Path("state.json")
MAX_ITEMS_PER_FEED = 10  # Сколько последних новостей проверять из каждого фида
GROQ_MODEL = "llama-3.3-70b-versatile"  # Актуальная текстовая модель (не vision!)
