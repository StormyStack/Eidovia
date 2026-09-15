#!/bin/bash
# ============================================================
# GITHUB WORKFLOW - PUSH THESIS TO TEAM REPO
# Command-by-command guide for pushing to StormyStack/Thesis
# ============================================================

# ============================================================
# SETUP: Clone repo and create branch
# ============================================================

# Step 1: Clone the team repo
git clone https://github.com/StormyStack/Thesis.git
cd Thesis

# Step 2: Create and switch to your feature branch
git checkout -b feature/postgres-rag-bandit-integration

# Verify branch created
git branch -a

# ============================================================
# ADD FILES: Copy thesis files to repo
# ============================================================

# Step 3: Copy SQL schema
cp E:\thesis-ai-service\thesis_schema.sql ./ai-service/
cp E:\thesis-ai-service\.gitignore ./

# Step 4: Copy Python models and database files
cp E:\thesis-ai-service\models_postgres.py ./ai-service/
cp E:\thesis-ai-service\database_postgres.py ./ai-service/
cp E:\thesis-ai-service\rag_postgres.py ./ai-service/
cp E:\thesis-ai-service\bandit_postgres.py ./ai-service/

# Step 5: Copy all other thesis files
cp E:\thesis-ai-service\main_week3.py ./ai-service/
cp E:\thesis-ai-service\config_week2.py ./ai-service/
cp E:\thesis-ai-service\config_week3.py ./ai-service/
cp E:\thesis-ai-service\.env ./ai-service/
cp E:\thesis-ai-service\requirements.txt ./

# ============================================================
# GIT WORKFLOW: Stage, commit, push
# ============================================================

# Step 6: Check status
git status

# Step 7: Stage all changes
git add .
git add .gitignore

# Step 8: Create meaningful commit message
git commit -m "Week 4: PostgreSQL integration with RAG + Contextual Bandit

- Add thesis_schema.sql: 11-table PostgreSQL schema for AI tutoring
- Add models_postgres.py: SQLAlchemy ORM models (User, Session, Event, Module, DocumentChunk, AiDecisionLog, RlEpisode, Experiment)
- Add database_postgres.py: Async connection pool + database utilities
- Add rag_postgres.py: RAG retrieval with PostgreSQL + Python vector search (NumPy cosine similarity)
- Add bandit_postgres.py: Contextual bandit with Thompson Sampling + PostgreSQL logging
- Add .gitignore: Ignore Python cache, venv, .env secrets, etc.
- Update requirements.txt: Add sqlalchemy, asyncpg, psycopg2-binary, sentence-transformers

Architecture:
- PostgreSQL 16 database with proper schema per AIE specification
- 11 tables: users, sessions, events, modules, document_chunks, ai_decision_log, rl_episodes, experiments, etc.
- Async SQLAlchemy ORM for database operations
- RAG retriever uses Python (NumPy) for cosine similarity (no pgvector compilation needed on Windows)
- Contextual bandit logs all decisions and episodes to database for thesis analysis
- Full audit trail in ai_decision_log table for reproducibility

Status: Ready for Week 4 integration testing"

# Step 9: Push to remote branch
git push -u origin feature/postgres-rag-bandit-integration

# ============================================================
# CREATE PULL REQUEST on GitHub
# ============================================================

# Step 10: Go to GitHub and create PR
# 1. Visit: https://github.com/StormyStack/Thesis
# 2. You should see a banner "Compare & pull request"
# 3. Click it
# 4. Set:
#    - Base: main
#    - Compare: feature/postgres-rag-bandit-integration
# 5. Add description (copy your commit message)
# 6. Click "Create pull request"
# 7. Ask team to review

# ============================================================
# ALTERNATIVE: If PR banner doesn't show, create manually
# ============================================================

# After git push, go to:
# https://github.com/StormyStack/Thesis/pulls
# Click "New pull request"
# Select your branch

# ============================================================
# AFTER TEAM REVIEW: Merge to main
# ============================================================

# Once approved, on GitHub click "Merge pull request"
# Then locally:

git checkout main
git pull origin main

# Your feature branch code is now in main!

# ============================================================
# VERIFY EVERYTHING
# ============================================================

# Check tables exist
psql -U postgres -d thesis_db -c "\dt"

# Should show all 11 tables

# ============================================================
# DONE!
# ============================================================

echo "✅ Week 4 PostgreSQL integration pushed to team repo!"
echo "Branch: feature/postgres-rag-bandit-integration"
echo "Next: Team reviews and merges to main"
