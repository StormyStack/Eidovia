import logging
import uuid
from typing import List, Optional, Any
from sqlalchemy import text
from fastapi import HTTPException
from db import db
from security import hash_password
from schemas import AdminUserCreate, AdminUserUpdate, AdminPasswordReset

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
    async def create_user(data: AdminUserCreate) -> dict[str, Any]:
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
            await session.commit()
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
    async def update_user(user_id: str, data: AdminUserUpdate, current_admin_id: str) -> dict[str, Any]:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        async with db.get_session() as session:
            existing = await session.execute(
                text("SELECT user_id FROM users WHERE user_id = :uid"),
                {"uid": uid},
            )
            if not existing.first():
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
            await session.commit()

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
    async def reset_password(user_id: str, data: AdminPasswordReset) -> dict[str, str]:
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
            await session.commit()

        return {"status": "password_reset_success", "username": row.username}

    @staticmethod
    async def delete_user(user_id: str, current_admin_id: str) -> dict[str, str]:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid user ID format")

        if current_admin_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete your own admin account")

        async with db.get_session() as session:
            existing = await session.execute(
                text("SELECT username FROM users WHERE user_id = :uid"),
                {"uid": uid},
            )
            row = existing.first()
            if not row:
                raise HTTPException(status_code=404, detail="User not found")

            # Clean associated records
            try:
                await session.execute(text("DELETE FROM events WHERE user_id = :u_str"), {"u_str": user_id})
                await session.execute(text("DELETE FROM support_tickets WHERE user_id = :u_str"), {"u_str": user_id})
            except Exception:
                pass

            await session.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": uid})
            await session.commit()

        return {"status": "deleted", "username": row.username}
