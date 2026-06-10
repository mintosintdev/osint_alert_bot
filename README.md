# OSINT Alert Bot

AI-powered OSINT monitoring with Telegram integration. RAG search via SearXNG + Groq LLM summarization.

## Features
- On-demand search with verified sources (no hallucinations)
- Automated RSS monitoring with keyword filtering
- Structured MINT OSINT summaries via Groq
- Telegram commands: /search, /add, /list, /help
- Self-hosted SearXNG (no external news API keys needed)
- JSON-based deduplication

## Quick Start
1. Run SearXNG: `docker run -d --name searxng -p 8304:8080 searxng/searxng:latest`
2. Copy `.env.example` → `.env`, fill GROQ_API_KEY, TG_BOT_TOKEN, TG_CHAT_ID
3. Install: `pip install -r requirements.txt`
4. Run interactive: `python tg_controller.py` or scheduled: `python main.py`

## Tech Stack
Python 3.10+, asyncio, aiohttp, SearXNG, Groq (llama-3.3-70b-versatile), python-telegram-bot, feedparser, Docker

## Disclaimer
For educational and legitimate OSINT research only. Users responsible for compliance with laws and platform ToS.

## License
MIT
