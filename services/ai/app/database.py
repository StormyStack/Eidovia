"""
Database Service Module
Async SQLAlchemy connection pooling and session management.
Provides async context manager for safe session handling.
"""

import logging
import contextlib
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import event, text
from typing import Optional, AsyncGenerator

from app import config

logger = logging.getLogger(__name__)

# ============================================================
# DATABASE SERVICE WITH ASYNC CONTEXT MANAGER
# ============================================================

class DatabaseService:
    """
    Manages async PostgreSQL connections with pgvector support.
    Provides async context manager for session lifecycle management.
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
                        "application_name": "eidovia_ai_service"
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
    
    @contextlib.asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get a new database session as async context manager.
        
        Usage:
            async with db.get_session() as session:
                result = await session.execute(query)
        
        Yields:
            AsyncSession for database operations
            
        Raises:
            RuntimeError: If not connected
        """
        if not self.connected or not self.async_session_maker:
            raise RuntimeError("Database not connected. Call connect() first.")
        
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Session error: {e}")
                raise
            finally:
                await session.close()
    
    @property
    def is_healthy(self) -> bool:
        """Check if database connection is healthy."""
        return self.connected


# Global database service instance
db = DatabaseService()