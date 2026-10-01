import asyncio, logging, json, asyncpg
from sentence_transformers import SentenceTransformer
from urllib.parse import quote
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PASSWORD = quote(os.getenv("DB_PASSWORD"), safe='')
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
DATABASE_URL = (
    f"postgresql://{POSTGRES_USER}:{DB_PASSWORD}"
    f"@{DATABASE_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

async def main():
    logger.info("Loading model...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("Model loaded")
    
    logger.info("Connecting to database...")
    pool = await asyncpg.create_pool(DATABASE_URL)
    logger.info("Connected!")
    
    logger.info("Creating module...")
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url, difficulty) VALUES ($1, $2, $3, $4, $5) ON CONFLICT DO NOTHING",
            "DNA_BIOLOGY_001", "DNA & Cell Biology", "dna_scene", "https://cdn.example.com/dna-bundle.zip", 3
        )
    logger.info("Module created")
    
    logger.info("Reading curriculum...")
    with open("expanded_dna_curriculum.txt") as f:
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