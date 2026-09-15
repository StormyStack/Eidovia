# WEEK 1: FOUNDATION SETUP - Complete Guide

## Overview
This week we build:
- ✅ PostgreSQL + pgvector database
- ✅ DNA curriculum ingestion pipeline
- ✅ RAG retrieval system
- ✅ FastAPI microservice skeleton
- ✅ Mock LLM responses (real LLM in Week 2)
- ✅ Smoke test suite

**Timeline: 3-4 hours total**

---

## Prerequisites

You should have:
- [ ] Windows 11
- [ ] Docker Desktop installed and running
- [ ] Python 3.11+ installed
- [ ] VS Code installed
- [ ] ~10 GB free disk space

Check Python version:
```bash
python --version
```

Should output: `Python 3.11.X` or higher

---

## Step-by-Step Setup

### STEP 1: Copy All Files (10 minutes)

Navigate to your project folder:
```bash
cd E:\thesis-ai-service
```

You should have these files in `E:\thesis-ai-service\`:
```
├── docker-compose.yml
├── requirements.txt
├── config.py
├── main.py
├── rag.py
├── database.py
├── Dockerfile
├── .env.example
├── dna_curriculum.txt
├── test_smoke.py
├── ingest_curriculum.py
└── .gitignore (optional)
```

All files have been created in `/home/claude/` and you need to copy them to `E:\thesis-ai-service\`.

**Copy-paste each file content into VS Code and save.**

---

### STEP 2: Install Python Dependencies (5 minutes)

Open PowerShell in `E:\thesis-ai-service`:

```bash
pip install -r requirements.txt
```

Wait for installation to complete. You should see:
```
Successfully installed FastAPI uvicorn pydantic asyncpg redis sentence-transformers numpy pandas pytest...
```

---

### STEP 3: Start Docker Containers (10 minutes)

Make sure **Docker Desktop is running** (check system tray).

In PowerShell (in `E:\thesis-ai-service`):

```bash
docker-compose up -d
```

Wait 30 seconds for containers to start.

Verify they're running:
```bash
docker-compose ps
```

You should see:
```
CONTAINER ID   IMAGE                 STATUS
xxx            pgvector/pgvector:pg16 Up 2 seconds
xxx            redis:7-alpine        Up 2 seconds
```

---

### STEP 4: Verify Database Connection (5 minutes)

Test PostgreSQL is accessible:

```bash
python -c "import asyncpg; import asyncio; asyncio.run(asyncpg.connect('postgresql://thesis_user:thesis_password@localhost:5432/thesis_db'))" && echo "✅ DB OK"
```

Should output: `✅ DB OK`

---

### STEP 5: Initialize Database Schema (5 minutes)

Run the database setup:

```bash
python -c "import asyncio; from database import init_db; asyncio.run(init_db())"
```

Should output:
```
pgvector extension created/verified
document_chunks table created/verified
events table created/verified
sessions table created/verified
ai_decision_log table created/verified
✅ Database initialization complete
```

---

### STEP 6: Ingest DNA Curriculum (10 minutes)

This loads the curriculum into PostgreSQL with embeddings:

```bash
python ingest_curriculum.py
```

**Note**: First run will take 5-10 minutes as it:
1. Loads sentence-transformers model (~200 MB download)
2. Chunks the curriculum
3. Generates embeddings
4. Stores in PostgreSQL

You should see:
```
📖 Starting curriculum ingestion...
✅ Curriculum loaded (45000 chars)
✅ Parsed 5 sections
  Topic 'DNA STRUCTURE': 8 chunks
  Topic 'DNA REPLICATION': 7 chunks
  ... more sections ...
✅ Successfully inserted 42 chunks into database
📊 Final count: 42 chunks in document_chunks table
```

---

### STEP 7: Start the FastAPI Service (5 minutes)

In a NEW PowerShell window (keep Docker running):

```bash
python main.py
```

Should output:
```
🚀 Starting AI Service...
✅ Database initialized
✅ Database pool created
✅ RAG retriever initialized
INFO:     Uvicorn running on http://127.0.0.1:8001
```

**Keep this terminal open** (it's your API server).

---

### STEP 8: Test the API (5 minutes)

Open a THIRD PowerShell window and test:

```bash
# Health check
curl http://localhost:8001/health

# Chat endpoint (on-topic)
curl -X POST http://localhost:8001/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is DNA replication?"}'

# Chat endpoint (off-topic)
curl -X POST http://localhost:8001/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is the capital of France?"}'
```

Expected responses:
- **Health**: `{"status":"healthy","service":"ai-service",...}`
- **DNA Question**: `{"answer":"Based on our curriculum...","is_on_topic":true,...}`
- **Off-topic**: `{"answer":"This question is outside the scope...","is_on_topic":false,...}`

---

### STEP 9: Run Smoke Tests (10 minutes)

In the THIRD PowerShell:

```bash
pytest test_smoke.py -v
```

Should see:
```
test_smoke.py::test_database_connection PASSED
test_smoke.py::test_document_chunks_table PASSED
test_smoke.py::test_embedding_dimension PASSED
test_smoke.py::test_rag_retrieval PASSED
test_smoke.py::test_health_endpoint PASSED
test_smoke.py::test_chat_endpoint_off_topic PASSED
test_smoke.py::test_chat_endpoint_on_topic PASSED
test_smoke.py::test_api_response_schema PASSED

===== 8 passed in 3.45s =====
```

---

## Week 1 Success Checklist

- [ ] Docker containers running (PostgreSQL + Redis)
- [ ] Database schema created with pgvector
- [ ] DNA curriculum loaded (42 chunks with embeddings)
- [ ] FastAPI server running on `http://127.0.0.1:8001`
- [ ] `/health` endpoint responds with `healthy` status
- [ ] `/chat` endpoint accepts on-topic questions
- [ ] `/chat` endpoint rejects off-topic questions
- [ ] All 8 smoke tests pass
- [ ] Latency: < 500ms per request

---

## Troubleshooting

### Docker won't start
```bash
# Check Docker is running
docker ps

# If not, start Docker Desktop from Start menu
# Then retry: docker-compose up -d
```

### Database connection error
```bash
# Check PostgreSQL container
docker logs thesis-postgres

# Verify connection manually
psql -h localhost -U thesis_user -d thesis_db
# Password: thesis_password
```

### Embedding generation slow
- First run downloads ~200 MB sentence-transformers model
- Subsequent runs are cached and faster
- Be patient (5-10 minutes for ingestion is normal)

### Port already in use
```bash
# Check what's using port 8001
netstat -ano | findstr :8001

# Kill process if needed (replace PID)
taskkill /PID <PID> /F
```

---

## What's Ready for Week 2

- ✅ **Infrastructure**: Database, API, Docker setup
- ✅ **RAG Pipeline**: Retrieval, topic checking, context building
- ✅ **Mock Responses**: Working endpoints for testing
- ✅ **Test Suite**: Smoke tests for all components

**Not Yet (Week 2)**:
- ❌ Real LLM (Phi-3-Mini via HuggingFace)
- ❌ WebSocket real-time adaptation
- ❌ RL contextual bandit
- ❌ User state profiling

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Container definitions |
| `config.py` | Configuration (DB, API, model settings) |
| `database.py` | PostgreSQL + pgvector setup |
| `rag.py` | RAG retrieval logic |
| `main.py` | FastAPI application |
| `ingest_curriculum.py` | Curriculum loader |
| `dna_curriculum.txt` | Biology content (5 sections, 42 chunks) |
| `test_smoke.py` | Automated tests |

---

## Next: Week 2 Preview

In Week 2, we'll:
1. Integrate real Phi-3-Mini LLM (HuggingFace/Ollama)
2. Build WebSocket `/ws/adapt` endpoint
3. Implement contextual bandit RL
4. Real-time decision making (~150ms latency)

---

**Week 1 Complete! 🎉**

Message when all tests pass:
> "Week 1 complete. All smoke tests passing. Ready for Week 2."
