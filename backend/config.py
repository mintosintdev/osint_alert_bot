"""Конфигурация проекта. Все секреты тянем строго из .env"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Загружаем переменные из файла .env
load_dotenv()

# === СЕКРЕТЫ (Обязательно должны быть в .env) ===
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Проверка на наличие критических ключей при старте
if not TG_BOT_TOKEN:
    raise ValueError("❌ Ошибка: TG_BOT_TOKEN не найден в файле .env")
if not GROQ_API_KEY:
    raise ValueError("❌ Ошибка: GROQ_API_KEY не найден в файле .env")

# === НАСТРОЙКИ МОДЕЛЕЙ ===
# Текстовая модель для дорков и саммари
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"
# Визион-модель для анализа PDF/картинок
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"

# === ПУТИ И ФАЙЛЫ ===
BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "state.json"      # Для хранения RSS-состояния
DB_FILE = BASE_DIR / "search_memory.db"   # SQLite база для кэша поисков

# === НАСТРОЙКИ ПОИСКА И RSS ===
SEARXNG_URL = "http://localhost:8304/search" # Адрес твоего локального SearXNG
RSS_FEEDS = [
    "https://rss.dw.com/xml/rss-ru-all",
    "https://www.radiosvoboda.org/api/zqkue-qmm-k",
    "https://www.ukrinform.ua/rss/block-lastnews",
    "https://armyinform.com.ua/feed/",
    "https://sprotyv.mod.gov.ua/feed/",
]
MAX_ITEMS_PER_FEED = 10  # Сколько последних новостей парсить из каждого фида

# === ТАЙМАУТЫ И ЛИМИТЫ ===
SEARCH_CACHE_TTL_HOURS = 24  # Время жизни кэша поисковых запросов
REQUEST_TIMEOUT = 30         # Таймаут запросов к API
