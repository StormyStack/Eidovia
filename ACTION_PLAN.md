# 🎯 Deployment Action Plan

Step-by-step checklist to get everything running.

---

## ✅ Phase 1: Preparation (5 mins)

### 1.1 Verify Docker Desktop
```bash
# Windows PowerShell
docker --version
docker-compose --version

# Expected output:
# Docker version 20.10+
# docker-compose version 2.0+
```

**Status:** ☐ Docker installed and working

### 1.2 Get Credentials from SE
Ask SE for:
- ✅ `DB_PASSWORD` (PostgreSQL admin password)
- ✅ `REDIS_PASSWORD` (Redis auth password)

**Status:** ☐ Credentials received and saved

---

## ✅ Phase 2: File Setup (2 mins)

### 2.1 Copy All Files to E:\Thesis

```bash
# From /mnt/user-data/outputs/

# Core services
copy config_prod.py E:\Thesis\
copy main_service.py E:\Thesis\
copy database_service.py E:\Thesis\
copy rag_service.py E:\Thesis\
copy bandit_service.py E:\Thesis\
copy scheduler_service.py E:\Thesis\

# Deployment
copy Dockerfile E:\Thesis\
copy requirements.txt E:\Thesis\
copy .dockerignore E:\Thesis\
copy docker-compose.override.yml E:\Thesis\

# Configuration
copy .env.example E:\Thesis\

# Scripts
copy startup.ps1 E:\Thesis\

# Documentation (optional but recommended)
copy DOCKER_SETUP.md E:\Thesis\
copy QUICK_REFERENCE.md E:\Thesis\
copy GIT_WORKFLOW.md E:\Thesis\
copy FINAL_SUMMARY.md E:\Thesis\
```

**Status:** ☐ All files copied

### 2.2 Verify SE's Files
```bash
cd E:\Thesis

# Should have from SE:
ls docker-compose.yml
ls 01_schema.sql

# Expected: Both files exist
```

**Status:** ☐ SE's files present

---

## ✅ Phase 3: Configuration (1 min)

### 3.1 Create .env File
```bash
cd E:\Thesis

# Copy template
copy .env.example .env

# Edit with your password
notepad .env
```

**Replace these placeholders:**
```
DB_PASSWORD=changeme_strong_password_from_SE
    ↓
DB_PASSWORD=<actual_password_from_SE>

REDIS_PASSWORD=changeme_strong_password_from_SE
    ↓
REDIS_PASSWORD=<actual_password_from_SE>
```

**Status:** ☐ .env created with real passwords

### 3.2 Validate .env
```bash
# Check no placeholders remain
grep "changeme" .env
# Should return: (nothing)

# Check passwords are set
grep "DB_PASSWORD\|REDIS_PASSWORD" .env
# Should show real passwords
```

**Status:** ☐ .env validated

---

## ✅ Phase 4: Startup (2 mins)

### 4.1 Run Startup Script
```bash
cd E:\Thesis

# Allow PowerShell scripts (one-time)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# Run automation
.\startup.ps1

# Script will:
# ✅ Check Docker
# ✅ Verify .env
# ✅ Check required files
# ✅ Start Docker Compose
# ✅ Wait for health checks
# ✅ Show service URLs
```

**Expected Output:**
```
✅ Stack Started Successfully

📋 Services:
NAME                STATUS
eduarai_postgres    Up
eduarai_redis       Up
eduarai_ai          Up

🌐 URLs:
  API:        http://localhost:8001
  Health:     http://localhost:8001/health
  Database:   localhost:5432 (PostgreSQL)
  Cache:      localhost:6379 (Redis)
```

**Status:** ☐ Startup script completed successfully

---

## ✅ Phase 5: Verification (3 mins)

### 5.1 Check Containers
```bash
docker-compose ps

# Expected: All 3 containers "Up"
# NAME                STATUS
# eduarai_postgres    Up
# eduarai_redis       Up
# eduarai_ai          Up
```

**Status:** ☐ All containers running

### 5.2 Test Health Check
```bash
curl http://localhost:8001/health

# Expected response:
# {
#   "status": "healthy",
#   "service": "eduarai-ai",
#   "database": "connected",
#   "rag_ready": true,
#   "scheduler_running": true
# }
```

**Status:** ☐ Health check passing

### 5.3 Test Chat Endpoint
```bash
curl -X POST http://localhost:8001/api/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is DNA?"}'

# Expected response:
# {
#   "answer": "Based on our curriculum...",
#   "is_on_topic": true,
#   "max_similarity": 0.78,
#   "num_documents": 3,
#   "latency_ms": 145.2
# }
```

**Status:** ☐ Chat endpoint working

### 5.4 Check Logs
```bash
# Should see initialization logs
docker-compose logs ai-service --tail=20

# Look for:
# ✅ Embedding model loaded
# ✅ Database connected
# ✅ Scheduler started
# ✅ API running on 0.0.0.0:8001
```

**Status:** ☐ Logs show successful initialization

---

## ✅ Phase 6: Commit & Push (1 min)

### 6.1 Git Setup
```bash
cd E:\Thesis

# Activate venv
.\.venv\Scripts\Activate.ps1

# Verify on correct branch
git branch
# Should show: week4-postgres-integration

# Check status
git status
# Should show modified/new files
```

**Status:** ☐ On correct branch

### 6.2 Commit Changes
```bash
git add *.py Dockerfile requirements.txt .env.example docker-compose.override.yml .dockerignore startup.ps1 *.md

git commit -m "Week 4: AI service with RAG + contextual bandit (Docker-ready)"

# Expected: Commit created with ~20 files

git push origin week4-postgres-integration
```

**Status:** ☐ Pushed to feature branch

---

## 🆘 Troubleshooting

### If startup.ps1 fails:

```bash
# Check what went wrong
docker-compose logs

# Common issues:

# 1. Port already in use
netstat -ano | findstr :8001
# Solution: Change API_PORT in .env

# 2. Invalid credentials
docker-compose logs postgres
docker-compose logs redis
# Solution: Check .env passwords match SE's credentials

# 3. Schema not loading
docker-compose logs postgres
# Solution: Verify 01_schema.sql exists and is readable

# 4. Docker daemon not running
# Solution: Start Docker Desktop
```

### If containers won't start:

```bash
# Restart everything
docker-compose down -v
docker-compose up -d

# Wait 30 seconds for PostgreSQL to initialize
sleep 30

# Check status
docker-compose ps
```

### If API won't connect:

```bash
# Verify container is running
docker-compose ps ai-service
# Should show: Up

# Check logs
docker-compose logs ai-service

# Try manual connection test
docker exec -it eduarai_ai curl http://localhost:8001/health
```

---

## ✅ Final Verification Checklist

```bash
☐ Docker version 20.10+
☐ docker-compose version 2.0+
☐ All 16 files in E:\Thesis\
☐ SE's docker-compose.yml present
☐ SE's 01_schema.sql present
☐ .env created with real passwords
☐ No "changeme" in .env
☐ startup.ps1 completed successfully
☐ docker-compose ps shows all 3 containers Up
☐ curl http://localhost:8001/health returns 200
☐ Chat endpoint responds with data
☐ Git branch is week4-postgres-integration
☐ All changes committed
☐ Changes pushed to origin
```

---

## 📝 Success Indicators

You'll know everything is working when:

✅ **All 3 containers are running**
```bash
docker-compose ps
# Shows eduarai_postgres, eduarai_redis, eduarai_ai all "Up"
```

✅ **Health check passes**
```bash
curl http://localhost:8001/health
# Returns JSON with "status": "healthy"
```

✅ **API responds to chat**
```bash
curl -X POST http://localhost:8001/api/chat ...
# Returns answer with is_on_topic and similarity
```

✅ **Logs show no errors**
```bash
docker-compose logs --tail=50
# No ERROR or CRITICAL messages
```

✅ **Git history shows commit**
```bash
git log --oneline -1
# Shows "Week 4: AI service with RAG + contextual bandit"
```

---

## 🚀 Next Steps After Success

1. **Notify Team:**
   ```
   "AI service deployed locally. Docker stack stable."
   ```

2. **Code Review Prep:**
   - All files have type hints ✅
   - Comprehensive docstrings ✅
   - Error handling ✅
   - No garbage code ✅

3. **Create Pull Request:**
   - Base: `main`
   - Compare: `week4-postgres-integration`
   - Title: "Week 4: AI Service with RAG + Contextual Bandit"

4. **Week 5 Planning:**
   - [ ] Merge to main
   - [ ] Thesis writing
   - [ ] Defense slides
   - [ ] Testing + optimization

---

## ⏱️ Time Estimate

| Phase | Time | Status |
|-------|------|--------|
| 1. Preparation | 5 min | ☐ |
| 2. File Setup | 2 min | ☐ |
| 3. Configuration | 1 min | ☐ |
| 4. Startup | 2 min | ☐ |
| 5. Verification | 3 min | ☐ |
| 6. Git Commit | 1 min | ☐ |
| **Total** | **14 min** | ☐ |

---

**Expected Completion Time: 15 minutes**

---

**Status:** ✅ Ready to deploy  
**Last Updated:** 2026-09-19  
**Version:** 1.0.0
