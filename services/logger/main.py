import asyncio
import json
import logging
import os
import redis.asyncio as redis
import asyncpg
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("logger_service")

REDIS_HOST = os.getenv("REDIS_HOST", "eidovia_redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

DB_USER = os.getenv("POSTGRES_USER", "appuser")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DATABASE_HOST", "eidovia_postgres")
DB_PORT = os.getenv("DATABASE_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "eidovia")

async def get_db_connection():
    while True:
        try:
            conn = await asyncpg.connect(
                user=DB_USER,
                password=DB_PASSWORD,
                database=DB_NAME,
                host=DB_HOST,
                port=DB_PORT
            )
            return conn
        except Exception as e:
            logger.warning(f"Database not ready, retrying in 5s... ({e})")
            await asyncio.sleep(5)

async def process_logs():
    logger.info("Connecting to Redis...")
    r = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True
    )

    logger.info("Connecting to Postgres...")
    conn = await get_db_connection()
    logger.info("Database connected")

    logger.info("Logger service started. Waiting for logs...")

    while True:
        try:
            # BLPOP blocks until a message is available
            result = await r.blpop("raw_audit_logs", timeout=0)
            if not result:
                continue

            queue_name, data = result
            event = json.loads(data)
            
            # ELT/ETL logic: 
            # We filter/transform the log before saving.
            action = event.get("action")
            user_id = event.get("user_id")
            details = event.get("details", {})
            timestamp_str = event.get("timestamp")
            
            if not action or not user_id:
                logger.warning(f"Invalid log event skipped: {event}")
                continue

            # Filtering logic: Only save known events.
            # E.g. user login logout, how many message send
            if action not in ["login", "logout", "register", "message_sent"]:
                logger.info(f"Skipping unknown action: {action}")
                continue

            details_json = json.dumps(details)
            created_at = datetime.fromisoformat(timestamp_str) if timestamp_str else datetime.utcnow()
            
            # Save the defined/filtered log
            try:
                await conn.execute(
                    """
                    INSERT INTO audit_logs (user_id, action, details, created_at)
                    VALUES ($1, $2, $3::jsonb, $4)
                    """,
                    user_id, action, details_json, created_at
                )
                logger.info(f"Processed and saved log: {action} for user {user_id}")
            except asyncpg.exceptions.UndefinedTableError:
                logger.error("audit_logs table does not exist! Waiting for migrations...")
                await asyncio.sleep(5)
                # Retry push back
                await r.lpush("raw_audit_logs", data)

        except Exception as e:
            logger.error(f"Error processing log: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(process_logs())
