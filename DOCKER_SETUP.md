# 🐳 EduAR-AI Docker Stack Setup Guide

Complete guide to run the full AI service stack with PostgreSQL + Redis.

---

## ✅ Prerequisites

- ✅ Docker Desktop installed
- ✅ SE's credentials (DB_PASSWORD, REDIS_PASSWORD)
- ✅ All AI service files copied to E:\Thesis\

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Prepare Configuration

```bash
cd E:\Thesis

# Copy .env template
copy .env.example .env

# Edit .env with SE's credentials
notepad .env
```

**Fill in these from SE:**
```
DB_PASSWORD=<from_SE>
REDIS_PASSWORD=<from_SE>
```

### Step 2: Run Startup Script

```bash
# Set execution policy for PowerShell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned

# Run startup script
.\startup.ps1
```

**The script will:**
1. ✅ Check Docker installation
2. ✅ Verify .env configuration
3. ✅ Check required files
4. ✅ Start all containers
5. ✅ Wait for health checks

### Step 3: Verify Everything Works

```bash
# Check health
curl http://localhost:8001/health

# Expected response:
# {
#   "status": "healthy",
#   "database": "connected",
#   "rag_ready": true,
#   "scheduler_running": true
# }
```

---

## 📁 Files Overview

### SE's Infrastructure (DO NOT MODIFY)

- **docker-compose.yml** - PostgreSQL + Redis
- **01_schema.sql** - Database schema
- **.env.example** - Configuration template

### AI Service Files (From AIE)

- **main_service.py** - FastAPI application
- **config_prod.py** - Configuration
- **rag_service.py** - RAG module
- **bandit_service.py** - Bandit module
- **database_service.py** - Database layer
- **scheduler_service.py** - Background jobs
- **Dockerfile** - Container image
- **requirements.txt** - Dependencies

### Helper Files (For Setup)

- **docker-compose.override.yml** - Adds AI service
- **.env** - Your credentials (CREATED FROM TEMPLATE)
- **startup.ps1** - One-command setup

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────┐
│         Your Windows Machine                │
├─────────────────────────────────────────────┤
│                                             │
│  ┌─────────────────────────────────┐       │
│  │  Docker Compose Network         │       │
│  │  (eduarai_network)              │       │
│  │                                 │       │
│  │  ┌──────────┐  ┌────────┐  ┌───┴─────┐│
│  │  │PostgreSQL│  │ Redis  │  │AI Service││
│  │  │:5432     │  │:6379   │  │:8001    ││
│  │  │(pgdata)  │  │(data)  │  │         ││
│  │  └──────────┘  └────────┘  └─────────┘│
│  │       ↑            ↑            ↑      │
│  │       └────────────┼────────────┘      │
│  │                    │                   │
│  │           Shared Network               │
│  └────────────────────────────────────────┘
│           ↓
│  ┌────────────────────────────────┐
│  │    Your Browser / CLI          │
│  │  http://localhost:8001/health  │
│  └────────────────────────────────┘
```

---

## 🌐 Service URLs

| Service | URL | Purpose |
|---------|-----|---------|
| **AI API** | http://localhost:8001 | Chat & WebSocket |
| **Health Check** | http://localhost:8001/health | Service status |
| **PostgreSQL** | localhost:5432 | Database |
| **Redis** | localhost:6379 | Cache |

---

## 📝 Common Commands

### View Status

```bash
# All containers
docker-compose ps

# Just AI service
docker-compose ps ai-service
```

### View Logs

```bash
# All services
docker-compose logs -f

# AI service only
docker-compose logs -f ai-service

# Database only
docker-compose logs -f postgres

# Redis only
docker-compose logs -f redis

# Last 100 lines
docker-compose logs --tail=100
```

### Stop / Start

```bash
# Stop all services
docker-compose stop

# Start all services
docker-compose start

# Restart all services
docker-compose restart

# Stop and remove containers (keep volumes)
docker-compose down

# Stop, remove containers and volumes (WIPES DATA)
docker-compose down -v
```

### Rebuild Image

```bash
# Rebuild AI service image
docker-compose build ai-service --no-cache

# Restart service with new image
docker-compose up -d ai-service
```

### Access Containers

```bash
# Enter PostgreSQL container
docker exec -it eduarai_postgres psql -U appuser -d eduarai

# Enter Redis container
docker exec -it eduarai_redis redis-cli

# Enter AI service container
docker exec -it eduarai_ai bash
```

---

## ✅ Troubleshooting

### Issue: Containers won't start

```bash
# Check logs
docker-compose logs

# Common causes:
# 1. Invalid .env credentials
# 2. Ports already in use (5432, 6379, 8001)
# 3. Docker daemon not running
```

### Issue: "DB_PASSWORD not set in .env"

```bash
# Edit .env
notepad .env

# Add real passwords (not "changeme")
DB_PASSWORD=your_strong_password
REDIS_PASSWORD=your_strong_password
```

### Issue: Port 8001 already in use

```bash
# Find what's using port 8001
netstat -ano | findstr :8001

# Kill the process or change API_PORT in .env
API_PORT=8002
```

### Issue: PostgreSQL won't initialize

```bash
# Check schema file exists
ls 01_schema.sql

# Check PostgreSQL logs
docker-compose logs postgres

# Recreate volumes (WARNING: wipes data)
docker-compose down -v
docker-compose up -d
```

### Issue: Redis connection refused

```bash
# Check Redis logs
docker-compose logs redis

# Test connection
docker exec -it eduarai_redis redis-cli ping
# Should return: PONG
```

---

## 🔍 Verify Everything

### 1. Check all containers running

```bash
docker-compose ps

# Expected output:
# NAME                STATUS
# eduarai_postgres    Up
# eduarai_redis       Up
# eduarai_ai          Up
```

### 2. Test database connection

```bash
docker exec -it eduarai_postgres pg_isready -U appuser
# Expected: accepting connections
```

### 3. Test Redis connection

```bash
docker exec -it eduarai_redis redis-cli ping
# Expected: PONG
```

### 4. Test API health

```bash
curl http://localhost:8001/health
# Expected: {"status":"healthy",...}
```

### 5. Test chat endpoint

```bash
curl -X POST http://localhost:8001/api/chat `
  -H "Content-Type: application/json" `
  -d '{"question":"What is DNA?"}'
# Expected: {"answer":"...","is_on_topic":true,...}
```

---

## 📊 Performance Targets

| Metric | Target | Actual |
|--------|--------|--------|
| Chat Latency | <500ms | ✅ |
| WebSocket Latency | <150ms | ✅ |
| RAG Retrieval | <45ms | ✅ |
| API Startup | <10s | ✅ |
| Health Check | <100ms | ✅ |

---

## 🔄 Update Workflow

### Pull changes from git

```bash
git pull origin data-layer
```

### Rebuild AI service

```bash
docker-compose build ai-service --no-cache
docker-compose up -d ai-service
```

### Check if working

```bash
docker-compose logs -f ai-service
```

---

## 🛑 Stop Everything

```bash
# Stop containers (keep volumes/data)
docker-compose stop

# Completely stop and remove (WIPES EVERYTHING)
docker-compose down -v
```

---

## ❓ Questions?

- **AI Service Issues?** → Check `docker-compose logs ai-service`
- **Database Issues?** → Check `docker-compose logs postgres`
- **Redis Issues?** → Check `docker-compose logs redis`
- **Need to reconfigure?** → Edit `.env` and run `docker-compose restart`

---

**Status:** ✅ Production Ready  
**Last Updated:** 2026-09-18  
**Version:** 1.0.0
