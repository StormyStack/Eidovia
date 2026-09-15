import asyncpg
import logging
from config import DATABASE_ASYNC_URL, DATABASE_URL

logger = logging.getLogger("database")

async def init_db():
    """Initialize database and create tables with pgvector"""
    
    # Connect and create pgvector extension
    conn = await asyncpg.connect(DATABASE_ASYNC_URL)
    
    try:
        # Create pgvector extension
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        logger.info("pgvector extension created/verified")
        
        # Create tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id BIGSERIAL PRIMARY KEY,
                doc_id VARCHAR(255) NOT NULL,
                chunk_index INT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(384),
                topic VARCHAR(100) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(doc_id, chunk_index)
            );
        """)
        logger.info("document_chunks table created/verified")
        
        # Create index for faster cosine similarity search
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_embedding 
            ON document_chunks USING ivfflat (embedding vector_cosine_ops);
        """)
        logger.info("pgvector index created/verified")
        
        # Create events table (for future RL features)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id BIGSERIAL PRIMARY KEY,
                event_id UUID UNIQUE NOT NULL,
                user_id UUID NOT NULL,
                session_id UUID NOT NULL,
                event_type VARCHAR(64) NOT NULL,
                payload JSONB,
                client_timestamp TIMESTAMPTZ,
                server_timestamp TIMESTAMPTZ DEFAULT NOW()
            );
        """)
        logger.info("events table created/verified")
        
        # Create sessions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id BIGSERIAL PRIMARY KEY,
                session_id UUID UNIQUE NOT NULL,
                user_id UUID NOT NULL,
                started_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP
            );
        """)
        logger.info("sessions table created/verified")
        
        # Create ai_decision_log table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_decision_log (
                id BIGSERIAL PRIMARY KEY,
                session_id UUID NOT NULL,
                decision_type VARCHAR(64) NOT NULL,
                decision_data JSONB,
                latency_ms INT,
                created_at TIMESTAMP DEFAULT NOW()
            );
        """)
        logger.info("ai_decision_log table created/verified")
        
        logger.info("✅ Database initialization complete")
        
    except Exception as e:
        logger.error(f"Database init failed: {e}")
        raise
    finally:
        await conn.close()

async def get_db_pool():
    """Create connection pool for database queries"""
    return await asyncpg.create_pool(DATABASE_ASYNC_URL, min_size=5, max_size=20)
