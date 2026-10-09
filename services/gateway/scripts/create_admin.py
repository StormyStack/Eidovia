import asyncio
import logging
import sys

from sqlalchemy import text
from app.db import db
from app.security import hash_password

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def create_admin(username: str, email: str, password: str):
    await db.connect()
    
    password_hash = await hash_password(password)
    
    async with db.get_session() as session:
        # Check if exists
        result = await session.execute(
            text("SELECT user_id FROM users WHERE username = :username OR email = :email"),
            {"username": username, "email": email}
        )
        row = result.first()
        if row:
            logger.info(f"User {username} already exists. Promoting to admin...")
            await session.execute(
                text("UPDATE users SET is_admin = TRUE WHERE user_id = :user_id"),
                {"user_id": row.user_id}
            )
            logger.info(f"User {username} is now an admin.")
        else:
            logger.info(f"Creating new admin user {username}...")
            await session.execute(
                text("""
                    INSERT INTO users (username, email, password_hash, language, is_admin)
                    VALUES (:username, :email, :password_hash, 'en', TRUE)
                """),
                {"username": username, "email": email, "password_hash": password_hash}
            )
            logger.info(f"Admin user {username} created successfully.")
            
    await db.disconnect()

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python -m scripts.create_admin <username> <email> <password>")
        sys.exit(1)
        
    username = sys.argv[1]
    email = sys.argv[2]
    password = sys.argv[3]
    
    asyncio.run(create_admin(username, email, password))
