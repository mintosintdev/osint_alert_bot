"""Border Sentinel Backend - Enhanced Analytics & Search"""
import os, json, sqlite3, time, uuid, aiohttp
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Border Sentinel API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8304/search")
DB_FILE = Path("border_sentinel.db")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# === DATABASE SETUP ===
def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS searches (
        id TEXT PRIMARY KEY,
        query TEXT,
        target_date TEXT,
        coordinates TEXT,
        timestamp TEXT,
        duration REAL,
        dorks TEXT,
        results TEXT,
        analysis TEXT,
        total_results INTEGER
    )''')
    conn.commit()
    conn.close()

init_db()

# === MODELS ===
class SearchRequest(BaseModel):
    query: str
    target_date: Optional[str] = None
    coordinates: Optional[List[dict]] = None

class AnalyzeRequest(BaseModel):
    search_id: str  # Анализируем конкретный поиск по ID, а не просто текст

# === CORE FUNCTIONS ===
def generate_dorks(query: str, coords: List[dict] = None, date: str = None) -> List[str]:
    """Генерация умных OSINT-дорков"""
    dorks = [f'"{query}"']
    
    # Документы и отчеты
    dorks.append(f'{query} filetype:pdf')
    dorks.append(f'{query} filetype:xlsx OR filetype:csv')
    
    # Госструктуры и тендеры
    dorks.append(f'site:gov.ua "{query}"')
    dorks.append(f'site:prozorro.gov.ua "{query}"')
    
    # Геолокация (если есть координаты)
    if coords:
        for coord in coords[:2]:
            lat, lng = round(coord['lat'], 3), round(coord['lng'], 3)
            dorks.append(f'"{query}" near "{lat},{lng}"')
            dorks.append(f'"{query}" logistics border {lat} {lng}')
    
    # Временной фильтр
    if date:
        dorks.append(f'"{query}" after:{date}')
        
    return list(set(dorks))

async def searxng_search(query: str, num_results: int = 10) -> List[dict]:
    """Поиск через SearXNG"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SEARXNG_URL,
                params={"q": query, "format": "json", "pageno": 1},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200: return []
                data = await resp.json()
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:600] if r.get("content") else ""
                    }
                    for r in data.get("results", [])[:num_results]
                ]
    except Exception as e:
        print(f"SearXNG error: {e}")
        return []

def extract_entities(results: List[dict]) -> List[dict]:
    """Извлечение сущностей для графа (базовая версия)"""
    entities = []
    seen = set()
    for r in results[:15]:
        title = r.get("title", "").strip()
        if title and len(title) > 5 and title not in seen:
            entities.append({
                "id": hash(title) % 100000,
                "name": title[:80],
                "type": "document",
                "color": "#D0BCFF"
            })
            seen.add(title)
    return entities[:12]

# === ENDPOINTS ===
@app.post("/api/search")
async def search(req: SearchRequest):
    if not client: raise HTTPException(500, "GROQ_API_KEY not configured")
    
    search_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    dorks = generate_dorks(req.query, req.coordinates, req.target_date)
    
    all_results = []
    for dork in dorks[:6]:
        results = await searxng_search(dork, num_results=5)
        all_results.extend(results)
    
    # Дедупликация
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)
    
    entities = extract_entities(unique_results)
    
    # Сохранение в БД
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO searches VALUES (?,?,?,?,?,?,?,?,?,?)''', (
        search_id, req.query, req.target_date,
        json.dumps(req.coordinates or []),
        datetime.now().isoformat(),
        round(time.time() - start_time, 2),
        json.dumps(dorks),
        json.dumps(unique_results[:25]),
        json.dumps({"entities": entities}),
        len(unique_results)
    ))
    conn.commit()
    conn.close()
    
    return {
        "id": search_id,
        "query": req.query,
        "dorks": dorks,
        "results": unique_results[:25],
        "entities": entities,
        "total_results": len(unique_results),
        "duration": round(time.time() - start_time, 2),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    """Глубокий анализ результатов конкретного поиска"""
    if not client: raise HTTPException(500, "GROQ_API_KEY not configured")
    
    # Получаем реальные результаты из БД
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT query, results FROM searches WHERE id=?", (req.search_id,))
    row = c.fetchone()
    conn.close()
    
    if not row: raise HTTPException(404, "Search not found")
    
    original_query = row[0]
    try:
        results = json.loads(row[1])
    except:
        results = []
        
    if not results:
        return {"summary": "No data to analyze.", "key_entities": [], "suggested_dorks": []}

    # Формируем контекст для LLM
    context = "\n\n".join([
        f"[{i+1}] TITLE: {r.get('title','')}\nSNIPPET: {r.get('content','')[:400]}\nURL: {r.get('url','')}"
        for i, r in enumerate(results[:12])
    ])

    prompt = f"""You are an elite OSINT Analyst. Analyze the search results below for the query: "{original_query}".

SEARCH RESULTS:
{context}

TASK:
1. SUMMARY: Write a concise intelligence briefing (3-5 sentences). What do these results reveal? Identify patterns, key events, or red flags.
2. KEY ENTITIES: Extract 3-7 specific entities (company names, people, locations, organizations) mentioned in the snippets that are relevant to the investigation.
3. NEXT STEPS: Suggest 3-5 highly specific follow-up Google Dorks based on GAPS in the current results or interesting leads found. Do NOT repeat the original query.

OUTPUT FORMAT (STRICT JSON):
{{
  "summary": "string",
  "key_entities": ["string", "string"],
  "suggested_dorks": ["string", "string"]
}}

RULES:
- Be factual. Only use information from the provided snippets.
- If no relevant info is found, say so clearly in the summary.
- Suggested dorks must be advanced (use site:, filetype:, quotes, OR operators).
- Output MUST be valid JSON only."""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1200,
            response_format={"type": "json_object"}
        )
        return json.loads(completion.choices[0].message.content)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

@app.get("/api/stats")
async def get_stats():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM searches")
    total_searches = c.fetchone()[0]
    c.execute("SELECT results FROM searches")
    rows = c.fetchall()
    conn.close()
    
    total_results = 0
    sources = set()
    for row in rows:
        try:
            res = json.loads(row[0])
            total_results += len(res)
            for r in res:
                try: sources.add(r["url"].split("//")[1].split("/")[0])
                except: pass
        except: pass
    
    return {
        "total_searches": total_searches,
        "total_results": total_results,
        "unique_sources": len(sources)
    }

@app.get("/api/history")
async def get_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, query, target_date, timestamp, total_results FROM searches ORDER BY timestamp DESC LIMIT 30")
    rows = c.fetchall()
    conn.close()
    return [{"id": r[0], "query": r[1], "target_date": r[2], "timestamp": r[3], "total_results": r[4]} for r in rows]

@app.get("/api/search/{search_id}")
async def get_search_detail(search_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM searches WHERE id=?", (search_id,))
    row = c.fetchone()
    conn.close()
    if not row: raise HTTPException(404, "Not found")
    return {
        "id": row[0], "query": row[1], "target_date": row[2],
        "coordinates": json.loads(row[3]), "timestamp": row[4],
        "duration": row[5], "dorks": json.loads(row[6]),
        "results": json.loads(row[7]), "analysis": json.loads(row[8]),
        "total_results": row[9]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
