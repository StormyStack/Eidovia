# WEEK 2: RAG PIPELINE + CONTEXT-AWARE CHAT

## Overview

This week we build:
- ✅ Real DNA curriculum ingestion (chunking + embeddings)
- ✅ RAG retrieval system (cosine similarity search)
- ✅ Context-aware `/chat` endpoint (uses curriculum as sources)
- ✅ Topic detection (on-topic/off-topic classification)
- ✅ Mock LLM with context enhancement
- ✅ No database needed (JSON file storage)
- ✅ No network required (all local)

**Timeline: 1-2 hours total**

---

## Architecture

```
dna_curriculum.txt
    ↓
[ingest_curriculum_week2.py]
    ↓
Sentence-Transformers Embeddings (local)
    ↓
embeddings.json (chunks + vectors)
    ↓
RAGRetriever (cosine similarity)
    ↓
/chat endpoint (context-aware)
    ↓
Mock LLM Response
```

**Everything runs locally. No external APIs. No database server.**

---

## Step-by-Step Setup

### STEP 1: Update Your Project

Replace these files in `E:\thesis-ai-service\`:

1. Rename old files:
   ```bash
   mv main.py main_week1.py
   mv config.py config_week1.py
   ```

2. Copy new Week 2 files from outputs:
   - `main_week2.py` → `main.py`
   - `config_week2.py` → `config.py`
   - `rag_week2.py` → `rag.py`
   - `ingest_curriculum_week2.py` → `ingest_curriculum.py`

3. Verify `dna_curriculum.txt` exists in project root

---

### STEP 2: Create Data Directory

In PowerShell:

```bash
cd E:\thesis-ai-service
mkdir data
```

This is where embeddings will be saved.

---

### STEP 3: Activate venv

```bash
.\venv\Scripts\Activate.ps1
```

Should show `(venv)` prefix.

---

### STEP 4: Ingest Curriculum (5-10 minutes)

This loads DNA curriculum, chunks it, and generates embeddings:

```bash
python ingest_curriculum.py
```

**Expected output:**
```
==============================
📖 WEEK 2: DNA CURRICULUM INGESTION
==============================

[1/4] Loading curriculum...
✅ Loaded (45000+ characters)

[2/4] Parsing and chunking...
✅ Parsed 5 sections
  • DNA Structure: 8 chunks
  • DNA Replication: 7 chunks
  ... more sections ...
✅ Total: 42 chunks

[3/4] Generating embeddings...
  Processing 10/42...
  Processing 20/42...
  Processing 30/42...
  Processing 40/42...
✅ Generated 42 embeddings

[4/4] Saving to data/embeddings.json...
✅ Saved to data/embeddings.json (2.5 MB)

==============================
✅ INGESTION COMPLETE
==============================
Chunks: 42
Embeddings: 42
File: data/embeddings.json
Ready for RAG retrieval!
```

**First run takes 3-5 minutes** (downloads embedding model ~200MB, cached after).

---

### STEP 5: Verify Embeddings File

```bash
dir data\
```

Should show:
```
embeddings.json  (2-3 MB)
```

---

### STEP 6: Start FastAPI Server

In the SAME PowerShell:

```bash
python main.py
```

**Expected output:**
```
============================================================
🚀 WEEK 2: RAG + CONTEXT-AWARE AI SERVICE STARTED
============================================================
Chunks loaded: 42
Embedding model: all-MiniLM-L6-v2
API: http://127.0.0.1:8001
============================================================

INFO:     Started server process [12345]
INFO:     Uvicorn running on http://127.0.0.1:8001
```

**Keep this terminal open.**

---

### STEP 7: Test RAG Endpoints

Open a NEW PowerShell and test:

#### Health Check
```bash
curl http://localhost:8001/health
```

Expected:
```json
{
  "status": "healthy",
  "service": "ai-service",
  "version": "0.2.0",
  "rag_ready": true,
  "chunks_loaded": 42,
  "embedding_model": "all-MiniLM-L6-v2"
}
```

---

#### On-Topic DNA Question
```bash
curl -X POST http://localhost:8001/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is the structure of DNA?"}'
```

Expected:
```json
{
  "answer": "DNA (deoxyribonucleic acid) is a double helix...\n\n**Sources from curriculum:**\n\n1. DNA Structure (Relevance: 95%)",
  "is_on_topic": true,
  "sources": 3,
  "context_used": true,
  "latency_ms": 245.5,
  "mock": true
}
```

---

#### Off-Topic Question
```bash
curl -X POST http://localhost:8001/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is the capital of France?"}'
```

Expected:
```json
{
  "answer": "This question is outside the scope of our DNA biology module...",
  "is_on_topic": false,
  "sources": 0,
  "context_used": false,
  "latency_ms": 125.3,
  "mock": true
}
```

---

#### Another DNA Topic
```bash
curl -X POST http://localhost:8001/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"Explain DNA replication process"}'
```

---

## Week 2 Success Checklist

- [ ] Files replaced (main.py, config.py, rag.py, ingest_curriculum.py)
- [ ] Data directory created
- [ ] venv activated
- [ ] Curriculum ingested (embeddings.json created, 42 chunks)
- [ ] FastAPI server running on 127.0.0.1:8001
- [ ] `/health` endpoint returns rag_ready: true
- [ ] `/chat` accepts on-topic DNA questions
- [ ] `/chat` rejects off-topic questions
- [ ] Latency: < 500ms per request
- [ ] Context sources displayed in answers

---

## What's Working Now

✅ **Real embeddings** (sentence-transformers)
✅ **RAG retrieval** (cosine similarity search)
✅ **Topic detection** (embedding-based guardrail)
✅ **Context-aware responses** (curriculum sources cited)
✅ **Mock LLM** (foundation for real LLM integration)
✅ **No database** (JSON file storage)
✅ **No network required** (all local)

---

## What's Next (Week 3)

- ❌ WebSocket `/ws/adapt` endpoint
- ❌ Real Phi-3-Mini LLM (when internet/GPU available)
- ❌ Contextual bandit for personalization
- ❌ Real-time user state tracking

---

## Troubleshooting

### "Embeddings file not found"

```bash
python ingest_curriculum.py
```

Run ingestion first.

---

### "No chunks available"

Same as above — embeddings not ingested yet.

---

### High latency (>2s)

First request is slow (model loading). Subsequent requests are fast (<300ms).

---

### "ModuleNotFoundError: No module named 'sentence_transformers'"

```bash
pip install sentence-transformers
```

---

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | FastAPI app with RAG |
| `config.py` | Settings (RAG threshold, chunk size) |
| `rag.py` | RAG retriever logic |
| `ingest_curriculum.py` | Curriculum loader |
| `data/embeddings.json` | Embedded chunks (generated) |
| `dna_curriculum.txt` | Curriculum source |

---

## Next: Week 3 Preview

In Week 3, we'll add:
1. WebSocket endpoint for real-time adaptation
2. Real Phi-3-Mini (when Huggingface/GPU available)
3. Contextual bandit (RL-based personalization)
4. User state profiling

---

**Week 2 Complete! 🎉**

Message when all tests pass:
> "Week 2 complete. RAG pipeline working. 42 chunks loaded. Ready for Week 3."
