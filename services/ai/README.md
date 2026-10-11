# Eidovia — AI Service

Adaptive biology tutoring service featuring HOE (Hierarchy of Expertise) depth-capped RAG and local LLM generation powered by **Ollama (Phi-4 mini)**. Runs on port `8001`.

---

## Architecture

- **LLM Runtime**: **Ollama** running in Docker (`eidovia_ollama` on port `11434`), serving Microsoft Phi-4 mini with GPU acceleration.
- **RAG Engine**: Section-aware curriculum retrieval with depth capping (`hoe_level` 1–4).
- **Embedder**: `all-MiniLM-L6-v2` via sentence-transformers or Ollama (`all-minilm`).
- **Vector DB**: PostgreSQL 16 with `pgvector` (`eidovia_postgres` on port `6543`).
- **Cache**: Redis 7 (`eidovia_redis` on port `6379`).

---

## Running

1. **Ensure Docker containers are running (from repo root):**
   ```powershell
   docker compose up -d
   ```
   *(Starts `eidovia_postgres`, `eidovia_redis`, and `eidovia_ollama`)*

2. **Load curriculum chunks (first time or when updating curriculum):**
   ```powershell
   cd services\ai
   python -m scripts.load_curriculum
   ```

3. **Start AI service:**
   ```powershell
   cd services\ai
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
   ```

4. **Run HOE evaluation benchmark:**
   ```powershell
   cd services\ai
   python -m scripts.eval_hoe
   ```

---

## Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check (`rag_ready`, `embed_backend`, `mock_llm`) |
| `/api/chat` | POST | Biology Q&A with optional `hoe_level` depth cap (1–4) |
| `/api/cache-stats` | GET | Redis cache hit/miss statistics |
| `/api/cache-flush` | POST | Clear Redis cache |
| `/ws/adapt/{session_id}` | WS | Adaptive WebSocket tutoring |

### Chat Request Example

```json
POST /api/chat
Content-Type: application/json

{
  "question": "What enzyme builds new DNA strands?",
  "hoe_level": 4
}
```
