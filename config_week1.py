import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT = int(os.getenv("DATABASE_PORT", "5432"))
DATABASE_USER = os.getenv("DATABASE_USER", "thesis_user")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "thesis_password")
DATABASE_NAME = os.getenv("DATABASE_NAME", "thesis_db")

DATABASE_URL = f"postgresql://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
DATABASE_ASYNC_URL = f"postgresql+asyncpg://{DATABASE_USER}:{DATABASE_PASSWORD}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")

# Sentence Transformers
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 22MB, fast, accurate
EMBEDDING_DIMENSION = 384

# RAG Configuration
RAG_THRESHOLD = 0.40  # Cosine similarity threshold for topic relevance
RAG_TOP_K = 3  # Number of chunks to retrieve

# API
API_HOST = os.getenv("API_HOST", "127.0.0.1")
API_PORT = int(os.getenv("API_PORT", "8001"))

# LLM Mock (for Week 1)
USE_MOCK_LLM = True
MOCK_LLM_RESPONSES = {
    "default": "This is a mock response. Full LLM will be integrated in Week 2.",
    "dna_structure": "DNA is a double helix molecule composed of nucleotides. Each nucleotide has a sugar-phosphate backbone and a nitrogenous base (A, T, G, C).",
    "replication": "DNA replication is a semi-conservative process where the double helix unwinds and each strand serves as a template for a new complementary strand.",
}
