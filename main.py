"""OSINT Alert Bot MVP."""
import asyncio
import argparse
import logging
from config import TARGETS, STATE_FILE
from monitor import collect_alerts
from summarizer import generate_summary
from notifier import send_telegram
from state_manager import StateManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="🤖 OSINT Alert Bot — мониторинг новостей с AI-саммари и TG-уведомлениями",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
💡 Примеры использования:
  python main.py                          # Запуск с целями из config.py
  python main.py --interactive            # Интерактивный режим (бот спросит что мониторить в TG)
  python main.py --query "Харьков обстріл" # Мониторинг по произвольному запросу
  python main.py --dry-run                # Тест без отправки в Telegram

📁 Структура проекта:
  config.py          # Цели мониторинга, RSS-фиды, настройки
  .env               # Секреты (GROQ_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID)
  state.json         # Дедупликация (создаётся автоматически)
  monitor.py         # Сбор и фильтрация новостей
  summarizer.py      # Генерация MINT OSINT саммари через Groq
  notifier.py        # Отправка уведомлений в Telegram
  state_manager.py   # Управление состоянием (предотвращение спама)

⚙️ Настройка:
  1. Скопируйте .env.example → .env
  2. Заполните GROQ_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID
  3. Настройте цели в config.py
  4. Запустите: python main.py
        """
    )
    
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Интерактивный режим: бот спросит цель мониторинга в Telegram перед запуском"
    )
    parser.add_argument(
        "--query", "-q",
        type=str,
        default=None,
        help="Произвольный запрос для мониторинга (переопределяет цели из config.py)"
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Тестовый режим: собирает и анализирует новости, но НЕ отправляет в Telegram"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод (DEBUG уровень логирования)"
    )
    
    return parser.parse_args()


async def run(interactive=False, query=None, dry_run=False):
    logger.info("🚀 Запуск OSINT Alert Bot...")
    
    if interactive:
        logger.info("💬 Интерактивный режим: ожидание ответа в Telegram...")
        # TODO: Реализовать ожидание ответа от пользователя в TG
        # Пока что fallback на конфиг
        logger.warning("⚠️ Интерактивный режим ещё не реализован, используем config.py")
    
    if query:
        logger.info(f"🎯 Кастомный запрос: {query}")
        # TODO: Переопределить TARGETS на основе query
    
    sm = StateManager(STATE_FILE)
    alerts = await collect_alerts(TARGETS if not query else None)

    new_count = 0
    for alert in alerts:
        if sm.is_seen(alert["id"]):
            continue

        logger.info(f"🆕 Новая цель: {alert['target']} | {alert['title'][:60]}...")
        summary = await generate_summary(alert)
        message = f"{summary}\n\n🏷️ *Цель:* {alert['target']}"
        
        if dry_run:
            logger.info(f"📝 [DRY-RUN] Сообщение:\n{message}")
        else:
            await send_telegram(message)
        
        sm.mark_seen(alert["id"])
        new_count += 1

    logger.info(f"✅ Обработано {new_count} новых алертов из {len(alerts)} найденных")


if __name__ == "__main__":
    args = parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    asyncio.run(run(
        interactive=args.interactive,
        query=args.query,
        dry_run=args.dry_run
    ))
