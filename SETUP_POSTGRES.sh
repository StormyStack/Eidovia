#!/bin/bash
# ============================================================
# THESIS DATABASE SETUP SCRIPT
# AI Engineer: Shabab
# Purpose: PostgreSQL + Python vector search setup
# ============================================================

set -e  # Exit on error

POSTGRES_USER="postgres"
POSTGRES_PASS="thesis_password"
POSTGRES_HOST="localhost"
POSTGRES_PORT="5432"
DB_NAME="thesis_db"
PSQL_PATH="C:\Program Files\PostgreSQL\16\bin\psql.exe"

echo "=========================================="
echo "THESIS POSTGRESQL SETUP"
echo "=========================================="

# Step 1: Create database
echo ""
echo "[1/7] Creating database thesis_db..."
powershell -Command "& '$PSQL_PATH' -U $POSTGRES_USER -h $POSTGRES_HOST -p $POSTGRES_PORT -c 'CREATE DATABASE $DB_NAME;' 2>/dev/null || true"

# Step 2: Create extensions
echo "[2/7] Creating extensions (uuid-ossp)..."
powershell -Command "& '$PSQL_PATH' -U $POSTGRES_USER -h $POSTGRES_HOST -p $POSTGRES_PORT -d $DB_NAME -c 'CREATE EXTENSION IF NOT EXISTS uuid-ossp;'"

# Step 3: Load schema
echo "[3/7] Loading database schema..."
if [ -f "schema_postgres.sql" ]; then
    powershell -Command "& '$PSQL_PATH' -U $POSTGRES_USER -h $POSTGRES_HOST -p $POSTGRES_PORT -d $DB_NAME -f schema_postgres.sql"
    echo "✅ Schema loaded"
else
    echo "❌ schema_postgres.sql not found"
    exit 1
fi

# Step 4: Install Python dependencies
echo ""
echo "[4/7] Installing Python dependencies..."
pip install --upgrade pip
pip install \
    sqlalchemy==2.0.23 \
    psycopg2-binary==2.9.9 \
    asyncpg==0.29.0 \
    sentence-transformers==2.5.1 \
    numpy==1.24.3 \
    pandas==2.1.0 \
    apscheduler==3.10.4 \
    mlflow==2.11.0 \
    redis==5.0.0 \
    pydantic==2.5.0 \
    FastAPI==0.104.1 \
    uvicorn==0.24.0 \
    websockets==12.0

# Step 5: Create .env file
echo ""
echo "[5/7] Creating .env file..."
cat > .env << EOF
# PostgreSQL Configuration
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_USER=postgres
DATABASE_PASSWORD=thesis_password
DATABASE_NAME=thesis_db
DATABASE_URL=postgresql://postgres:thesis_password@localhost:5432/thesis_db
DATABASE_ASYNC_URL=postgresql+asyncpg://postgres:thesis_password@localhost:5432/thesis_db

# API Configuration
API_HOST=127.0.0.1
API_PORT=8001

# Model Configuration
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384

# RAG Configuration
RAG_THRESHOLD=0.40
RAG_TOP_K=3

# LLM Configuration
USE_MOCK_LLM=True
LLM_TIMEOUT=30

# MLflow Configuration
MLFLOW_TRACKING_URI=file:./mlruns
MLFLOW_EXPERIMENT_NAME=thesis-adaptive-learning

# Redis Configuration
REDIS_URL=redis://localhost:6379

# Application
DEBUG=False
LOG_LEVEL=INFO
EOF
echo "✅ .env file created"

# Step 6: Verify database connection
echo ""
echo "[6/7] Verifying PostgreSQL connection..."
powershell -Command "& '$PSQL_PATH' -U $POSTGRES_USER -h $POSTGRES_HOST -p $POSTGRES_PORT -d $DB_NAME -c 'SELECT version();'"
echo "✅ PostgreSQL connection successful"

# Step 7: Initialize data directories
echo ""
echo "[7/7] Initializing data directories..."
mkdir -p data/
mkdir -p logs/
mkdir -p mlruns/
touch data/.gitkeep
echo "✅ Directories created"

echo ""
echo "=========================================="
echo "✅ SETUP COMPLETE"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate venv: .\.venv\Scripts\Activate.ps1"
echo "2. Run migration: python migrate_to_postgres.py"
echo "3. Start API: python main_postgres.py"
echo "4. Run tests: python integration_tests_postgres.py"
echo ""
echo "Database: $DB_NAME"
echo "User: $POSTGRES_USER"
echo "Host: $POSTGRES_HOST:$POSTGRES_PORT"
echo ""
