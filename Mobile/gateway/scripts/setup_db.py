"""
Gateway Database Setup
1. Applies the additive migrations in apps/gateway/migrations/ (in name order).
2. Seeds the 4 Unity AR modules and one test user.

Usage (from apps/gateway, with the venv active):
    python -m scripts.setup_db            # migrations + seed
    python -m scripts.setup_db --no-seed  # migrations only

Safety:
- Requires the base schema (01_schema.sql) to exist already; it never creates or drops base tables.
- Migrations use IF NOT EXISTS; seeds skip rows that already exist (nothing is overwritten,
  an existing user's password is never changed).
- The test user's password comes from SEED_USER_PASSWORD only; it is never printed.
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import asyncpg
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import StatementError

from app import repositories as repo
from app.config import GATEWAY_ROOT, get_env, get_settings
from app.db import DatabaseService
from app.schemas import RegisterRequest
from app.security import hash_password

logger = logging.getLogger("setup_db")

MIGRATIONS_DIR = GATEWAY_ROOT / "migrations"
PLACEHOLDER_CDN = "https://cdn.example.com/bundles"

# Scene names are the Unity Developer's actual scenes (Unity Dev Reference, apps/unity/Assets/Scenes).
# cdn_bundle_url values are placeholders until the SE provides CloudFront URLs.
SEED_MODULES = [
    {
        "module_id": "cell-explore",
        "name": "Explore the Cell",
        "scene_name": "GameScene_CellExplore",
        "difficulty": 1,
        "description": "Tap organelles in 3D to discover what each part of the cell does.",
    },
    {
        "module_id": "cell-puzzle",
        "name": "Cell Puzzle",
        "scene_name": "GameScene_CellPuzzle",
        "difficulty": 2,
        "description": "Drag and drop organelles into their correct place inside the cell.",
    },
    {
        "module_id": "cell-process",
        "name": "Cell Processes",
        "scene_name": "GameScene_CellProcess",
        "difficulty": 3,
        "description": "Follow a step-by-step 3D animation of a cell process such as ATP synthesis.",
    },
    {
        "module_id": "cell-quiz",
        "name": "Cell Quiz",
        "scene_name": "GameScene_CellQuiz",
        "difficulty": 3,
        "description": "Test what you have learned in an interactive 3D quiz.",
    },
]


class BaseSchemaMissing(RuntimeError):
    """01_schema.sql has not been applied to this database."""


@dataclass
class SetupReport:
    migrations_applied: list
    modules_created: int
    modules_skipped: int
    user_status: str  # "created" | "exists" | "skipped (no SEED_USER_PASSWORD)" | "skipped (seed disabled)"


def _asyncpg_dsn(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


# ============================================================
# STEPS
# ============================================================

async def _check_base_schema(database: DatabaseService) -> None:
    async with database.get_session() as session:
        result = await session.execute(
            text("SELECT to_regclass('users') IS NOT NULL AS users, to_regclass('modules') IS NOT NULL AS modules")
        )
        row = result.one()
    if not (row.users and row.modules):
        raise BaseSchemaMissing(
            "Tables 'users'/'modules' not found. Start the team database first "
            "(docker compose up -d applies 01_schema.sql), then re-run this script."
        )


async def apply_migrations(database_url: str) -> list:
    """Run every migrations/*.sql file in its own transaction (files are idempotent)."""
    applied = []
    conn = await asyncpg.connect(_asyncpg_dsn(database_url), timeout=10)
    try:
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
            applied.append(path.name)
    finally:
        await conn.close()
    return applied


async def seed_modules(database: DatabaseService) -> tuple[int, int]:
    """Insert missing seed modules; existing module_ids are left untouched. Returns (created, skipped)."""
    created = 0
    async with database.get_session() as session:
        for module in SEED_MODULES:
            config = {"display": {"description": module["description"]}}
            result = await session.execute(
                text("""
                    INSERT INTO modules (module_id, name, scene_name, cdn_bundle_url, difficulty, config)
                    VALUES (:module_id, :name, :scene_name, :cdn_bundle_url, :difficulty,
                            CAST(CAST(:config AS TEXT) AS JSONB))
                    ON CONFLICT (module_id) DO NOTHING
                    RETURNING module_id
                """),
                {
                    "module_id": module["module_id"],
                    "name": module["name"],
                    "scene_name": module["scene_name"],
                    "cdn_bundle_url": f"{PLACEHOLDER_CDN}/{module['module_id']}",
                    "difficulty": module["difficulty"],
                    "config": json.dumps(config),
                },
            )
            if result.first() is not None:
                created += 1
    return created, len(SEED_MODULES) - created


async def seed_test_user(database: DatabaseService) -> str:
    """Create the test user from SEED_USER_* env vars unless it already exists."""
    password = get_env("SEED_USER_PASSWORD")
    if not password:
        return "skipped (no SEED_USER_PASSWORD)"

    try:
        user = RegisterRequest(
            username=get_env("SEED_USER_USERNAME", "demo_student"),
            email=get_env("SEED_USER_EMAIL", "demo.student@example.com"),
            password=password,
            language=get_env("SEED_USER_LANGUAGE", "en"),
        )
    except ValidationError as e:
        problems = "; ".join(f"{err['loc'][0]}: {str(err['msg']).removeprefix('Value error, ')}" for err in e.errors())
        raise ValueError(f"Invalid SEED_USER_* settings: {problems}") from None

    async with database.get_session() as session:
        username_taken, email_taken = await repo.find_user_conflicts(session, user.username, user.email)
    if username_taken or email_taken:
        return "exists"

    password_hash = await hash_password(user.password)
    async with database.get_session() as session:
        await repo.create_user(session, user.username, user.email, password_hash, user.language)
    return "created"


async def run(seed: bool = True, database_url: Optional[str] = None) -> SetupReport:
    """Full setup. database_url overrides the configured database (used by tests)."""
    url = database_url or get_settings().database_url
    database = DatabaseService()
    await database.connect(url)
    try:
        await _check_base_schema(database)
        applied = await apply_migrations(url)
        if not seed:
            return SetupReport(applied, 0, 0, "skipped (seed disabled)")
        created, skipped = await seed_modules(database)
        user_status = await seed_test_user(database)
        return SetupReport(applied, created, skipped, user_status)
    finally:
        await database.disconnect()


# ============================================================
# CLI
# ============================================================

def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description="Apply gateway migrations and seed demo data.")
    parser.add_argument("--no-seed", action="store_true", help="apply migrations only")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s | %(name)s | %(message)s")
    try:
        report = asyncio.run(run(seed=not args.no_seed))
    except BaseSchemaMissing as e:
        print(f"[ERROR] {e}")
        return 2
    except Exception as e:
        # SQLAlchemy errors embed bound parameters (e.g. a password hash); print only the driver error
        cause = e.orig if isinstance(e, StatementError) and e.orig is not None else e
        print(f"[ERROR] Setup failed: {type(cause).__name__}: {cause}")
        return 1

    print("[OK] Gateway database setup complete")
    print(f"   Migrations applied : {', '.join(report.migrations_applied) or 'none found'}")
    if not args.no_seed:
        print(f"   Modules            : {report.modules_created} created, {report.modules_skipped} already present")
        print(f"   Test user          : {report.user_status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
