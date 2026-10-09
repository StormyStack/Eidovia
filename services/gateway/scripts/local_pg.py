"""
Private local PostgreSQL clusters built with the locally installed PostgreSQL programs
(initdb / pg_ctl). Used by the test suite (throwaway cluster) and by scripts/dev_db.py
(persistent dev cluster in apps/gateway/.devdb).

These clusters listen on 127.0.0.1 only, on their own port and data folder: they never
touch the machine's PostgreSQL service or any team database.

The base schema is the team's 01_schema.sql minus the pgvector statements (pgvector is
not part of a standard local PostgreSQL install; the gateway does not use document_chunks).
"""

import glob
import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Optional

import asyncpg

GATEWAY_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = GATEWAY_DIR.parents[1]
DEFAULT_SCHEMA_FILE = REPO_ROOT / "01_schema.sql"


class PostgresNotFound(RuntimeError):
    """initdb/pg_ctl could not be located."""


def _exe(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def find_pg_bin() -> Path:
    """PG_BIN env var, then pg_ctl on PATH, then the newest C:\\Program Files\\PostgreSQL\\<n>\\bin."""
    candidates = []
    if os.getenv("PG_BIN"):
        candidates.append(Path(os.environ["PG_BIN"]))
    on_path = shutil.which("pg_ctl")
    if on_path:
        candidates.append(Path(on_path).parent)
    installed = [Path(p) for p in glob.glob(r"C:\Program Files\PostgreSQL\*\bin")]
    installed.sort(key=lambda p: int(p.parent.name) if p.parent.name.isdigit() else 0, reverse=True)
    candidates.extend(installed)

    for candidate in candidates:
        if (candidate / _exe("initdb")).exists() and (candidate / _exe("pg_ctl")).exists():
            return candidate
    raise PostgresNotFound("PostgreSQL programs not found. Set PG_BIN to the folder containing initdb and pg_ctl.")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def schema_file() -> Path:
    """
    The team's 01_schema.sql: SCHEMA_FILE if set, otherwise the nearest 01_schema.sql in a
    parent folder of apps/gateway (works whether apps/ sits at the repo root or one level deeper).
    """
    if os.getenv("SCHEMA_FILE"):
        path = Path(os.environ["SCHEMA_FILE"])
        if path.is_file():
            return path
        raise FileNotFoundError(f"SCHEMA_FILE points to a missing file: {path}")

    for folder in GATEWAY_DIR.parents:
        candidate = folder / DEFAULT_SCHEMA_FILE.name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "Base schema 01_schema.sql not found in any parent folder of apps/gateway. The gateway needs "
        "the team's 01_schema.sql (data-layer branch) at the repository root, or set SCHEMA_FILE."
    )


def base_schema_sql() -> str:
    """01_schema.sql without the pgvector-dependent statements."""
    statements = [part.strip() for part in schema_file().read_text(encoding="utf-8").split(";")]
    kept = [stmt for stmt in statements if stmt and "vector" not in stmt.lower()]
    return ";\n\n".join(kept) + ";"


def init_cluster(pg_bin: Path, data_dir: Path, password: str) -> None:
    """initdb with scram-sha-256 auth; the password file is deleted immediately."""
    data_dir.parent.mkdir(parents=True, exist_ok=True)
    pw_file = data_dir.parent / "initdb-pw.tmp"
    pw_file.write_text(password, encoding="utf-8")
    try:
        subprocess.run(
            [str(pg_bin / _exe("initdb")), "-D", str(data_dir), "-U", "postgres",
             "-A", "scram-sha-256", f"--pwfile={pw_file}", "-E", "UTF8", "--no-locale"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    finally:
        pw_file.unlink(missing_ok=True)


def start_cluster(pg_bin: Path, data_dir: Path, port: int, log_file: Path) -> None:
    # No pipes: on Windows the server inherits them and pg_ctl would never return
    subprocess.run(
        [str(pg_bin / _exe("pg_ctl")), "-D", str(data_dir),
         "-o", f"-p {port} -c listen_addresses=127.0.0.1",
         "-l", str(log_file), "-w", "-t", "60", "start"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def stop_cluster(pg_bin: Path, data_dir: Path) -> None:
    subprocess.run(
        [str(pg_bin / _exe("pg_ctl")), "-D", str(data_dir), "-m", "fast", "-w", "stop"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def cluster_running(pg_bin: Path, data_dir: Path) -> bool:
    result = subprocess.run(
        [str(pg_bin / _exe("pg_ctl")), "-D", str(data_dir), "status"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


async def create_database(host: str, port: int, password: str, name: str,
                          with_schema: bool = True, replace: bool = True) -> None:
    """Create a database in a private cluster (optionally dropping an existing one first)."""
    admin = await asyncpg.connect(host=host, port=port, user="postgres", password=password, database="postgres")
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", name)
        if exists and replace:
            await admin.execute(f'DROP DATABASE "{name}"')
            exists = None
        if not exists:
            await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    if with_schema:
        conn = await asyncpg.connect(host=host, port=port, user="postgres", password=password, database=name)
        try:
            has_users: Optional[str] = await conn.fetchval("SELECT to_regclass('users')::text")
            if not has_users:
                await conn.execute(base_schema_sql())
        finally:
            await conn.close()


def database_url(host: str, port: int, password: str, name: str) -> str:
    return f"postgresql+asyncpg://postgres:{password}@{host}:{port}/{name}"
