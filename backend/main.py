"""OSINT Alert Bot MVP - Main Controller."""
import asyncio
import argparse
import logging
import time
from config import STATE_FILE
from monitor import collect_alerts
from summarizer import generate_summary, search_on_demand
from notifier import send_telegram
from state_manager import StateManager

logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Интервал проверки RSS (в секундах). Для теста поставь 60, для продакшена 300-600
CHECK_INTERVAL = 60 

def parse_args():
    parser = argparse.ArgumentParser(description="🤖 OSINT Alert Bot")
    parser.add_argument("--query", "-q", type=str, default=None, help="Поиск по запросу (RAG)")
    parser.add_argument("--dry-run", "-d", action="store_true", help="Тест без отправки в ТГ")
    parser.add_argument("--loop", "-l", action="store_true", help="Запустить в цикле мониторинга")
    return parser.parse_args()

async def process_rss_alerts(dry_run=False):
    """Основной цикл обработки RSS новостей."""
    logger.info("🔄 Начало цикла сбора RSS...")
    
    # 1. Собираем новости
    raw_alerts = await collect_alerts()
    if not raw_alerts:
        logger.info(" Новых релевантных новостей не найдено.")
        return

    # 2. Инициализируем менеджер состояний (дедупликация)
    state_mgr = StateManager(STATE_FILE)
    await state_mgr.load()

    new_alerts_count = 0
    for item in raw_alerts:
        item_id = item['id']
        
        # 3. Проверка на дубликаты
        if state_mgr.is_seen(item_id):
            continue
            
        logger.info(f"🆕 Новая новость: {item['title'][:50]}...")
        new_alerts_count += 1

        # 4. Генерация MINT OSINT саммари
        try:
            # Формируем объект для саммаризатора
            mint_item = {
                "title": item['title'],
                "summary": item['summary'][:1000], # Обрезаем слишком длинные summaries
                "link": item['link'],
                "target": item['target']
            }
            
            logger.info(f"🧠 Генерация саммари для: {item['title'][:30]}...")
            mint_summary = await generate_summary(mint_item)
            
            # 5. Формирование сообщения
            message = f"🚨 <b>{item['target']}</b>\n\n{mint_summary}\n\n <a href='{item['link']}'>Источник</a>"
            
            # 6. Отправка или лог
            if dry_run:
                logger.info(f"📝 [DRY-RUN] Сообщение:\n{message}")
            else:
                await send_telegram(message)
                
            # 7. Сохраняем ID как обработанный
            state_mgr.mark_seen(item_id)
            
            # Небольшая пауза, чтобы не спамить API
            await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"❌ Ошибка обработки новости {item_id}: {e}")

    # Сохраняем состояние после пачки новостей
    await state_mgr.save()
    logger.info(f"✅ Цикл завершен. Обработано новых новостей: {new_alerts_count}")

async def run_query_search(query: str, dry_run: bool):
    """Обработка одиночного поискового запроса (RAG)."""
    logger.info(f" Поиск по запросу: '{query}'")
    
    try:
        result_data = await search_on_demand(query)
        summary = result_data["summary"]
        label = result_data["label"]
        
        message = f"🔍 <b>Результат поиска: {label}</b>\n\n{summary}"
        
        if dry_run:
            logger.info(f"📝 [DRY-RUN] Сообщение:\n{message}")
        else:
            await send_telegram(message)
            
        logger.info("✅ Поиск завершен.")
    except Exception as e:
        logger.error(f" Ошибка поиска: {e}")

async def main_loop(dry_run=False):
    """Бесконечный цикл мониторинга."""
    logger.info("🚀 Запуск OSINT Bot в режиме мониторинга...")
    while True:
        try:
            await process_rss_alerts(dry_run=dry_run)
        except Exception as e:
            logger.error(f" Критическая ошибка в цикле: {e}")
        
        logger.info(f" Сон на {CHECK_INTERVAL} секунд...")
        await asyncio.sleep(CHECK_INTERVAL)

async def run(args):
    if args.query:
        await run_query_search(args.query, args.dry_run)
    elif args.loop:
        await main_loop(dry_run=args.dry_run)
    else:
        # Однократный запуск RSS
        await process_rss_alerts(dry_run=args.dry_run)

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args))
