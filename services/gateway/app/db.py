"""
Gateway Database Service
Async SQLAlchemy (asyncpg) engine + session context manager.

Mirrors the pattern of the AI service's database_service.py, but is configured
from the gateway's own settings (importing the root module would also require
the AI service's Redis/RAG environment variables).
"""

import logging
import contextlib
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Manages the async PostgreSQL engine and per-request sessions."""

    def __init__(self) -> None:
        self.engine: Optional[AsyncEngine] = None
        self.async_session_maker: Optional[async_sessionmaker] = None

    async def connect(self, database_url: Optional[str] = None) -> None:
        """
        Create the engine and session factory, then try one test query.
        A failed test query is logged, not raised: the gateway still starts and
        /health reports the database as disconnected until it becomes reachable.

        Args:
            database_url: Override for scripts/tests; defaults to the configured database
        """
        settings = get_settings()
        self.engine = create_async_engine(
            database_url or settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
            connect_args={
                "timeout": 5,
                "command_timeout": 10,
                "server_settings": {"application_name": "eduarai_gateway"},
            },
        )
        self.async_session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

        if await self.ping():
            logger.info("Database connected")
        else:
            logger.warning("Database not reachable at startup; will retry on each request")

    async def disconnect(self) -> None:
        """Dispose of all pooled connections."""
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.async_session_maker = None
            logger.info("Database disconnected")

    async def ping(self) -> bool:
        """Return True if a trivial query succeeds."""
        if not self.engine:
            return False
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"Database ping failed: {type(e).__name__}")
            return False

    @contextlib.asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Yield a session; commit on success, roll back on error.

        Usage:
            async with db.get_session() as session:
                result = await session.execute(text("SELECT 1"))
        """
        if not self.async_session_maker:
            raise RuntimeError("Database not initialised. Call connect() first.")

        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise


# Global database service instance
db = DatabaseService()
