"""
Event Service for EduAR-AI
Handles logging of learner interaction events.
"""

import logging
from typing import Optional
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
from sqlalchemy import text

logger = logging.getLogger(__name__)


class EventRequest(BaseModel):
    """Event request model."""
    user_id: str
    session_id: str
    event_type: str
    payload: Optional[dict] = None
    client_timestamp: Optional[datetime] = None


class EventService:
    """Service for logging events to database."""

    async def log_event(self, session, event: EventRequest) -> str:
        """
        Log an event to the database.
        
        Args:
            session: Database session
            event: Event request data
            
        Returns:
            Event ID as string
        """
        try:
            query = text("""
                INSERT INTO events (user_id, session_id, event_type, payload, client_timestamp)
                VALUES (:user_id, :session_id, :event_type, :payload, :client_timestamp)
                RETURNING event_id
            """)
            
            result = await session.execute(query, {
                "user_id": event.user_id,
                "session_id": event.session_id,
                "event_type": event.event_type,
                "payload": event.payload,
                "client_timestamp": event.client_timestamp or datetime.utcnow()
            })
            
            event_id = result.scalar_one()
            await session.commit()
            
            logger.info(f"Event logged: {event_id} ({event.event_type})")
            return str(event_id)
            
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            await session.rollback()
            raise


event_service = EventService()