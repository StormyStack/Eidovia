"""
Auth Routes
POST /api/auth/register  (NEW — needs team agreement)
POST /api/auth/login     (PDF contract, exact)
POST /api/auth/password-reset-request   forgot password: becomes a support ticket; an admin resets it
"""

import logging

from typing import Optional

from fastapi import APIRouter, status, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app import errors
from app import repositories as repo
from app.db import db
from app.schemas import AuthResponse, LoginRequest, ProfileSummary, RegisterRequest
from app.security import burn_password_check, create_access_token, hash_password, verify_password
from app.logger_client import push_log_event
from app.request_log import note
from app.deps import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _auth_response(user_id: str, detail_level: int, language: str) -> AuthResponse:
    return AuthResponse(
        user_id=user_id,
        token=create_access_token(user_id),
        profile=ProfileSummary(detail_level=detail_level, language=language),
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest) -> AuthResponse:
    """Create an account and log in immediately (same response shape as login)."""
    async with db.get_session() as session:
        username_taken, email_taken = await repo.find_user_conflicts(session, body.username, body.email)
    if username_taken:
        raise errors.username_taken()
    if email_taken:
        raise errors.email_taken()

    # Hash outside any DB session: bcrypt takes ~0.25 s and should not hold a connection
    password_hash = await hash_password(body.password)

    try:
        async with db.get_session() as session:
            user = await repo.create_user(session, body.username, body.email, password_hash, body.language)
    except IntegrityError as e:
        # Lost a race with a concurrent sign-up for the same name/email
        constraint = str(e.orig)
        if "uq_users_email_lower" in constraint:
            raise errors.email_taken()
        if "username" in constraint:
            raise errors.username_taken()
        raise

    logger.info(f"User registered: {user['user_id']}")
    await push_log_event("register", str(user["user_id"]), body.username, False, {"email": body.email})
    return _auth_response(user["user_id"], user["detail_level"], user["language"])


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest) -> AuthResponse:
    """Verify username + password and return a JWT (PDF contract)."""
    async with db.get_session() as session:
        user = await repo.get_user_for_login(session, body.username)

    if user is None:
        await burn_password_check(body.password)
        note(detail=f"login failed: unknown user {body.username[:40]}")
        raise errors.invalid_credentials()

    if not await verify_password(body.password, user.password_hash):
        note(user_id=str(user.user_id), username=user.username, detail="login failed: wrong password")
        await push_log_event("login_failed", str(user.user_id), user.username, bool(user.is_admin),
                             {"reason": "wrong password"})
        raise errors.invalid_credentials()

    user_id = str(user.user_id)
    logger.info(f"User logged in: {user_id}")
    await push_log_event("login", user_id, user.username, bool(user.is_admin))
    return _auth_response(user_id, user.detail_level, user.language)


@router.post("/logout")
async def logout(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Log out a user."""
    await push_log_event("logout", current_user.user_id, current_user.username, current_user.is_admin)
    return {"status": "logged_out"}



# ============================================================
# FORGOT PASSWORD → support ticket (kind 'password_reset'); the admin resets it in User Support
# ============================================================

class PasswordResetRequest(BaseModel):
    username_or_email: str = Field(..., min_length=3, max_length=254)
    message: Optional[str] = Field(None, max_length=500)


RESET_RECEIVED = ("Your request was sent to support. An admin will reset your password and "
                  "tell you the new one (for example by email).")


@router.post("/password-reset-request")
async def password_reset_request(body: PasswordResetRequest) -> dict:
    """
    Public (the user cannot log in). The answer is the same whether or not the account exists,
    so nobody can find out which usernames or emails are registered. One open request per user.
    """
    from app.routers.wildcards import _setup as ensure_support_columns   # support_tickets.kind (migration 008)

    key = body.username_or_email.strip().lower()
    async with db.get_session() as session:
        await ensure_support_columns(session)
        user = (await session.execute(text(
            "SELECT user_id, username, email FROM users WHERE lower(username) = :k OR lower(email) = :k LIMIT 1"
        ), {"k": key})).first()
        if user is None:
            note(detail="password reset requested for an unknown user")
            return {"status": "received", "message": RESET_RECEIVED}
        uid = str(user.user_id)
        note(user_id=uid, username=user.username)
        open_one = (await session.execute(text(
            "SELECT 1 FROM support_tickets WHERE user_id = :u AND kind = 'password_reset' AND status <> 'resolved' LIMIT 1"
        ), {"u": uid})).first()
        if open_one:
            return {"status": "received", "message": RESET_RECEIVED}
        message = (body.message or "").strip() or "I forgot my password. Please reset it."
        row = (await session.execute(text("""
            INSERT INTO support_tickets (user_id, username, subject, message, priority, status, kind)
            VALUES (:u, :name, 'Password reset request', :message, 'high', 'open', 'password_reset')
            RETURNING ticket_id
        """), {"u": uid, "name": user.username, "message": f"{message}\n\nContact email: {user.email or 'none'}"})).first()
    await push_log_event("password_reset_requested", uid, user.username, False, {"ticket_id": str(row.ticket_id)})
    return {"status": "received", "message": RESET_RECEIVED}
