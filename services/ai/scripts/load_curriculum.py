import asyncio, logging, json, asyncpg
from sentence_transformers import SentenceTransformer
from urllib.parse import quote
import os
from dotenv import load_dotenv

from pathlib import Path

# Resolve repo root and data directories
SCRIPT_DIR = Path(__file__).resolve().parent
SERVICE_DIR = SCRIPT_DIR.parent
ROOT_DIR = SERVICE_DIR.parent.parent

# Load root .env
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PASSWORD = quote(os.getenv("DB_PASSWORD", ""), safe='')
POSTGRES_USER = os.getenv("POSTGRES_USER", "appuser")
POSTGRES_DB = os.getenv("POSTGRES_DB", "eidovia")
DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")

# If connecting to the docker service name "postgres", the internal port is 5432
if DATABASE_HOST == "postgres":
    POSTGRES_PORT = os.getenv("DATABASE_PORT", "5432")
else:
    POSTGRES_PORT = os.getenv("DATABASE_PORT", os.getenv("POSTGRES_PORT", "6543"))
DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{DB_PASSWORD}"
    f"@{DATABASE_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

async def main():
    logger.info("Loading model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Model loaded")
    
    logger.info(f"Connecting to database {DATABASE_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}...")
    pool = await asyncpg.create_pool(DATABASE_URL)
    logger.info("Connected!")
    
    logger.info("Creating module...")
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url, difficulty) VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
            "DNA_BIOLOGY_001", "DNA & Cell Biology", "dna_scene", "https://cdn.example.com/dna-bundle.zip", 3
        )
    logger.info("Module created")
    
    data_file = SERVICE_DIR / "data" / "expanded_dna_curriculum.txt"
    if not data_file.exists():
        data_file = SERVICE_DIR / "data" / "dna_curriculum.txt"
    logger.info(f"Reading curriculum from {data_file}...")
    with open(data_file, "r", encoding="utf-8") as f:
        text = f.read()
    logger.info(f"Curriculum: {len(text)} chars")
    
    chunks = []
    for i in range(0, len(text), 500):
        chunk = text[i:i+500].strip()
        if chunk:
            chunks.append(chunk)
    logger.info(f"Chunks: {len(chunks)}")
    
    logger.info("Generating embeddings...")
    embeddings = model.encode(chunks)
    logger.info("Embeddings done")
    
    logger.info("Inserting into database...")
    async with pool.acquire() as conn:
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            emb_str = '[' + ', '.join(map(str, emb)) + ']'
            await conn.execute(
                "INSERT INTO document_chunks (module_id, content, embedding) VALUES ($1, $2, $3::vector(384))",
                "DNA_BIOLOGY_001", chunk, emb_str
            )
            if (i+1) % 10 == 0:
                logger.info(f"  Inserted {i+1}/{len(chunks)}")
    
    await pool.close()
    logger.info("SUCCESS!")

asyncio.run(main())