"""
EduAR-AI Configuration Module
Handles environment variables, connection strings, and global constants.
"""

import os
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ============================================================
# LOGGING CONFIGURATION
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

def get_env(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Safely retrieve environment variable with validation."""
    value = os.getenv(key, default)
    if value is None and required:
        raise ValueError(f"Required environment variable not set: {key}")
    return value or default


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DATABASE_HOST = get_env("DATABASE_HOST", "eduarai_postgres")
DATABASE_PORT = get_env("DATABASE_PORT", "5432")
DATABASE_USER = get_env("POSTGRES_USER", "appuser")
DATABASE_PASSWORD = get_env("DB_PASSWORD", required=True)
DATABASE_NAME = get_env("POSTGRES_DB", "eduarai")

DATABASE_URL = f"postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"

DB_POOL_SIZE = int(get_env("DB_POOL_SIZE", "10"))
DB_MAX_OVERFLOW = int(get_env("DB_MAX_OVERFLOW", "20"))
DB_POOL_TIMEOUT = int(get_env("DB_POOL_TIMEOUT", "30"))
DB_ECHO = get_env("DB_ECHO", "False").lower() == "true"

# ============================================================
# REDIS CONFIGURATION
# ============================================================

REDIS_HOST = get_env("REDIS_HOST", "eduarai_redis")
REDIS_PORT = get_env("REDIS_PORT", "6379")
REDIS_PASSWORD = get_env("REDIS_PASSWORD", required=True)
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}"

REDIS_SESSION_STATE_PREFIX = "session"
REDIS_USER_PROFILE_PREFIX = "user"
REDIS_ETL_LOCK_PREFIX = "lock:etl_refresh"
REDIS_TTL_SESSION_STATE = 3600
REDIS_TTL_PROFILE = 7200

# ============================================================
# RAG CONFIGURATION
# ============================================================

EMBEDDING_MODEL = get_env("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
EMBEDDING_DIMENSION = 384

RAG_THRESHOLD = float(get_env("RAG_THRESHOLD", "0.40"))
RAG_TOP_K = int(get_env("RAG_TOP_K", "3"))
RAG_TIMEOUT = float(get_env("RAG_TIMEOUT", "5.0"))
# ============================================================
# BANDIT CONFIGURATION
# ============================================================

BANDIT_ACTIONS = [
    "increase_difficulty",
    "decrease_difficulty", 
    "maintain_difficulty",
    "show_hint",
    "hide_hint",
    "suggest_quiz",
    "suggest_ar_activity",
    "switch_scene"
]
BANDIT_NUM_ACTIONS = len(BANDIT_ACTIONS)
BANDIT_EPSILON = float(get_env("BANDIT_EPSILON", "0.15"))
BANDIT_STATE_DIM = 8

# ============================================================
# SCHEDULER CONFIGURATION
# ============================================================

ETL_REFRESH_INTERVAL = int(get_env("ETL_REFRESH_INTERVAL", "60"))
ETL_SESSION_WINDOW = int(get_env("ETL_SESSION_WINDOW", "30"))
ETL_LOCK_TTL = 15

# ============================================================
# API CONFIGURATION
# ============================================================

API_HOST = get_env("API_HOST", "127.0.0.1")
API_PORT = int(get_env("API_PORT", "8001"))

WS_TIMEOUT = float(get_env("WS_TIMEOUT", "10.0"))
WS_MAX_FRAME_SIZE = int(get_env("WS_MAX_FRAME_SIZE", "1000000"))
REQUEST_TIMEOUT = float(get_env("REQUEST_TIMEOUT", "5.0"))

# ============================================================
# FEATURE FLAGS
# ============================================================

DEBUG = get_env("DEBUG", "False").lower() == "true"
MOCK_LLM = get_env("MOCK_LLM", "True").lower() == "true"
