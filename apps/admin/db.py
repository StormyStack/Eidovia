import logging
import contextlib
from typing import AsyncGenerator, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from config import get_settings

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self) -> None:
        self.engine: Optional[AsyncEngine] = None
        self.async_session_maker: Optional[async_sessionmaker] = None

    async def connect(self) -> None:
        settings = get_settings()
        self.engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            connect_args={
                "timeout": 5,
                "command_timeout": 10,
                "server_settings": {"application_name": "eidovia_admin"},
            },
        )
        self.async_session_maker = async_sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
        if await self.ping():
            logger.info("Admin Database connected")
        else:
            logger.warning("Admin Database not reachable at startup")

    async def disconnect(self) -> None:
        if self.engine:
            await self.engine.dispose()
            self.engine = None
            self.async_session_maker = None
            logger.info("Admin Database disconnected")

    async def ping(self) -> bool:
        if not self.engine:
            return False
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            logger.debug(f"Admin DB ping failed: {exc}")
            return False

    @contextlib.asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        if not self.async_session_maker:
            raise RuntimeError("DatabaseService is not connected")
        async with self.async_session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

db = DatabaseService()
