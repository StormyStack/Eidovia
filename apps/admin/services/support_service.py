import logging
import uuid
from typing import List, Optional, Any
from sqlalchemy import text
from fastapi import HTTPException
from db import db
from schemas import SupportTicketCreate, SupportTicketUpdate

logger = logging.getLogger(__name__)

# wildcard requests from the app are tickets of kind 'wildcard' (migration 008; also added here at runtime)
SUPPORT_COLUMNS = [
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'general'",
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS requested_amount INT",
    "ALTER TABLE support_tickets ADD COLUMN IF NOT EXISTS granted_amount INT",
]
_columns_ready = False
TICKET_COLUMNS = ("ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at, "
                  "kind, requested_amount, granted_amount")


async def _ensure_columns(session) -> None:
    global _columns_ready
    if not _columns_ready:
        for sql in SUPPORT_COLUMNS:
            await session.execute(text(sql))
        _columns_ready = True


def _ticket(row) -> dict[str, Any]:
    return {
        "ticket_id": str(row.ticket_id),
        "user_id": row.user_id,
        "username": row.username,
        "subject": row.subject,
        "message": row.message,
        "status": row.status,
        "priority": row.priority,
        "admin_notes": row.admin_notes,
        "kind": row.kind or "general",
        "requested_amount": row.requested_amount,
        "granted_amount": row.granted_amount,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


class SupportService:
    @staticmethod
    async def create_ticket(user_id: str, username: str, data: SupportTicketCreate) -> dict[str, Any]:
        async with db.get_session() as session:
            await _ensure_columns(session)
            result = await session.execute(
                text("""
                    INSERT INTO support_tickets (user_id, username, subject, message, priority, status)
                    VALUES (:user_id, :username, :subject, :message, :priority, 'open')
                    RETURNING ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at, kind, requested_amount, granted_amount
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
            return _ticket(ticket)

    @staticmethod
    async def list_tickets(status: Optional[str] = None, priority: Optional[str] = None) -> List[dict[str, Any]]:
        async with db.get_session() as session:
            await _ensure_columns(session)
            query = """
                SELECT ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at, kind, requested_amount, granted_amount
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
                tickets.append(_ticket(row))
            return tickets

    @staticmethod
    async def update_ticket(ticket_id: str, data: SupportTicketUpdate) -> dict[str, Any]:
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ticket ID format")

        async with db.get_session() as session:
            await _ensure_columns(session)
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
                RETURNING ticket_id, user_id, username, subject, message, status, priority, admin_notes, created_at, updated_at, kind, requested_amount, granted_amount
            """
            result = await session.execute(text(sql), params)
            row = result.first()
            if not row:
                raise HTTPException(status_code=404, detail="Ticket not found")
            await session.commit()

            return _ticket(row)

    @staticmethod
    async def give_wildcards(ticket_id: str, amount: int, admin_username: str, note: Optional[str]) -> dict[str, Any]:
        """Answer a wildcard request: give the cards (added to the learner's default) and resolve the ticket."""
        from services.ar_service import ArService
        try:
            tid = uuid.UUID(ticket_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid ticket ID format")
        async with db.get_session() as session:
            await _ensure_columns(session)
            row = (await session.execute(text(
                "SELECT ticket_id, user_id, status, kind FROM support_tickets WHERE ticket_id = :tid"
            ), {"tid": tid})).first()
        if not row:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if row.status == "resolved":
            raise HTTPException(status_code=409, detail="This request is already resolved")
        gift = await ArService.grant_wildcards(row.user_id, amount, admin_username)
        if gift is None:
            raise HTTPException(status_code=404, detail="Learner not found")
        notes = (note or "").strip() or f"Gave you {amount} wildcard{'s' if amount != 1 else ''}. Have fun!"
        async with db.get_session() as session:
            updated = (await session.execute(text(f"""
                UPDATE support_tickets SET status = 'resolved', granted_amount = :amount, admin_notes = :notes, updated_at = now()
                WHERE ticket_id = :tid
                RETURNING {TICKET_COLUMNS}
            """), {"tid": tid, "amount": amount, "notes": notes})).first()
        return {**_ticket(updated), "wallet": {"gift": gift["gift"], "default": gift["default"], "total": gift["total"]}}
