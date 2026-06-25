"""Border Sentinel Backend - Fully Functional"""
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

# Database setup
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

class SearchRequest(BaseModel):
    query: str
    target_date: Optional[str] = None
    coordinates: Optional[List[dict]] = None

class AnalyzeRequest(BaseModel):
    query: str

def generate_dorks(query: str, coords: List[dict] = None, date: str = None) -> List[str]:
    """Generate OSINT dorks with location awareness"""
    dorks = []
    
    # Base dorks
    dorks.append(f'"{query}"')
    dorks.append(f'{query} filetype:pdf')
    dorks.append(f'site:gov.ua "{query}"')
    
    # Add location-based dorks if coordinates exist
    if coords:
        for coord in coords[:3]:  # Max 3 locations
            lat, lng = coord['lat'], coord['lng']
            dorks.append(f'{query} near "{lat},{lng}"')
            dorks.append(f'{query} logistics border {lat} {lng}')
    
    # Add date filter if exists
    if date:
        dorks.append(f'{query} after:{date}')
    
    return list(set(dorks))  # Remove duplicates

async def searxng_search(query: str, num_results: int = 10) -> List[dict]:
    """Search via SearXNG"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                SEARXNG_URL,
                params={"q": query, "format": "json", "pageno": 1},
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:500] if r.get("content") else ""
                    }
                    for r in data.get("results", [])[:num_results]
                ]
    except Exception as e:
        print(f"SearXNG error: {e}")
        return []

def extract_entities(results: List[dict]) -> List[dict]:
    """Extract entities from search results"""
    entities = []
    seen = set()
    
    for r in results[:10]:
        # Simple entity extraction (can be improved with NLP)
        title = r.get("title", "")
        if title and title not in seen:
            entities.append({
                "name": title[:100],
                "type": "document",
                "color": "#D0BCFF",
                "related_to": []
            })
            seen.add(title)
    
    return entities[:8]  # Max 8 entities for graph

@app.post("/api/search")
async def search(req: SearchRequest):
    if not client:
        raise HTTPException(500, "GROQ_API_KEY not configured")
    
    search_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    
    # Generate dorks
    dorks = generate_dorks(req.query, req.coordinates, req.target_date)
    
    # Search all dorks
    all_results = []
    per_dork = {}
    
    for dork in dorks[:5]:  # Max 5 dorks to avoid timeout
        results = await searxng_search(dork, num_results=5)
        per_dork[dork] = len(results)
        all_results.extend(results)
    
    # Remove duplicates by URL
    seen_urls = set()
    unique_results = []
    for r in all_results:
        if r["url"] not in seen_urls:
            seen_urls.add(r["url"])
            unique_results.append(r)
    
    # Extract entities for graph
    entities = extract_entities(unique_results)
    
    # Save to database
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''INSERT INTO searches VALUES (?,?,?,?,?,?,?,?,?,?)''', (
        search_id, req.query, req.target_date,
        json.dumps(req.coordinates or []),
        datetime.now().isoformat(),
        round(time.time() - start_time, 2),
        json.dumps(dorks),
        json.dumps(unique_results[:20]),
        json.dumps({"entities": entities}),
        len(unique_results)
    ))
    conn.commit()
    conn.close()
    
    return {
        "id": search_id,
        "query": req.query,
        "dorks": dorks,
        "results": unique_results[:20],
        "entities": entities,
        "total_results": len(unique_results),
        "duration": round(time.time() - start_time, 2),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest):
    if not client:
        raise HTTPException(500, "GROQ_API_KEY not configured")
    
    prompt = f"""You are an OSINT analyst. Analyze this search query and provide actionable intelligence:

Query: {req.query}

Provide:
1. Brief summary of what this query might reveal
2. 3-5 suggested follow-up search queries
3. Key entities or topics to monitor

Format as JSON with keys: summary, suggested_queries, entities_to_watch"""

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=800,
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
    total_results = 0
    sources = set()
    
    for row in rows:
        try:
            results = json.loads(row[0])
            total_results += len(results)
            for r in results:
                if "url" in r:
                    try:
                        domain = r["url"].split("//")[1].split("/")[0]
                        sources.add(domain)
                    except:
                        pass
        except:
            pass
    
    conn.close()
    
    return {
        "total_searches": total_searches,
        "total_results": total_results,
        "unique_sources": len(sources)
    }

@app.get("/api/history")
async def get_history():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT id, query, target_date, timestamp, total_results FROM searches ORDER BY timestamp DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    
    return [
        {
            "id": r[0],
            "query": r[1],
            "target_date": r[2],
            "timestamp": r[3],
            "total_results": r[4]
        }
        for r in rows
    ]

@app.get("/api/search/{search_id}")
async def get_search_detail(search_id: str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM searches WHERE id=?", (search_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, "Search not found")
    
    return {
        "id": row[0],
        "query": row[1],
        "target_date": row[2],
        "coordinates": json.loads(row[3]),
        "timestamp": row[4],
        "duration": row[5],
        "dorks": json.loads(row[6]),
        "results": json.loads(row[7]),
        "analysis": json.loads(row[8]),
        "total_results": row[9]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
