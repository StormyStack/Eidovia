"""
Test fixtures: an ISOLATED, throwaway PostgreSQL cluster.

Created with the local PostgreSQL install's own programs (initdb / pg_ctl) inside
pytest's temp folder, listening only on 127.0.0.1 on a random free port with a random
password. It never connects to the running PostgreSQL service or to the team's dev
database, and it is stopped and deleted when the test session ends.
See scripts/local_pg.py for the shared cluster helpers.
"""

import asyncio
import secrets
import shutil

import pytest

from scripts import local_pg

TEST_DB = "eduarai_gateway_test"


def base_schema_sql() -> str:
    """Kept for callers/tools that import it from here."""
    return local_pg.base_schema_sql()


async def _create_database(cluster: dict, name: str, with_schema: bool = True) -> None:
    await local_pg.create_database(cluster["host"], cluster["port"], cluster["password"], name, with_schema=with_schema)


def database_url(cluster: dict, name: str) -> str:
    return local_pg.database_url(cluster["host"], cluster["port"], cluster["password"], name)


# ============================================================
# FIXTURES
# ============================================================

@pytest.fixture(scope="session")
def pg_cluster(tmp_path_factory):
    """Start a private PostgreSQL cluster for the whole test session."""
    try:
        pg_bin = local_pg.find_pg_bin()
    except local_pg.PostgresNotFound as e:
        pytest.exit(str(e), returncode=3)

    root = tmp_path_factory.mktemp("pgcluster")
    data_dir = root / "data"
    password = secrets.token_urlsafe(24)
    port = local_pg.free_port()

    local_pg.init_cluster(pg_bin, data_dir, password)
    local_pg.start_cluster(pg_bin, data_dir, port, root / "postgres.log")
    try:
        yield {"host": "127.0.0.1", "port": port, "user": "postgres", "password": password}
    finally:
        local_pg.stop_cluster(pg_bin, data_dir)
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="session")
def gateway_env(pg_cluster):
    """Point the gateway's settings at the private cluster (never at a real .env)."""
    from app.config import get_settings

    mp = pytest.MonkeyPatch()
    mp.setenv("GATEWAY_ENV_FILE", "")  # do not load a developer's apps/gateway/.env
    mp.setenv("DATABASE_HOST", pg_cluster["host"])
    mp.setenv("DATABASE_PORT", str(pg_cluster["port"]))
    mp.setenv("POSTGRES_USER", pg_cluster["user"])
    mp.setenv("DB_PASSWORD", pg_cluster["password"])
    mp.setenv("POSTGRES_DB", TEST_DB)
    mp.setenv("JWT_SECRET", secrets.token_urlsafe(48))
    mp.setenv("JWT_EXPIRES_MINUTES", "60")
    mp.setenv("BCRYPT_ROUNDS", "4")  # fast hashing in tests only
    for key in ("SEED_USER_USERNAME", "SEED_USER_EMAIL", "SEED_USER_PASSWORD", "SEED_USER_LANGUAGE"):
        mp.delenv(key, raising=False)
    get_settings.cache_clear()
    yield pg_cluster
    mp.undo()
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def test_db(gateway_env):
    """Main test database: base schema + gateway migrations (no seed)."""
    from scripts import setup_db

    asyncio.run(_create_database(gateway_env, TEST_DB))
    asyncio.run(setup_db.run(seed=False))
    return database_url(gateway_env, TEST_DB)


@pytest.fixture(scope="session")
def client(test_db):
    """TestClient running the real app (lifespan included) against the test database."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def seeded_modules(test_db):
    """Ensure the 4 seed modules exist (idempotent)."""
    from app.db import DatabaseService
    from scripts import setup_db

    async def _seed():
        database = DatabaseService()
        await database.connect(test_db)
        try:
            await setup_db.seed_modules(database)
        finally:
            await database.disconnect()

    asyncio.run(_seed())


@pytest.fixture
def fresh_database(gateway_env):
    """Factory: create an extra, empty-or-base-schema database in the private cluster."""
    def _make(name: str, with_schema: bool = True) -> str:
        asyncio.run(_create_database(gateway_env, name, with_schema))
        return database_url(gateway_env, name)
    return _make
