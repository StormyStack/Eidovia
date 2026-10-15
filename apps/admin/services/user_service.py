import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any
from sqlalchemy import text
from fastapi import HTTPException
from db import db
from redis_client import get_redis
from security import hash_password
from schemas import AdminUserCreate, AdminUserUpdate, AdminPasswordReset
from services import admin_audit

logger = logging.getLogger(__name__)


class UserService:
    @staticmethod
    async def list_users(q: Optional[str] = None, limit: int = 100, offset: int = 0) -> List[dict[str, Any]]:
        async with db.get_session() as session:
            query = """
                SELECT user_id, username, email, detail_level, language, is_admin, created_at
                FROM users
            """
            params: dict[str, Any] = {"limit": limit, "offset": offset}
            if q:
                query += " WHERE lower(username) LIKE :q OR lower(email) LIKE :q"
                params["q"] = f"%{q.lower().strip()}%"
            query += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"

            result = await session.execute(text(query), params)
            users = []
            for row in result.all():
                users.append({
                    "user_id": str(row.user_id),
                    "username": row.username,
                    "email": row.email,
                    "detail_level": row.detail_level,
                    "language": row.language,
                    "is_admin": bool(row.is_admin),
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                })
            return users

    @staticmethod
    async def get_user(user_id: str) -> dict[str, Any]:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        async with db.get_session() as session:
            result = await session.execute(
                text("""
                    SELECT user_id, username, email, detail_level, language, is_admin, created_at
                    FROM users
                    WHERE user_id = :uid
                """),
                {"uid": uid}
            )
            row = result.first()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")

            # Check recent activity summary
            session_count = await session.execute(
                text("SELECT count(*) as c FROM sessions WHERE user_id = :uid"),
                {"uid": uid}
            )
            s_row = session_count.first()

            return {
                "user_id": str(row.user_id),
                "username": row.username,
                "email": row.email,
                "detail_level": row.detail_level,
                "language": row.language,
                "is_admin": bool(row.is_admin),
                "total_sessions": s_row.c if s_row else 0,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    @staticmethod
    async def create_user(data: AdminUserCreate, admin: Any = None) -> dict[str, Any]:
        async with db.get_session() as session:
            existing = await session.execute(
                text("SELECT user_id FROM users WHERE lower(username) = lower(:u) OR lower(email) = lower(:e)"),
                {"u": data.username, "e": data.email},
            )
            if existing.first():
                raise HTTPException(status_code=409, detail="Username or email already taken")

            pwd_hash = await hash_password(data.password)
            res = await session.execute(
                text("""
                    INSERT INTO users (username, email, password_hash, detail_level, language, is_admin)
                    VALUES (:username, :email, :password_hash, :detail_level, :language, :is_admin)
                    RETURNING user_id, created_at
                """),
                {
                    "username": data.username,
                    "email": data.email,
                    "password_hash": pwd_hash,
                    "detail_level": data.detail_level,
                    "language": data.language,
                    "is_admin": data.is_admin,
                },
            )
            created = res.first()
            await admin_audit.record(session, admin, "admin_created" if data.is_admin else "user_created",
                                     str(created.user_id), {"username": data.username, "email": data.email,
                                                            "is_admin": data.is_admin, "level": data.detail_level})
            await session.commit()
            if not data.is_admin:
                await admin_audit.user_event("account_updated_by_admin", str(created.user_id), data.username, {
                    "by": admin.username if admin else None, "created": True})
            return {
                "user_id": str(created.user_id),
                "username": data.username,
                "email": data.email,
                "is_admin": data.is_admin,
                "detail_level": data.detail_level,
                "language": data.language,
                "created_at": created.created_at.isoformat() if created.created_at else None,
            }

    @staticmethod
    async def update_user(user_id: str, data: AdminUserUpdate, current_admin_id: str, admin: Any = None) -> dict[str, Any]:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        async with db.get_session() as session:
            old = (await session.execute(
                text("SELECT username, email, detail_level, language, COALESCE(is_admin, FALSE) AS is_admin "
                     "FROM users WHERE user_id = :uid FOR UPDATE"),
                {"uid": uid},
            )).first()
            if not old:
                raise HTTPException(status_code=404, detail="User not found")

            updates = []
            params: dict[str, Any] = {"uid": uid}

            if data.username is not None:
                check = await session.execute(
                    text("SELECT user_id FROM users WHERE lower(username) = lower(:u) AND user_id != :uid"),
                    {"u": data.username, "uid": uid},
                )
                if check.first():
                    raise HTTPException(status_code=409, detail="Username already in use")
                updates.append("username = :username")
                params["username"] = data.username

            if data.email is not None:
                check = await session.execute(
                    text("SELECT user_id FROM users WHERE lower(email) = lower(:e) AND user_id != :uid"),
                    {"e": data.email, "uid": uid},
                )
                if check.first():
                    raise HTTPException(status_code=409, detail="Email already in use")
                updates.append("email = :email")
                params["email"] = data.email

            if data.detail_level is not None:
                updates.append("detail_level = :detail_level")
                params["detail_level"] = data.detail_level

            if data.language is not None:
                updates.append("language = :language")
                params["language"] = data.language

            if data.is_admin is not None:
                if not data.is_admin and current_admin_id == user_id:
                    raise HTTPException(status_code=400, detail="Cannot revoke your own admin rights")
                if not data.is_admin and old.is_admin and await _admin_count(session) <= 1:
                    raise HTTPException(status_code=400, detail="Cannot remove the last administrator")
                updates.append("is_admin = :is_admin")
                params["is_admin"] = data.is_admin

            if not updates:
                raise HTTPException(status_code=400, detail="No valid update fields specified")

            sql = f"""
                UPDATE users SET {', '.join(updates)}
                WHERE user_id = :uid
                RETURNING user_id, username, email, detail_level, language, is_admin, created_at
            """
            res = await session.execute(text(sql), params)
            updated = res.first()
            changes = {f: {"from": getattr(old, f), "to": getattr(updated, f)}
                       for f in ("username", "email", "detail_level", "language", "is_admin")
                       if (bool(getattr(old, f)) if f == "is_admin" else getattr(old, f))
                       != (bool(getattr(updated, f)) if f == "is_admin" else getattr(updated, f))}
            if changes:
                role = changes.get("is_admin")
                action = ("admin_role_granted" if role and role["to"] else "admin_role_revoked" if role else "user_updated")
                await admin_audit.record(session, admin, action, str(uid), {"changes": changes})
            await session.commit()
            if changes:
                await admin_audit.user_event("account_updated_by_admin", str(uid), updated.username, {
                    "by": admin.username if admin else None, "changes": changes})

            return {
                "user_id": str(updated.user_id),
                "username": updated.username,
                "email": updated.email,
                "detail_level": updated.detail_level,
                "language": updated.language,
                "is_admin": bool(updated.is_admin),
                "created_at": updated.created_at.isoformat() if updated.created_at else None,
            }

    @staticmethod
    async def reset_password(user_id: str, data: AdminPasswordReset, admin_username: str = "admin",
                             admin: Any = None) -> dict[str, Any]:
        """Set a new password. Also resolves the user's open "forgot password" support requests."""
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        if len(data.new_password) < 8:
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

        async with db.get_session() as session:
            existing = await session.execute(
                text("SELECT username FROM users WHERE user_id = :uid"),
                {"uid": uid},
            )
            row = existing.first()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")

            pwd_hash = await hash_password(data.new_password)
            await session.execute(
                text("UPDATE users SET password_hash = :pwd_hash WHERE user_id = :uid"),
                {"pwd_hash": pwd_hash, "uid": uid},
            )
            resolved = 0
            try:
                resolved = len((await session.execute(text("""
                    UPDATE support_tickets SET status = 'resolved', updated_at = now(),
                        admin_notes = COALESCE(NULLIF(admin_notes, '') || ' ', '') || :note
                    WHERE user_id = :u AND kind = 'password_reset' AND status <> 'resolved'
                    RETURNING ticket_id
                """), {"u": str(uid), "note": f"Password reset by {admin_username}."})).all())
            except Exception:
                pass    # support_tickets.kind not there yet (migration 008)
            await admin_audit.record(session, admin, "password_reset", str(uid), {"requests_resolved": resolved})
            await session.commit()

        try:
            r = await get_redis()
            await r.rpush("raw_audit_logs", json.dumps({
                "action": "password_reset_by_admin", "user_id": str(uid), "username": row.username,
                "details": {"by": admin_username, "requests_resolved": resolved},
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            pass
        return {"status": "password_reset_success", "username": row.username, "requests_resolved": resolved}

    @staticmethod
    async def delete_user(user_id: str, current_admin_id: str, admin: Any = None) -> dict[str, str]:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        if current_admin_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

        async with db.get_session() as session:
            existing = await session.execute(
                text("SELECT username, email, COALESCE(is_admin, FALSE) AS is_admin FROM users WHERE user_id = :uid"),
                {"uid": uid},
            )
            row = existing.first()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")
            if row.is_admin and await _admin_count(session) <= 1:
                raise HTTPException(status_code=400, detail="Cannot delete the last administrator")

            # Clean associated records
            try:
                await session.execute(text("DELETE FROM events WHERE user_id = :u_str"), {"u_str": user_id})
                await session.execute(text("DELETE FROM support_tickets WHERE user_id = :u_str"), {"u_str": user_id})
            except Exception:
                pass

            await session.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": uid})
            # the account is gone, the audit record stays (the user's activity log rows in audit_logs stay too)
            await admin_audit.record(session, admin, "admin_deleted" if row.is_admin else "user_deleted", user_id,
                                     {"username": row.username, "email": row.email})
            await session.commit()

        return {"status": "deleted", "username": row.username}


async def _admin_count(session) -> int:
    """Administrator accounts right now (the last one can be neither demoted nor deleted)."""
    row = (await session.execute(text("SELECT count(*) AS n FROM users WHERE is_admin = TRUE"))).first()
    return int(row.n) if row else 0
