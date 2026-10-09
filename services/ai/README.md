# Eidovia — AI Service

RAG-based biology Q&A. Runs on port `8001`.

## Start

```powershell
# From repo root:
docker compose up -d
```

## Load Curriculum (first time only)

```powershell
docker exec -it eidovia_ai python -m scripts.load_curriculum
```

## Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/api/chat` | POST | Biology Q&A |
| `/api/cache-stats` | GET | Redis hit/miss |
| `/api/cache-flush` | POST | Clear cache |
| `/ws/adapt/{session_id}` | WS | Adaptive tutoring |
