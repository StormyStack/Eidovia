#!/usr/bin/env python3
"""
PostgreSQL Database Connection Pool
Async support for FastAPI + SQLAlchemy
"""

import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from contextlib import asynccontextmanager
import os

logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = os.getenv(
    "DATABASE_ASYNC_URL",
    "postgresql+asyncpg://postgres:thesis_password@localhost:5432/thesis_db"
)

class Database:
    """PostgreSQL async database manager"""
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.engine = None
        self.async_session_maker = None
    
    async def connect(self):
        """Create connection pool"""
        self.engine = create_async_engine(
            self.database_url,
            echo=False,
            pool_size=20,
            max_overflow=40,
            pool_pre_ping=True,
            pool_recycle=3600,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        logger.info("✅ Database connected")
    
    async def disconnect(self):
        """Close connection pool"""
        if self.engine:
            await self.engine.dispose()
            logger.info("❌ Database disconnected")
    
    @asynccontextmanager
    async def get_session(self):
        """Get async session context"""
        if not self.async_session_maker:
            raise RuntimeError("Database not connected")
        
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Database error: {e}")
                raise
    
    async def get_user(self, user_id: str):
        """Get user by ID"""
        from models_postgres import User
        async with self.get_session() as session:
            result = await session.get(User, user_id)
            return result
    
    async def create_session(self, user_id: str):
        """Create new learning session"""
        from models_postgres import Session
        async with self.get_session() as session:
            new_session = Session(user_id=user_id)
            session.add(new_session)
            await session.flush()
            return new_session.session_id
    
    async def log_event(self, event_data: dict):
        """Log interaction event"""
        from models_postgres import Event
        async with self.get_session() as session:
            event = Event(**event_data)
            session.add(event)
            await session.flush()
            return event.event_id
    
    async def log_decision(self, decision_data: dict):
        """Log AI decision"""
        from models_postgres import AiDecisionLog
        async with self.get_session() as session:
            decision = AiDecisionLog(**decision_data)
            session.add(decision)
            await session.flush()
            return decision.decision_id
    
    async def log_episode(self, episode_data: dict):
        """Log RL episode"""
        from models_postgres import RlEpisode
        async with self.get_session() as session:
            episode = RlEpisode(**episode_data)
            session.add(episode)
            await session.flush()
            return episode.episode_id
    
    async def get_document_chunks(self, module_id: str = None):
        """Get curriculum chunks"""
        from models_postgres import DocumentChunk
        from sqlalchemy import select
        async with self.get_session() as session:
            query = select(DocumentChunk)
            if module_id:
                query = query.where(DocumentChunk.module_id == module_id)
            result = await session.execute(query)
            return result.scalars().all()

# Global database instance
db = Database()
