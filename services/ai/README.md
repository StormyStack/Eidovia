# EduAR-AI: AI Microservice

RAG-based tutoring + contextual bandit for an AR biology learning app.

**Stack:** Python 3.11 · FastAPI · PostgreSQL 16 + pgvector · Redis 7 · Docker  
**Status:** Prototype — retrieval and cache working end-to-end.

---

## Prerequisites

- Docker Desktop (running)
- Python 3.11
- Git

---

## Quick Start

### 1. Clone

```powershell
git clone https://github.com/StormyStack/Thesis.git
cd Thesis\AI
git checkout AI_Code_Works
```

### 2. Configure `.env`

```powershell
Copy-Item .env.example .env
notepad .env
```

Set these two values (get passwords from SE):

```env
DB_PASSWORD=your_password
REDIS_PASSWORD=your_password
```

> **Important:** Port `5432` is blocked by Windows Hyper-V. The `.env` already uses port `6543` as the host-side mapping — do not change it.

### 3. Start all services

```powershell
docker-compose up -d --build
```

This builds the AI image and starts all three containers: PostgreSQL, Redis, and the AI service.  
First build takes **15–40 minutes** (PyTorch download). Subsequent starts are instant.

Wait until all three are healthy:

```powershell
docker-compose ps
```

### 4. Load the curriculum (first time only)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python load_curriculum.py
```

### 5. Verify

```powershell
# Health check
curl http://localhost:8001/health

# Ask a question
$body = '{"question":"What is DNA?"}'
curl -s -X POST http://localhost:8001/api/chat -H "Content-Type: application/json" -d $body

# Cache stats
curl http://localhost:8001/api/cache-stats
```

Expected health response:
```json
{
  "status": "healthy",
  "database": "connected",
  "cache": "connected",
  "rag_ready": true
}
```

### Stop

```powershell
docker-compose down
```

---

## Ports

| Service | Host port | Notes |
|---|---|---|
| AI service | `8001` | REST + WebSocket |
| PostgreSQL | `6543` | Changed from 5432 — blocked by Hyper-V on this machine |
| Redis | `6379` | |

---

## Key environment variables

| Variable | Default | Notes |
|---|---|---|
| `DB_PASSWORD` | required | Raw value — code auto-encodes it |
| `REDIS_PASSWORD` | required | Raw value — code auto-encodes it |
| `POSTGRES_PORT` | `6543` | Host-side port (container still uses 5432 internally) |
| `RAG_TIMEOUT` | `5.0` | Seconds — 1.5 is too tight on CPU |
| `MOCK_LLM` | `True` | Returns retrieved text; no LLM |

---

## API

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Service health |
| `/api/chat` | POST | Ask a biology question |
| `/api/cache-stats` | GET | Redis hit/miss stats |
| `/api/cache-flush` | POST | Clear Redis cache |
| `/ws/adapt/{session_id}` | WS | Adaptive learning (prototype) |

**Chat request:**
```json
{ "question": "What is DNA?" }
```

**Chat response:**
```json
{
  "answer": "Based on the curriculum: ...",
  "is_on_topic": true,
  "max_similarity": 0.567,
  "num_documents": 3,
  "latency_ms": 316,
  "cached": false
}
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `bind: access denied` on port 5432/5433 | Windows Hyper-V blocks those ports. Use `POSTGRES_PORT=6543` in `.env` |
| `No module named 'greenlet'` | Use `SQLAlchemy[asyncio]` in `requirements.txt` (already fixed) |
| `Query encoding timeout` | Set `RAG_TIMEOUT=5.0` in `.env` (already fixed) |
| Container still loading | Wait 40s after `docker-compose up`; `docker logs eduarai_ai --tail 30` |
| No documents returned | Run `python load_curriculum.py` |
| `docker-compose up` fails missing DB_PASSWORD | Fill in `.env` from `.env.example` |

---

## Verified results (this machine)

| | |
|---|---|
| All 3 containers | healthy |
| Curriculum chunks | 18 |
| `POST /api/chat` cold | ~316 ms, similarity 0.567 |
| `POST /api/chat` cached | ~4 ms (80× faster) |
| Redis | connected, 40% hit rate |
