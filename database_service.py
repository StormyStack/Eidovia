"""
Database Service Module
Async SQLAlchemy connection pooling and session management.
"""

import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event, text  # ← Add "text" here
from typing import Optional

import config_prod as config

logger = logging.getLogger(__name__)

# ============================================================
# DATABASE SERVICE
# ============================================================

class DatabaseService:
    """
    Manages async PostgreSQL connections with pgvector support.
    """
    
    def __init__(self):
        """Initialize database service."""
        self.engine = None
        self.async_session_maker = None
        self.connected = False
    
    async def connect(self) -> None:
        """
        Establish database connection and create session factory.
        
        Raises:
            RuntimeError: If connection fails
        """
        try:
            self.engine = create_async_engine(
                config.DATABASE_URL,
                pool_size=config.DB_POOL_SIZE,
                max_overflow=config.DB_MAX_OVERFLOW,
                pool_timeout=config.DB_POOL_TIMEOUT,
                echo=config.DB_ECHO,
                connect_args={
                    "timeout": 10,
                    "command_timeout": 10,
                    "server_settings": {
                        "application_name": "eduarai_ai_service"
                    }
                }
            )
            
            self.async_session_maker = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
                autoflush=False
            )
            
            # Test connection
            async with self.engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            
            self.connected = True
            logger.info("✅ Database connected successfully")
            logger.info(
                f"Pool config: size={config.DB_POOL_SIZE}, "
                f"overflow={config.DB_MAX_OVERFLOW}, "
                f"timeout={config.DB_POOL_TIMEOUT}s"
            )
            
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            self.connected = False
            raise RuntimeError(f"Database connection error: {e}")
    
    async def disconnect(self) -> None:
        """Close all database connections."""
        if self.engine:
            await self.engine.dispose()
            self.connected = False
            logger.info("Database disconnected")
    
    async def get_session(self) -> AsyncSession:
        """
        Get a new database session.
        
        Returns:
            AsyncSession for database operations
            
        Raises:
            RuntimeError: If not connected
        """
        if not self.connected or not self.async_session_maker:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        return self.async_session_maker()
    
    @property
    def is_healthy(self) -> bool:
        """Check if database connection is healthy."""
        return self.connected


# Global database service instance
db = DatabaseService()
