import logging
import contextlib
from typing import AsyncGenerator
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from db import db
from security import verify_password, create_access_token
from sqlalchemy import text
from __init__ import admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("eidovia_admin")


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("Eidovia Enterprise Admin Suite starting up...")
    await db.connect()
    yield
    logger.info("Eidovia Enterprise Admin Suite shutting down...")
    await db.disconnect()


app = FastAPI(
    title="Eidovia Admin Center & Operations Suite",
    description="Enterprise administrative portal for user support, system maintenance, and learning telemetry.",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount all modular admin capabilities
app.include_router(admin_router)


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
async def admin_login(body: LoginRequest) -> dict:
    """Direct login endpoint for administrative operations suite."""
    async with db.get_session() as session:
        result = await session.execute(
            text("SELECT user_id, username, password_hash, is_admin FROM users WHERE lower(username) = lower(:u)"),
            {"u": body.username}
        )
        user = result.first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid administrative credentials")

    if not await verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid administrative credentials")

    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Forbidden: Account does not possess administrator role")

    token = create_access_token(str(user.user_id))
    return {"token": token, "user_id": str(user.user_id), "username": user.username}


@app.get("/health", tags=["health"])
async def health() -> dict:
    """Service liveness probe."""
    db_ok = await db.ping()
    return {"status": "ok" if db_ok else "degraded", "service": "eidovia_admin", "database_connected": db_ok}


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root to admin dashboard."""
    return RedirectResponse(url="/admin/dashboard")
