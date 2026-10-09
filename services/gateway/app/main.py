"""
Eidovia API Gateway (FastAPI :8000)
Auth + user profile + module catalogue for the mobile app.
Contract: docs/api-auth-home.md

Run (from apps/gateway):
    python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
"""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app import repositories as repo
from app.config import get_settings
from app.db import db
from app.errors import register_error_handlers
from app.routers import auth, chat, modules, users
from app.schemas import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================
# LIFECYCLE
# ============================================================

async def _warn_if_not_migrated() -> None:
    """Registration needs users.email; point the developer at the setup script if it is missing."""
    try:
        async with db.get_session() as session:
            if not await repo.users_email_column_exists(session):
                logger.error(
                    "users.email column missing. Run: python -m scripts.setup_db  (from apps/gateway)"
                )
    except Exception as e:
        logger.warning(f"Could not check migrations: {type(e).__name__}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings()  # fail fast on missing/invalid JWT_SECRET or DB_PASSWORD
    logger.info("Eidovia Gateway starting")
    await db.connect()
    await _warn_if_not_migrated()
    yield
    await db.disconnect()
    logger.info("Gateway stopped")


# ============================================================
# APPLICATION
# ============================================================

app = FastAPI(
    title="Eidovia API Gateway",
    description="Auth, user profile and module catalogue for the Eidovia mobile app.",
    version="0.1.0",
    lifespan=lifespan,
)

register_error_handlers(app)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(modules.router)
app.include_router(chat.router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Liveness check; always 200, reports database reachability."""
    connected = await db.ping()
    return HealthResponse(
        status="ok" if connected else "degraded",
        service="gateway",
        database="connected" if connected else "disconnected",
    )


if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port)
