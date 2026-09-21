# 📌 Git Workflow for EduAR-AI Team

Collaboration guide for AI Engineer + SE + other developers.

---

## 🌳 Branch Structure

```
main (production)
  ↓
  ├── data-layer (SE's infrastructure - LOCKED)
  │   ├── docker-compose.yml
  │   ├── 01_schema.sql
  │   └── .env.example
  │
  └── week4-postgres-integration (AIE's feature)
      ├── AI service (*.py files)
      ├── Dockerfile
      ├── requirements.txt
      ├── docker-compose.override.yml
      └── Startup scripts
```

---

## 🚀 Initial Setup (First Time)

### 1. Clone Repository

```bash
git clone https://github.com/StormyStack/Thesis.git
cd Thesis
```

### 2. List All Branches

```bash
git branch -a

# Output:
# * main
#   remotes/origin/data-layer
#   remotes/origin/week4-postgres-integration
```

### 3. Checkout SE's Infrastructure

```bash
# Get the latest schema and docker-compose
git fetch origin
git checkout data-layer

# Verify you have:
# - docker-compose.yml
# - 01_schema.sql
# - .env.example
ls -la docker-compose.yml 01_schema.sql .env.example
```

### 4. Checkout AI Service Branch

```bash
git checkout week4-postgres-integration

# Verify you have:
# - main_service.py
# - config_prod.py
# - All other AI service files
```

---

## 📝 Daily Workflow

### Start of Day

```bash
cd E:\Thesis

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Fetch latest changes
git fetch origin

# Make sure you're on your feature branch
git checkout week4-postgres-integration

# Pull any updates from team
git pull origin week4-postgres-integration

# Start services
docker-compose up -d
```

### During Development

```bash
# Check current branch
git branch

# Make changes to files
notepad main_service.py
# ... edit code ...

# See what changed
git status
git diff main_service.py

# Stage changes
git add main_service.py config_prod.py

# Commit with descriptive message
git commit -m "Fix RAG threshold validation and add logging"

# Push to your feature branch
git push origin week4-postgres-integration
```

### End of Day

```bash
# Make sure everything is committed
git status
# Should show: "nothing to commit, working tree clean"

# Push all changes
git push origin week4-postgres-integration

# Stop services
docker-compose stop
```

---

## 🔄 Syncing with SE's Updates

SE might update the database schema or Docker setup.

### Pull SE's Latest Changes

```bash
# Save your current work
git status
# All should be committed

# Add SE's branch as upstream (one-time setup)
git remote add se-upstream origin

# Fetch SE's latest
git fetch origin data-layer

# Merge SE's schema into your feature branch
git checkout week4-postgres-integration
git merge origin/data-layer --no-edit

# Restart services with updated schema
docker-compose down -v
docker-compose up -d

# Push merged changes
git push origin week4-postgres-integration
```

---

## ✅ Before Creating a Pull Request

### 1. Final Tests

```bash
# Restart clean stack
docker-compose down -v
docker-compose up -d

# Wait for health
sleep 10

# Test health check
curl http://localhost:8001/health

# Test chat endpoint
curl -X POST http://localhost:8001/api/chat \
  -H "Content-Type: application/json" \
  -d '{"question":"What is DNA?"}'
```

### 2. Check for Secrets

```bash
# Make sure .env is NOT committed
git status | grep ".env"
# Should show nothing

# Verify .env.example has placeholders
grep "changeme" .env.example
```

### 3. View Your Changes

```bash
# See all commits since main
git log --oneline origin/main..HEAD

# See all file changes
git diff origin/main..HEAD --stat

# Review specific file
git diff origin/main -- main_service.py
```

### 4. Check Code Quality

```bash
# Run tests
pytest tests/ -v

# Check for syntax errors
python -m py_compile *.py

# Check formatting
black --check *.py
```

---

## 📤 Create Pull Request

### On GitHub

1. Go to https://github.com/StormyStack/Thesis
2. Click "Pull Requests"
3. Click "New Pull Request"
4. **Base:** `main`
5. **Compare:** `week4-postgres-integration`
6. Write description:

```
## Week 4: AI Service with RAG + Contextual Bandit

### Changes
- ✅ FastAPI microservice with chat + WebSocket endpoints
- ✅ RAG service with pgvector cosine similarity
- ✅ Contextual bandit with 8-action policy
- ✅ Background ETL scheduler
- ✅ Full Docker Compose integration

### Testing
- ✅ Unit tests for RAG and bandit
- ✅ Integration tests with PostgreSQL
- ✅ API health checks passing
- ✅ Chat endpoint responding

### Files
- main_service.py: FastAPI application
- rag_service.py: Document retrieval
- bandit_service.py: Adaptive learning
- database_service.py: Database layer
- scheduler_service.py: Background jobs
- config_prod.py: Configuration
- Dockerfile: Container image
- requirements.txt: Dependencies

### Related to Issue
Closes #45 (Week 4 implementation)
```

7. Click "Create Pull Request"

---

## 🔀 Merging Pull Request

After team review:

```bash
# Switch to main
git checkout main

# Pull latest main
git pull origin main

# Merge your feature branch
git merge week4-postgres-integration

# Push to main
git push origin main

# Optional: Delete feature branch
git branch -d week4-postgres-integration
git push origin --delete week4-postgres-integration
```

---

## 🚨 Conflict Resolution

If there's a merge conflict:

```bash
# See conflicts
git status

# Open conflicted file
notepad main_service.py

# Look for conflict markers:
# <<<<<<< HEAD
#   your changes
# =======
#   their changes
# >>>>>>> branch-name

# Edit to keep what's needed
# Then:

git add main_service.py
git commit -m "Resolve merge conflict with data-layer"
git push origin week4-postgres-integration
```

---

## 👥 Collaboration with SE

### SE Updates Schema

```bash
# SE tells you: "Updated 01_schema.sql"

git fetch origin data-layer
git merge origin/data-layer --no-edit

# Restart database (WIPES DATA)
docker-compose down -v
docker-compose up -d postgres redis

# Verify new schema
docker exec -it eduarai_postgres psql -U appuser -d eduarai -c "\dt"

# Restart AI service
docker-compose up -d ai-service
```

### You Update Docker Config

```bash
# You edit Dockerfile or docker-compose.override.yml

git add Dockerfile docker-compose.override.yml
git commit -m "Optimize Docker image size"
git push origin week4-postgres-integration

# Tell SE: "Updated Docker build"
```

### Release to Production

```bash
# On main branch
git checkout main
git pull origin main

# Tag release
git tag -a v1.0.0 -m "Release 1.0: Week 4 complete"
git push origin v1.0.0

# Deploy
docker-compose build --no-cache
docker-compose up -d
```

---

## 📊 Useful Git Commands

### View History

```bash
# See commit log
git log --oneline -10

# See graph of branches
git log --graph --oneline --all

# See who changed what
git blame main_service.py
```

### Undo Changes

```bash
# Discard uncommitted changes
git checkout -- main_service.py

# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Undo pushed commit (creates new commit)
git revert HEAD
git push origin week4-postgres-integration
```

### Stash Work

```bash
# Save work temporarily
git stash

# List stashed work
git stash list

# Restore stashed work
git stash pop
```

---

## ✅ Checklist Before Pushing

```bash
☐ All changes committed
☐ No uncommitted .env files
☐ No sensitive data in code
☐ Tests passing
☐ Code formatted properly
☐ Commit messages are descriptive
☐ Pushed to feature branch (not main)
☐ Ready for team review
```

---

## 🆘 Emergency: Revert a Mistake

```bash
# Oops! Just committed something bad
git reset --soft HEAD~1
# Changes go back to staging

# Or: Want to undo a pushed commit
git revert HEAD
git push origin week4-postgres-integration

# Or: Need to go back to last known good
git reset --hard origin/week4-postgres-integration
```

---

## 📚 Team Communication

### When Pushing
```
"Just pushed X, ready for review"
```

### When Pulling SE's Changes
```
"Pulled latest schema from data-layer, restarted containers"
```

### When Merging
```
"Merged week4 to main, v1.0.0 ready for release"
```

---

**Last Updated:** 2026-09-18
