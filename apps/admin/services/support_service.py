import logging
import uuid
from typing import List, Optional, Any
from sqlalchemy import text
from fastapi import HTTPException
from db import db
from schemas import SupportTicketCreate, SupportTicketUpdate

logger = logging.getLogger(__name__)


class SupportService:
    @staticmethod
    async def create_ticket(user_id: str, username: str, data: SupportTicketCreate) -> dict[str, Any]:
        async with db.get_session() as session:
            result = await session.execute(
                text("""
                    INSERT INTO support_tickets (user_id, username, subject, message, priority, status)
                    VALUES (:user_id, :username, :subject, :message, :priority, 'open')
                    RETURNING ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at
                """),
                {
                    "user_id": user_id,
                    "username": username,
                    "subject": data.subject,
                    "message": data.message,
                    "priority": data.priority,
                }
            )
            ticket = result.first()
            await session.commit()
            return {
                "ticket_id": str(ticket.ticket_id),
                "user_id": ticket.user_id,
                "username": ticket.username,
                "subject": ticket.subject,
                "message": ticket.message,
                "status": ticket.status,
                "priority": ticket.priority,
                "admin_notes": ticket.admin_notes,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            }

    @staticmethod
    async def list_tickets(status: Optional[str] = None, priority: Optional[str] = None) -> List[dict[str, Any]]:
        async with db.get_session() as session:
            query = """
                SELECT ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at
                FROM support_tickets
            """
            conditions = []
            params: dict[str, Any] = {}
            if status:
                conditions.append("status = :status")
                params["status"] = status
            if priority:
                conditions.append("priority = :priority")
                params["priority"] = priority

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY created_at DESC LIMIT 100"

            result = await session.execute(text(query), params)
            tickets = []
            for row in result.all():
                tickets.append({
                    "ticket_id": str(row.ticket_id),
                    "user_id": row.user_id,
                    "username": row.username,
                    "subject": row.subject,
                    "message": row.message,
                    "status": row.status,
                    "priority": row.priority,
                    "admin_notes": row.admin_notes,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                })
            return tickets

    @staticmethod
    async def update_ticket(ticket_id: str, data: SupportTicketUpdate) -> dict[str, Any]:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ticket ID format")

        async with db.get_session() as session:
            updates = ["updated_at = now()"]
            params: dict[str, Any] = {"tid": tid}

            if data.status is not None:
                updates.append("status = :status")
                params["status"] = data.status
            if data.admin_notes is not None:
                updates.append("admin_notes = :admin_notes")
                params["admin_notes"] = data.admin_notes
            if data.priority is not None:
                updates.append("priority = :priority")
                params["priority"] = data.priority

            sql = f"""
                UPDATE support_tickets
                SET {', '.join(updates)}
                WHERE ticket_id = :tid
                RETURNING ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at
            """
            result = await session.execute(text(sql), params)
            row = result.first()
            if not row:
                raise HTTPException(status_code=404, detail="Ticket not found")
            await session.commit()

            return {
                "ticket_id": str(row.ticket_id),
                "user_id": row.user_id,
                "username": row.username,
                "subject": row.subject,
                "message": row.message,
                "status": row.status,
                "priority": row.priority,
                "admin_notes": row.admin_notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
