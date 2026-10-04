# EduAR-AI: AI Microservice

Grounded tutoring and real-time adaptation for an AR biology learning app (DNA and cell biology).

**Role:** AI Engineer (Shabab) | **Repo:** `StormyStack/Thesis` | **Branch:** `AI_Code_Works`
**Stack:** Python 3.11, FastAPI, PostgreSQL 16 + pgvector, Redis 7, Docker
**Status:** thesis prototype. Retrieval works end to end; cache, ETL and the WebSocket loop are not finished (see [Current status](#current-status)).
**Last updated:** 4 October 2026

> Documentation history: [`final.md`](final.md) is the consolidated Week 4 report. It was written before the Week 5 work and contains targets and numbers that were never measured (for example a 45 ms retrieval time, a 450 MB image and "production ready"). **Where `final.md` and this README disagree, this README is correct.**

---

## Contents

1. [What this is](#what-this-is)
2. [Current status](#current-status)
3. [Architecture](#architecture)
4. [Repository layout](#repository-layout)
5. [Tech stack](#tech-stack)
6. [Quick start (Windows / PowerShell)](#quick-start-windows--powershell)
7. [Configuration](#configuration)
8. [API reference](#api-reference)
9. [How it works](#how-it-works)
10. [Database schema](#database-schema)
11. [Docker notes](#docker-notes)
12. [Verified results](#verified-results)
13. [Known issues](#known-issues)
14. [Troubleshooting](#troubleshooting)
15. [Roadmap](#roadmap)
16. [Git workflow](#git-workflow)
17. [Team and references](#team-and-references)

---

## What this is

EduAR-AI is an augmented-reality learning app. This repository holds the **AI microservice** (internal service on port 8001). It does two jobs:

1. **Tutoring with a guardrail.** A student question is embedded, matched against the curriculum stored in PostgreSQL with pgvector, and answered only from retrieved curriculum text. Questions that are not similar enough to the curriculum (cosine similarity below 0.40) are treated as off-topic.
2. **Real-time adaptation.** A contextual bandit chooses one of 8 pedagogical actions (show a hint, change difficulty, suggest a quiz, and so on) from an 8-dimensional learner state.

Redis is meant to sit in front of PostgreSQL as a cache (cache first, database on a miss).

The Gateway (port 8000), PostgreSQL/Redis setup and schema are owned by the System Engineer. The AR scenes (Unity) and the mobile app (React Native) are owned by two other team members. Clients reach this service through the Gateway.

## Current status

| Area | Status | Notes |
|---|---|---|
| Docker stack (PostgreSQL + pgvector, Redis) | Working | SE's `docker-compose.yml`, both containers healthy |
| Curriculum in pgvector | Working | 18 chunks, 384-dim embeddings, module `DNA_BIOLOGY_001` |
| RAG retrieval and guardrail | Working | Live test: 3 documents, similarity 0.567, on-topic |
| `GET /health`, `POST /api/chat` | Working | Verified live |
| Async database sessions | Working | `get_session()` is an async context manager |
| Redis cache layer | **Coded, not connecting** | Wrong URL passed to the cache client; fix in [Known issues](#known-issues) |
| WebSocket `/ws/adapt/{session_id}` | **Prototype, not tested** | Uses a random state vector; frame format differs from the spec |
| Contextual bandit | Epsilon-greedy baseline | Per-action mean reward; the state vector is validated but not used in the score |
| Scheduler / ETL | **Disabled** | Start calls are commented out in `main_service.py` |
| Event logging (A.3) | **Drafted, not run** | `events` table exists in SE's schema; `event_service.py` needs changes |
| Answer generation | Template only | `MOCK_LLM=True`: the reply is the retrieved text, no language model |
| Automated tests | Not run in Week 5 | `test_integration.py` exists from Week 4 |
| Latency / memory SLAs | Not measured | One live request measured: about 570 ms (cache miss) |

## Architecture

```mermaid
flowchart LR
    U[Unity AR game] --> G[Gateway :8000<br/>System Engineer]
    R[React Native app] --> G
    G -->|REST /api/chat| A[AI service :8001<br/>FastAPI]
    G -->|WS /ws/adapt| A
    A -->|cache-first| C[(Redis 7 :6379)]
    A -->|SQL + vector search| P[(PostgreSQL 16 + pgvector :5432)]
    G -.->|logs learner events| P
```

Chat request flow:

```mermaid
flowchart LR
    Q[POST /api/chat] --> E[Embed question<br/>all-MiniLM-L6-v2]
    E --> K{Redis hit?}
    K -- yes --> X[Use cached context]
    K -- no --> S[pgvector cosine search<br/>top-3]
    S --> T{similarity >= 0.40?}
    X --> T
    T -- yes --> A1[Curriculum answer]
    T -- no --> A2[Off-topic reply]
    A1 --> B[Bandit picks an action<br/>decision_id returned]
    A2 --> B
```

The AI service is internal. Authentication, rate limiting and HTTPS are expected to be handled by the Gateway.

## Repository layout

```
.
├── main_service.py            FastAPI app: endpoints, startup/shutdown
├── config_prod.py             Settings from environment variables
├── database_service.py        Async SQLAlchemy engine, pool, session manager
├── rag_service.py             Embedding, pgvector search, guardrail, cache-first retrieval
├── cache_service.py           Redis cache client with hit/miss stats
├── bandit_service.py          Epsilon-greedy contextual bandit (8 actions)
├── scheduler_service.py       APScheduler ETL job (currently disabled)
├── event_service.py           Event logging draft (not wired or tested; see Known issues)
├── load_curriculum.py         Chunk, embed and load the curriculum into pgvector
├── create_curriculum.py       Helper used to build the curriculum text
├── expanded_dna_curriculum.txt  Curriculum text that is loaded (8,740 characters)
├── dna_curriculum.txt         Original curriculum text
├── test_integration.py        Integration tests (Week 4; not re-run in Week 5)
├── client_examples.py         Example REST and WebSocket clients
├── Dockerfile                 Multi-stage image for the AI service
├── docker-compose.yml         PostgreSQL + Redis (owned by SE; do not modify)
├── 01_schema.sql              Database schema (owned by SE)
├── requirements.txt           Pinned Python dependencies
├── .env.example               Template for .env (placeholders only)
├── .dockerignore
└── final.md                   Week 4 consolidated report (historical)
```

`.env` is local only and must never be committed.

## Tech stack

| Technology | Role |
|---|---|
| Python 3.11 | Language and runtime |
| FastAPI, Uvicorn, Pydantic | REST and WebSocket server, request validation (4 workers in the container) |
| sentence-transformers, `all-MiniLM-L6-v2` | Text embeddings, 384 dimensions, CPU only |
| PostgreSQL 16 + pgvector | Relational data and vector similarity search (cosine, IVFFlat index) |
| SQLAlchemy 2.0 (async) + asyncpg | Database access and connection pool |
| Redis 7 + redis-py (asyncio) | Cache and learner state |
| APScheduler | Periodic ETL job (designed; disabled) |
| NumPy | Vectors and bandit math |
| Docker, Docker Compose | Packaging and local deployment |

## Quick start (Windows / PowerShell)

Prerequisites: Docker Desktop (running), Python 3.11, Git. Commands below use PowerShell; there is no `tail` and no heredoc, so use `Select-Object -Last 50` and `notepad`.

### 1. Clone and configure

```powershell
git clone https://github.com/StormyStack/Thesis.git
cd Thesis
git checkout AI_Code_Works

copy .env.example .env
notepad .env        # fill in the passwords (ask SE); never commit this file
```

Passwords that contain `#` must be written as `%23` wherever they are used inside a URL or passed to the container as `DB_PASSWORD` / `REDIS_PASSWORD` (the service builds connection URLs from them).

### 2. Start PostgreSQL and Redis

```powershell
docker-compose up -d
Start-Sleep -Seconds 20
docker-compose ps         # both should be Up (healthy)
```

On a fresh volume, PostgreSQL runs `01_schema.sql` automatically. Deleting the volume (`docker volume rm thesis_pgdata`) wipes the curriculum; reload it with step 3.

### 3. Load the curriculum

Run from the host (not inside Docker). In `.env`, `DATABASE_HOST` must be `localhost` for this script.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python load_curriculum.py

docker exec eduarai_postgres psql -U appuser -d eduarai -c "SELECT COUNT(*) FROM document_chunks WHERE module_id = 'DNA_BIOLOGY_001';"
```

Expected count: 18 (or the current chunk count). The script is safe to re-run for the module row, but it inserts the chunks again each time, so clear the table first if you reload: `DELETE FROM document_chunks WHERE module_id = 'DNA_BIOLOGY_001';`

### 4. Build and run the AI service

```powershell
docker build -t eduarai-ai:latest .      # 15-40 minutes the first time; see Docker notes

docker rm -f eduarai_ai
docker run -d --name eduarai_ai -p 8001:8001 `
  -e DATABASE_HOST=eduarai_postgres -e DATABASE_PORT=5432 `
  -e POSTGRES_USER=appuser -e DB_PASSWORD=<url-encoded password> -e POSTGRES_DB=eduarai `
  -e REDIS_HOST=eduarai_redis -e REDIS_PORT=6379 -e REDIS_PASSWORD=<url-encoded password> `
  -e RAG_TIMEOUT=5.0 `
  --network thesis_default eduarai-ai:latest

Start-Sleep -Seconds 40       # the embedding model loads at startup (about 25-35 s)
```

Inside the Docker network, use the container names (`eduarai_postgres`, `eduarai_redis`). `localhost` inside a container means the container itself.

### 5. Verify

```powershell
curl http://localhost:8001/health
curl -X POST http://localhost:8001/api/chat -H "Content-Type: application/json" -d '{"question":"What is DNA?"}'
curl http://localhost:8001/api/cache-stats
docker logs eduarai_ai | Select-Object -Last 50
```

### Stop

```powershell
docker rm -f eduarai_ai
docker-compose down
```

## Configuration

All settings come from environment variables (`config_prod.py`). Secrets have no defaults.

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_HOST` / `DATABASE_PORT` | `eduarai_postgres` / `5432` | PostgreSQL location (`localhost` for scripts run on the host) |
| `POSTGRES_USER` / `POSTGRES_DB` | `appuser` / `eduarai` | Database login and name |
| `DB_PASSWORD` | required | Database password (URL-encode special characters) |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_TIMEOUT` | `10` / `20` / `30` | Connection pool |
| `REDIS_HOST` / `REDIS_PORT` | `eduarai_redis` / `6379` | Redis location (bare host name, no `redis://` prefix) |
| `REDIS_PASSWORD` | required | Redis password (URL-encode special characters) |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Embedding model |
| `RAG_THRESHOLD` | `0.40` | Minimum cosine similarity to count as on-topic |
| `RAG_TOP_K` | `3` | Chunks returned per query |
| `RAG_TIMEOUT` | `1.5` | Query encoding timeout in seconds. **Too tight on CPU; the running container sets `5.0`** |
| `BANDIT_EPSILON` | `0.15` | Exploration rate |
| `ETL_REFRESH_INTERVAL` / `ETL_SESSION_WINDOW` | `60` / `30` | ETL period (seconds) and active window (minutes) |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8001` | Bind settings used by the `python main_service.py` entry point |
| `MOCK_LLM` | `True` | Template answers instead of a language model |

## API reference

Base URL: `http://localhost:8001`. In production, clients call the Gateway instead.

### `GET /health`

```json
{
  "status": "healthy",
  "service": "eduarai-ai",
  "version": "1.0.0",
  "database": "connected",
  "cache": "disconnected",
  "rag_ready": true,
  "scheduler_running": false,
  "timestamp": "2026-10-04T10:00:00"
}
```

`status` reports that the process is up; check `database`, `cache` and `rag_ready` for the real state.

### `POST /api/chat`

Request:

| Field | Type | Required | Notes |
|---|---|---|---|
| `question` | string | yes | The student's question |
| `user_id` | string | no | Generated if absent |
| `session_id` | string | no | Generated if absent |
| `module_id` | string | no | Only used in the reply text today |

Response (measured, answer shortened):

```json
{
  "answer": "Based on the curriculum:\n\n[DNA_BIOLOGY_001] # DNA CURRICULUM ...",
  "is_on_topic": true,
  "max_similarity": 0.5666,
  "num_documents": 3,
  "latency_ms": 570.2,
  "decision_id": "42153e02-244a-44d0-b033-13dea1cda0df",
  "cached": false
}
```

Off-topic questions return `is_on_topic: false`, `num_documents: 0` and a polite refusal. (An off-topic question has not yet been tested against the corrected retrieval query; see the checklist in [Roadmap](#roadmap).) The bandit action is logged on the server and a `decision_id` is returned; the action itself is not in this response.

Errors return HTTP 500 with `{"detail": {"error": "...", "latency_ms": ...}}` (for example `Query encoding timeout`). A missing `question` returns HTTP 422 from Pydantic.

### `GET /api/cache-stats` and `POST /api/cache-flush`

`cache-stats` returns `hits`, `misses`, `errors`, `total`, `hit_rate` and `redis_status`. `cache-flush` clears the Redis database (testing only).

### `WS /ws/adapt/{session_id}` (prototype)

Send `{"question": "..."}`. The server runs retrieval, asks the bandit for an action using a **random** state vector, and replies with:

```json
{"answer": "...", "is_on_topic": true, "action": 2, "latency_ms": 120.5, "cached": false, "timestamp": "..."}
```

This does not yet follow the specification's frame (action token, `scene_name`, `target_object_id`, hint payload), does not read the learner state from Redis and does not update the bandit with a reward. It has not been tested end to end.

## How it works

### Retrieval and guardrail

1. The question is encoded to a 384-dimensional vector with `all-MiniLM-L6-v2`. Encoding runs in a worker thread under `asyncio.wait_for(RAG_TIMEOUT)` so the event loop is never blocked.
2. PostgreSQL ranks `document_chunks` by cosine distance and returns the top 3:

   ```sql
   SELECT chunk_id, module_id, content,
          1 - (embedding <=> '[0.01, -0.23, ...]'::vector) AS similarity
   FROM document_chunks
   ORDER BY similarity DESC LIMIT 3;
   ```

   `<=>` is pgvector's cosine distance, so `1 - distance` is the cosine similarity. The vector must be sent as a bracketed list string cast to `vector`. (An earlier version sent the raw bytes as hex, which made every query return zero documents.)
3. Chunks with similarity below `RAG_THRESHOLD` (0.40) are dropped. If none remain, the question is off-topic.
4. The remaining chunks are joined into a context string and returned as the answer (no language model yet).

The 0.40 threshold and top-3 come from the CTO specification. They have not yet been tuned on a labeled set.

### Curriculum loading

`load_curriculum.py` reads `expanded_dna_curriculum.txt` (8,740 characters), cuts it into fixed 500-character windows (18 chunks, no overlap), embeds them in one batch and inserts them. It first inserts the parent row into `modules`, which the foreign key requires. Limitations: windows cut mid-word, and the corpus contains a duplicated section (two of the three chunks returned in one live test had identical text).

### Cache design (Redis, cache first)

| Key pattern | Holds | TTL |
|---|---|---|
| `embedding:<text or md5>` | Query embedding | 1 hour |
| `docs:<module or all>:<hash>` | Retrieved documents | 1 hour |
| `context:<text or md5>` | Built context for a query | 30 minutes |
| `session:{id}:state` (spec) | 8-D learner vector written by the ETL | 3600 s |

If Redis is unreachable, every cache call returns nothing and the request goes to PostgreSQL. This was observed in practice: chat kept working while the Redis connection was failing.

### Contextual bandit

`bandit_service.py` implements an **epsilon-greedy** policy over 8 actions: with probability 0.15 it explores a random action; otherwise it picks the action with the highest mean reward (unvisited actions are tried first; ties are broken randomly). Rewards are clipped to [0, 1]. The 8-D state is validated (length must be 8) but is **not used in the score**, so today this is a multi-armed bandit baseline with a contextual interface. Statistics are kept in memory per worker process and reset on restart. The CTO specification describes a linear contextual policy (score = weights · state, with an incremental update); that is the planned upgrade.

Actions: `increase_difficulty`, `decrease_difficulty`, `maintain_difficulty`, `show_hint`, `hide_hint`, `suggest_quiz`, `suggest_ar_activity`, `switch_scene`.

Learner state (specification definition, computed by the ETL from the `events` table): correct-answer rate, hints per session, current difficulty, AR engagement rate, content-skip rate, time in session, session count, recent quiz score (all scaled to 0-1). Earlier prototypes used a different 8-D layout; the specification's definition is the canonical one.

### Scheduler / ETL (not active)

`scheduler_service.py` defines an APScheduler job (every 60 s) guarded by a Redis lock. As written, it refreshes existing `session:*:state` keys in Redis (for example decaying engagement); it does **not** yet build the state vector from the `events` table as the specification requires. It is disabled in `main_service.py`.

### Event logging (A.3) and ETL (A.4): not done

SE's schema already contains an `events` table (see below). The first draft of `event_service.py` was written without checking that schema and **will fail as is**: `event_id` has no default, `scene_name` and `client_timestamp` are `NOT NULL`, `user_id` and `session_id` are UUID foreign keys, and the user and session rows must exist first. Confirm with SE who writes events (the specification has the Gateway log them), then either adapt the draft or read the table from the ETL.

## Database schema

Owned by SE (`01_schema.sql`). Summary of the tables this service uses:

| Table | Purpose | Key columns |
|---|---|---|
| `users` | Learner identity | `user_id` (UUID), `username`, `detail_level`, `language` |
| `sessions` | One learning session | `session_id`, `user_id` (FK), `started_at`, `ended_at` |
| `events` | Learner telemetry | `event_id`, `user_id` (FK), `session_id` (FK), `scene_name` (NOT NULL), `event_type`, `correct`, `time_spent_ms`, `payload` JSONB, client/server timestamps |
| `modules` | Curriculum modules | `module_id`, `name`, `scene_name`, `cdn_bundle_url` (NOT NULL), `difficulty` |
| `document_chunks` | RAG knowledge store | `chunk_id`, `module_id` (FK), `content`, `embedding vector(384)`, `created_at` |

`document_chunks` has an IVFFlat index (`vector_cosine_ops`, 100 lists). With 18 rows an exact scan is instant, so the index matters only at larger scale; it is best built after the data is loaded.

## Docker notes

- **Containers:** `eduarai_postgres` (pgvector/pgvector:pg16), `eduarai_redis` (redis:7-alpine, password required), `eduarai_ai` (`eduarai-ai:latest`). All share the `thesis_default` network. The AI container is started with `docker run`; there is no compose override file in use.
- **Image:** multi-stage build on `python:3.11-slim`; the builder installs dependencies, the final stage copies them plus each service file, and starts uvicorn with 4 workers on port 8001. Every Python file must have its own `COPY` line, otherwise the container crashes with `ModuleNotFoundError` (this happened with `cache_service.py`). Size on the development machine: about 9.7 GB on disk (3.3 GB content), because PyTorch is pulled in by sentence-transformers.
- **Build time:** a full `--no-cache` build took roughly 13 to 37 minutes on the development laptop; the dependency install dominates.
- **Four workers** means four copies of the embedding model in memory and four separate bandit states.
- **Disk:** Docker Desktop's data disk and build cache can grow very large. Prefer environment variables for settings. For a single changed file, `docker cp main_service.py eduarai_ai:/app/` followed by `docker restart eduarai_ai` avoids a rebuild. `docker builder prune` reclaims build cache.
- **Networking:** scripts run on Windows use `localhost` (ports are published). `host.docker.internal` did not resolve from Windows Python.

## Verified results

Observed on the development machine (Windows 11, CPU only):

| Check | Result |
|---|---|
| PostgreSQL and Redis containers | Up and healthy |
| `SELECT COUNT(*) FROM document_chunks` (module `DNA_BIOLOGY_001`) | 18 |
| `GET /health` | HTTP 200, database connected, `rag_ready: true` (cache disconnected) |
| `POST /api/chat` with "What is DNA?" | `is_on_topic: true`, `max_similarity: 0.5666`, `num_documents: 3`, 570 ms, `cached: false` |
| Embedding model load at container start | about 25-35 seconds |

Not yet verified: off-topic rejection after the retrieval fix, a cache hit, WebSocket end to end, event insert and ETL, memory use, the specification's accuracy targets (top-3 hit rate, guardrail F1, bandit versus random), and the automated test suite.

## Known issues

| # | Issue | Fix |
|---|---|---|
| 1 | **Redis never connects.** `cache_service.py` ends with `CacheService(__name__)`, so the Redis URL is the string `"cache_service"`. Log: `Redis URL must specify one of the following schemes`. | `import config_prod as config` and `cache_service = CacheService(config.REDIS_URL)`. Keep `REDIS_HOST=eduarai_redis` (bare name). |
| 2 | A cache hit returns the stored dict with `cached` saved as `False`. | In `build_context`, on a hit set `cached["cached"] = True` before returning. |
| 3 | The `docs` cache key uses Python's `hash()`, which differs between worker processes, so hits are lost. | Use `hashlib.sha1(query_embedding.tobytes()).hexdigest()`. |
| 4 | Startup logs "Redis cache connected" even when `connect()` failed. | Log based on `cache_service.client is not None`. |
| 5 | WebSocket handler uses a random state, does not update the bandit and does not match the spec's frame. | Rework after the ETL provides state in Redis. |
| 6 | Bandit ignores the state in its score; stats are per worker and in memory. | Linear contextual policy per the spec; persist weights. |
| 7 | Corpus has a duplicated section; fixed 500-character windows cut mid-word. | Deduplicate, split on sentences with overlap, reload. |
| 8 | Retrieval SQL is built with an f-string. | Use bound parameters. |
| 9 | CORS is open (`*`) and the service has no authentication. | Restrict origins; rely on the Gateway for auth. |
| 10 | `event_service.py` does not match SE's `events` schema. | See [Event logging](#event-logging-a3-and-etl-a4-not-done). |
| 11 | `.venv` was committed in an earlier push. | Ignore and untrack it (see [Git workflow](#git-workflow)). |
| 12 | `scheduler_service.py` ETL does not build state from events; it is disabled. | Implement per the spec, then re-enable. |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `curl: Empty reply from server` | Container still loading the model, or workers crashed | Wait about 40 s; `docker logs eduarai_ai` |
| `ModuleNotFoundError` in logs | A `.py` file has no `COPY` line in the Dockerfile | Add the line and rebuild, or `docker cp` the file and restart |
| `Connection refused` to Postgres/Redis | Backing containers not running, or `localhost` used inside the container | `docker-compose up -d`; use container names and `--network thesis_default` |
| `num_documents: 0` with data present | Embedding passed to pgvector in the wrong format | Use the bracketed-list cast shown in [How it works](#retrieval-and-guardrail) |
| No documents at all | Volume was deleted, so the schema re-ran on an empty database | `python load_curriculum.py` |
| `Query encoding timeout` | `RAG_TIMEOUT` too tight on CPU | Set `-e RAG_TIMEOUT=5.0` |
| `'coroutine' object does not support the asynchronous context manager protocol` | `get_session()` returned a coroutine | Use the `@asynccontextmanager` version in `database_service.py` |
| Password or URL errors with `#` | `#` starts a URL fragment | Write it as `%23` in URLs and in the container's password variables |
| `pip install -r requirements.txt` fails with `UnicodeDecodeError` | Non-ASCII characters in `requirements.txt` on Windows | Keep the file ASCII only |
| Docker commands fail | Docker Desktop not running | Start it, wait 60 s, run `docker ps` |
| Image pull fails (registry DNS error) | Docker Hub unreachable | Retry later; keep images pulled before a demo |

## Roadmap

Do these in order; each produces evidence you can show.

1. Fix the Redis connection and the cache flag/key (issues 1-4); confirm `/api/cache-stats` shows `redis_status: connected`.
2. Off-topic test: ask an unrelated question (for example the capital of France) and confirm `is_on_topic: false`.
3. Cache test: ask the same question twice; expect `cached: true` and lower latency on the second call. Record real latencies (median of 10 requests for miss and hit).
4. Measure memory with `docker stats --no-stream` (the specification budget is 1.8 GB).
5. Remove the duplicated chunk, reload the curriculum, and confirm the new chunk count.
6. Event logging and ETL: align with SE's `events` schema, seed a user, session and events, build the 8-D state from events into `session:{id}:state`, then enable the scheduler.
7. Rework the WebSocket handler to the spec's frame; read state from Redis; update the bandit with rewards.
8. Linear contextual bandit and a simulation against a random baseline (specification target: at least 30 percent higher cumulative reward).
9. Evaluation: 50 annotated questions for top-3 hit rate, 100 prompts (biology and adversarial) for guardrail precision, recall and F1; tune the threshold.
10. Language-model answer generation (Phi-3-Mini or Mistral-7B class) over the retrieved context; replace the template.
11. Re-run `test_integration.py`, add golden Q&A regression cases, and stress test at low concurrency.

## Git workflow

- Work on `AI_Code_Works`. SE's `data-layer` branch (compose file and schema) is locked: do not modify it.
- Never commit `.env`. Commit `.env.example` with placeholders only. Do not paste real or realistic-looking passwords into any documentation.
- `.venv` and `__pycache__` must not be tracked:

  ```powershell
  Add-Content .gitignore ".venv/`nvenv/`n.env`n__pycache__/"
  git rm -r --cached .venv venv __pycache__ .env
  git status          # confirm only intended files are staged
  git commit -m "Remove virtual environment and secrets from tracking"
  git push origin AI_Code_Works
  ```

  (`git rm --cached` reports an error for any path that is not tracked; remove that path from the command and run it again.) Afterwards run `git ls-files | findstr .env`. If `.env` was ever committed, treat its passwords as exposed and rotate them.

## Team and references

| Role | Owns |
|---|---|
| AI Engineer (Shabab) | This service: RAG, guardrail, bandit, cache layer, ETL design, curriculum ingestion, Docker image |
| System Engineer | `docker-compose.yml`, PostgreSQL and Redis, `01_schema.sql`, Gateway, event logging |
| Unity developer | AR scenes and execution of the 8 action tokens |
| React Native developer | Mobile app, chat UI, bridge to Unity |

References: the CTO specification for the AI Engineer role (RAG parameters, bandit actions, 8-D state, WebSocket protocol, test plan) and the thesis roadmap (A.1 model, A.2 dataset, A.3 data collection, A.4 ETL). Curriculum sources named in the corpus header: NCBI, OpenStax Biology, Khan Academy.
