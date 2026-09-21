# EduAR-AI Service

Adaptive learning microservice with RAG + contextual bandit for personalized biology education.

## Architecture

```
┌─────────────────────────────────────────┐
│      FastAPI Application                │
│  /api/chat (REST)                       │
│  /ws/adapt/{session_id} (WebSocket)     │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┼──────────┐
    ↓          ↓          ↓
┌────────┐ ┌────────┐ ┌──────────┐
│ RAG    │ │ Bandit │ │Scheduler │
│Service │ │Service │ │ (ETL)    │
└────────┘ └────────┘ └──────────┘
    ↓          ↓          ↓
    └──────────┬──────────┘
               ↓
    ┌──────────────────────┐
    │  PostgreSQL + Redis  │
    │  (Shared infra)      │
    └──────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker Compose (optional, for full stack)
- PostgreSQL 16 + pgvector (provided by SE)
- Redis 7 Alpine (provided by SE)

### Local Development

#### 1. Setup Environment

```bash
# Create virtual environment
python -m venv venv

# Activate
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\Activate.ps1  # Windows

# Install dependencies
pip install -r requirements.txt
```

#### 2. Configure .env

```bash
# Copy example
cp .env.example .env

# Edit with actual values
# DATABASE_URL=postgresql+asyncpg://appuser:PASSWORD@localhost:5432/eduarai
# REDIS_URL=redis://:PASSWORD@localhost:6379/0
```

#### 3. Run Service

```bash
# Local development (reload on changes)
python -m uvicorn main_service:app --reload --host 127.0.0.1 --port 8001

# Production (4 workers)
python main_service.py
```

### Docker Deployment

#### Build Image

```bash
# Build AI service image
docker build -t eduarai-ai:latest .
```

#### Run with Docker Compose

```bash
# From data-layer branch (SE's infrastructure)
docker-compose up

# Includes: PostgreSQL, Redis, AI Service
```

## API Reference

### Health Check

```bash
GET /health

Response:
{
  "status": "healthy",
  "service": "eduarai-ai",
  "database": "connected",
  "rag_ready": true,
  "scheduler_running": true
}
```

### Chat Endpoint (REST)

```bash
POST /api/chat

Request:
{
  "question": "What is DNA?",
  "user_id": "user-123",
  "session_id": "session-456",
  "module_id": "dna-01"
}

Response:
{
  "answer": "Based on our curriculum...",
  "is_on_topic": true,
  "max_similarity": 0.78,
  "num_documents": 3,
  "latency_ms": 145.2,
  "decision_id": "dec-789"
}
```

### Adaptation Endpoint (WebSocket)

```javascript
// Connect to WebSocket
const ws = new WebSocket("ws://localhost:8001/ws/adapt/session-123");

// Send interaction event
ws.send(JSON.stringify({
  "question": "What causes mutations?",
  "correct": true,
  "response_time_ms": 2500,
  "difficulty": 2
}));

// Receive adaptation
ws.onmessage = (event) => {
  const response = JSON.parse(event.data);
  console.log(response);
  // {
  //   "action_id": 2,
  //   "action_name": "maintain_difficulty",
  //   "reward": 1.0,
  //   "timestamp": "2026-09-18T10:30:00"
  // }
};
```

## Configuration

### RAG Settings

```
RAG_THRESHOLD=0.40          # Cosine similarity threshold
RAG_TOP_K=3                 # Documents to retrieve
RAG_TIMEOUT=1.5             # Retrieval timeout (seconds)
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### Bandit Settings

```
BANDIT_EPSILON=0.15        # Exploration rate
BANDIT_STATE_DIM=8         # State vector dimension
```

### ETL Scheduler

```
ETL_REFRESH_INTERVAL=60    # Refresh every 60 seconds
ETL_SESSION_WINDOW=30      # Active session window (minutes)
```

## State Vector (8D)

Used by contextual bandit for decision-making:

```
[0] Correctness        → 1.0 if correct, 0.0 if incorrect
[1] Response Time      → normalized [0, 1]
[2] Difficulty Level   → 1/3 to 1 (easy to hard)
[3] Topic Match        → similarity to known topics [0, 1]
[4] Engagement         → decay over time [0, 1]
[5] Question Count     → normalized question frequency
[6] Error Rate         → 0.0 if correct, 1.0 if incorrect
[7] Time Spent         → normalized session duration
```

## Bandit Actions (8)

Recommended adaptations:

```
0: increase_difficulty    → More challenging content
1: decrease_difficulty    → Easier review material
2: maintain_difficulty    → Continue current level
3: show_hint              → Display hint for current question
4: hide_hint              → Hide hints (challenge mode)
5: suggest_quiz           → Recommend quiz practice
6: suggest_ar_activity    → Suggest AR simulation
7: switch_scene           → Switch to different AR scene
```

## Monitoring & Logging

### Log Levels

```bash
# Development
DEBUG=True

# Production
DEBUG=False
```

### Sample Logs

```
2026-09-18 10:30:15 | ai-service-postgres | INFO | Processing: 'What is DNA?...'
2026-09-18 10:30:15 | rag_service | INFO | Retrieved 3/3 documents
2026-09-18 10:30:15 | bandit_service | DEBUG | Exploitation: selected action 2
2026-09-18 10:30:15 | main_service | INFO | Chat response: on_topic=True, similarity=0.782, latency=145.2ms
```

## Performance Targets

- **Chat Latency:** <500ms (RAG + Bandit decision)
- **WebSocket Latency:** <150ms (Adaptation response)
- **RAG Retrieval:** <45ms (pgvector ivfflat index)
- **Bandit Decision:** <5ms (numpy operations)

## Testing

### Unit Tests

```bash
pytest tests/ -v
```

### Integration Tests

```bash
pytest tests/integration/ -v
```

### Load Testing

```bash
# Using Apache Bench
ab -n 1000 -c 10 http://localhost:8001/health

# WebSocket test
python tests/ws_load_test.py
```

## Troubleshooting

### Database Connection Failed

```
❌ Database connection failed: could not connect to server
```

**Solution:**
- Check PostgreSQL is running: `docker-compose up eduarai_postgres`
- Verify credentials in .env
- Check DATABASE_URL format: `postgresql+asyncpg://user:pass@host:port/db`

### RAG Model Not Loading

```
❌ Failed to load embedding model
```

**Solution:**
- Ensure sentence-transformers installed: `pip install sentence-transformers`
- Check internet connection (downloads model on first run)
- Verify EMBEDDING_MODEL config is valid

### Redis Connection Error

```
❌ Redis connection failed
```

**Solution:**
- Check Redis is running: `docker-compose up eduarai_redis`
- Verify REDIS_URL format: `redis://:password@host:port/0`
- Test connection: `redis-cli ping`

## Development Workflow

### Add New Feature

1. Create feature branch from `data-layer`
2. Implement in corresponding service module
3. Add tests in `tests/`
4. Update configuration if needed
5. Submit PR with tests passing

### Deployment

```bash
# Build and tag
docker build -t eduarai-ai:v1.0 .

# Push to registry
docker push registry.example.com/eduarai-ai:v1.0

# Deploy via Docker Compose
docker-compose up -d
```

## Files

- `config_prod.py` - Configuration and environment variables
- `database_service.py` - Async PostgreSQL connections
- `rag_service.py` - Document retrieval with guardrail
- `bandit_service.py` - ε-greedy contextual bandit
- `scheduler_service.py` - Background ETL tasks
- `main_service.py` - FastAPI application
- `requirements.txt` - Python dependencies
- `Dockerfile` - Container image definition

## Integration with SE Infrastructure

This service expects:

### PostgreSQL (SE provides)
- Host: `eduarai_postgres`
- Port: `5432`
- Database: `eduarai`
- Tables: `users`, `sessions`, `events`, `modules`, `document_chunks`
- Extensions: `pgvector`

### Redis (SE provides)
- Host: `eduarai_redis`
- Port: `6379`
- Password: `$REDIS_PASSWORD`

### Environment (.env from SE)
- `POSTGRES_USER` → `appuser`
- `DB_PASSWORD` → strong password
- `REDIS_PASSWORD` → strong password

## Support

For issues or questions, contact the AI Engineer or refer to the CTO's AIE Specification Document.

---

**Status:** Production Ready  
**Last Updated:** 2026-09-18  
**Version:** 1.0.0
