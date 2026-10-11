import logging
import json
import asyncio
from typing import List, Any
from sqlalchemy import text
from fastapi import WebSocket, WebSocketDisconnect
from db import db
from redis_client import get_redis
from security import decode_access_token

logger = logging.getLogger(__name__)


class AuditService:
    @staticmethod
    async def get_logs(limit: int = 100) -> List[dict[str, Any]]:
        async with db.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT id, user_id, username, action, details, created_at
                    FROM audit_logs
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                {"limit": limit}
            )
            logs = []
            for row in result.all():
                logs.append({
                    "id": str(row.id),
                    "user_id": row.user_id,
                    "username": row.username or "unknown",
                    "action": row.action,
                    "details": row.details,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            return logs

    @staticmethod
    async def get_platform_stats() -> dict[str, Any]:
        async with db.get_session() as session:
            u_res = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total_users,
                        COUNT(*) FILTER (WHERE is_admin = TRUE) as admin_users,
                        COUNT(*) FILTER (WHERE is_admin = FALSE OR is_admin IS NULL) as student_users
                    FROM users
                """)
            )
            u_row = u_res.first()

            l_res = await session.execute(
                text("""
                    SELECT 
                        COUNT(*) as total_logs,
                        COUNT(*) FILTER (WHERE action = 'message_sent') as chat_messages
                    FROM audit_logs
                """)
            )
            l_row = l_res.first()

            t_res = await session.execute(
                text("SELECT COUNT(*) as open_tickets FROM support_tickets WHERE status = 'open'")
            )
            t_row = t_res.first()

            return {
                "total_users": u_row.total_users if u_row else 0,
                "admin_users": u_row.admin_users if u_row else 0,
                "student_users": u_row.student_users if u_row else 0,
                "total_logs": l_row.total_logs if l_row else 0,
                "chat_messages": l_row.chat_messages if l_row else 0,
                "open_tickets": t_row.open_tickets if t_row else 0,
            }

    @staticmethod
    async def handle_websocket_logs(websocket: WebSocket, token: str) -> None:
        await websocket.accept()
        try:
            user_id = decode_access_token(token)
            async with db.get_session() as session:
                res = await session.execute(
                    text("SELECT is_admin FROM users WHERE user_id = :uid"),
                    {"uid": user_id}
                )
                row = res.first()
                if not row or not row.is_admin:
                    await websocket.close(code=1008)
                    return
        except Exception:
            await websocket.close(code=1008)
            return

        r = await get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe("realtime_logs")

        async def reader():
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass

        async def writer():
            try:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message:
                        await websocket.send_text(message["data"])
            except Exception:
                pass

        read_task = asyncio.create_task(reader())
        write_task = asyncio.create_task(writer())

        done, pending = await asyncio.wait(
            [read_task, write_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        await pubsub.unsubscribe("realtime_logs")
        await pubsub.close()
