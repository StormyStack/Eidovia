"""scripts/setup_db.py — migration + seed, idempotency, and safety."""

import asyncio
import secrets

import pytest

from scripts import setup_db
from tests.utils import sql

SEED_PASSWORD = "Seed-User-Pass-7"


def _db_name() -> str:
    return f"setup_{secrets.token_hex(4)}"


@pytest.fixture
def seed_env(monkeypatch):
    monkeypatch.setenv("SEED_USER_USERNAME", "demo_student")
    monkeypatch.setenv("SEED_USER_EMAIL", "demo.student@example.com")
    monkeypatch.setenv("SEED_USER_PASSWORD", SEED_PASSWORD)


def test_fresh_database_gets_migration_modules_and_user(fresh_database, seed_env):
    name = _db_name()
    url = fresh_database(name)

    report = asyncio.run(setup_db.run(seed=True, database_url=url))

    assert report.migrations_applied == ["001_add_user_email.sql"]
    assert (report.modules_created, report.modules_skipped) == (4, 0)
    assert report.user_status == "created"

    assert sql("SELECT count(*) FROM information_schema.columns "
               "WHERE table_name = 'users' AND column_name = 'email'", database=name, fetch="val") == 1
    assert sql("SELECT count(*) FROM pg_indexes WHERE indexname = 'uq_users_email_lower'",
               database=name, fetch="val") == 1

    modules = sql("SELECT module_id, scene_name, cdn_bundle_url FROM modules ORDER BY module_id",
                  database=name, fetch="all")
    assert {m["module_id"]: m["scene_name"] for m in modules} == {
        "cell-explore": "GameScene_CellExplore",
        "cell-puzzle": "GameScene_CellPuzzle",
        "cell-process": "GameScene_CellProcess",
        "cell-quiz": "GameScene_CellQuiz",
    }
    assert all(m["cdn_bundle_url"].startswith("https://cdn.example.com/bundles/") for m in modules)

    user = sql("SELECT email, password_hash FROM users WHERE username = 'demo_student'", database=name, fetch="row")
    assert user["email"] == "demo.student@example.com"
    assert user["password_hash"].startswith("$2b$")
    assert SEED_PASSWORD not in user["password_hash"]


def test_setup_is_idempotent_and_never_overwrites(fresh_database, seed_env, monkeypatch):
    name = _db_name()
    url = fresh_database(name)
    asyncio.run(setup_db.run(seed=True, database_url=url))
    hash_before = sql("SELECT password_hash FROM users WHERE username = 'demo_student'", database=name, fetch="val")
    sql("UPDATE modules SET name = 'Team Edited Name' WHERE module_id = 'cell-quiz'", database=name)

    monkeypatch.setenv("SEED_USER_PASSWORD", "A-Different-Pass-8")
    report = asyncio.run(setup_db.run(seed=True, database_url=url))

    assert (report.modules_created, report.modules_skipped) == (0, 4)
    assert report.user_status == "exists"
    assert sql("SELECT count(*) FROM modules", database=name, fetch="val") == 4
    assert sql("SELECT count(*) FROM users", database=name, fetch="val") == 1
    assert sql("SELECT password_hash FROM users WHERE username = 'demo_student'", database=name, fetch="val") == hash_before
    assert sql("SELECT name FROM modules WHERE module_id = 'cell-quiz'", database=name, fetch="val") == "Team Edited Name"


def test_existing_users_without_email_stay_valid(fresh_database):
    name = _db_name()
    url = fresh_database(name)
    sql("INSERT INTO users (username, password_hash) VALUES ('old_a', 'x'), ('old_b', 'y')", database=name)

    asyncio.run(setup_db.run(seed=False, database_url=url))

    assert sql("SELECT count(*) FROM users WHERE email IS NULL", database=name, fetch="val") == 2
    sql("INSERT INTO users (username, password_hash) VALUES ('old_c', 'z')", database=name)  # multiple NULLs ok


def test_user_seed_skipped_without_password(fresh_database, monkeypatch):
    monkeypatch.delenv("SEED_USER_PASSWORD", raising=False)
    name = _db_name()
    report = asyncio.run(setup_db.run(seed=True, database_url=fresh_database(name)))
    assert report.user_status == "skipped (no SEED_USER_PASSWORD)"
    assert report.modules_created == 4
    assert sql("SELECT count(*) FROM users", database=name, fetch="val") == 0


def test_invalid_seed_password_fails_without_revealing_it(fresh_database, monkeypatch):
    monkeypatch.setenv("SEED_USER_PASSWORD", "tiny")
    with pytest.raises(ValueError) as excinfo:
        asyncio.run(setup_db.run(seed=True, database_url=fresh_database(_db_name())))
    assert "at least 8" in str(excinfo.value)
    assert "tiny" not in str(excinfo.value)


def test_refuses_database_without_base_schema(fresh_database):
    url = fresh_database(_db_name(), with_schema=False)
    with pytest.raises(setup_db.BaseSchemaMissing):
        asyncio.run(setup_db.run(seed=True, database_url=url))


def test_cli_migrations_only_exits_zero(test_db, capsys):
    assert setup_db.main(["--no-seed"]) == 0
    assert "001_add_user_email.sql" in capsys.readouterr().out


def test_seeded_user_can_log_in_through_the_api(client, test_db, seed_env, monkeypatch):
    monkeypatch.setenv("SEED_USER_USERNAME", "seed_login_check")
    monkeypatch.setenv("SEED_USER_EMAIL", "seed.login.check@example.com")
    asyncio.run(setup_db.run(seed=True, database_url=test_db))

    response = client.post("/api/auth/login", json={"username": "seed_login_check", "password": SEED_PASSWORD})
    assert response.status_code == 200
