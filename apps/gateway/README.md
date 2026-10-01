# EduAR-AI API Gateway (`apps/gateway`)

FastAPI service on **port 8000** providing auth, user profile and the module catalogue for the
mobile app. The contract is in [`docs/api-auth-home.md`](../../docs/api-auth-home.md).

> **Ownership:** the Gateway belongs to the System Engineer (SE) per the architecture.
> This is additive code written by the RN developer to unblock Sprint 1. It does not modify
> `01_schema.sql`, `docker-compose.yml` or the AI service. Items needing SE agreement are listed at
> the end of the contract.

## Endpoints

| Method | Path | Auth |
|---|---|---|
| POST | `/api/auth/register` | — |
| POST | `/api/auth/login` | — |
| GET | `/api/users/{user_id}/profile` | Bearer |
| GET | `/api/modules` | Bearer |
| GET | `/api/modules/{module_id}/config` | Bearer |
| GET | `/health` | — |

Interactive docs: `http://127.0.0.1:8000/docs` while the server runs.

## Layout

```
apps/gateway/
├── app/
│   ├── main.py          FastAPI app, lifespan, /health
│   ├── config.py        settings from env (+ apps/gateway/.env)
│   ├── db.py            async engine + get_session() (same pattern as root database_service.py)
│   ├── security.py      bcrypt hashing, JWT issue/verify
│   ├── deps.py          get_current_user (Bearer token)
│   ├── errors.py        contract error format { detail: { code, message, fields? } }
│   ├── schemas.py       request validation + response shapes
│   ├── repositories.py  all SQL (bound parameters only)
│   └── routers/         auth.py, users.py, modules.py
├── migrations/001_add_user_email.sql   additive (needs SE agreement)
├── scripts/
│   ├── setup_db.py                     migrations + seed (4 Unity modules, 1 test user)
│   ├── dev_db.py                       local dev PostgreSQL for running without Docker
│   └── local_pg.py                     private-cluster helpers shared by tests and dev_db
└── tests/                              pytest (75 tests); runs on a private throwaway PostgreSQL
```

## Requirements

- Python **3.11**. Use the repo venv at `<repo>/.venv`, created with `python -m venv .venv` in the repo root.
- The team's **`01_schema.sql` at the repository root**, from the `data-layer` branch. The gateway
  builds on its `users` and `modules` tables, and the tests and dev DB load it. If your checkout
  keeps it elsewhere, set `SCHEMA_FILE`.
- One database: the team Docker stack (standard), or the local dev DB below.

## Option A: team database (Docker, standard)

Prerequisite: the team database is running (`docker compose up -d` in the repo root applies `01_schema.sql`).

```powershell
cd F:\Thesis\Thesis-final\apps\gateway
..\..\.venv\Scripts\Activate.ps1
pip install -r requirements.txt                # once

copy .env.example .env                         # then fill DB_PASSWORD, JWT_SECRET, SEED_USER_PASSWORD
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste the output as JWT_SECRET

python -m scripts.setup_db                     # migration + seed; safe to re-run
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

curl http://127.0.0.1:8000/health              # {"status":"ok",...,"database":"connected"}
```

**Port clash:** this PC already runs a native PostgreSQL on 5432. Two fixes:
- Stop that service.
- Or publish Docker's Postgres on another port: set `POSTGRES_PORT=5433` in the root `.env` and
  `DATABASE_PORT=5433` in `apps/gateway/.env`.

## Option B: local dev database (no Docker)

`scripts/dev_db.py` runs a **private** PostgreSQL with your locally installed PostgreSQL programs
(auto-detected under `C:\Program Files\PostgreSQL\<n>\bin`, or set `PG_BIN`):
- data in `apps/gateway/.devdb/` (gitignored), on `127.0.0.1:55432`;
- base schema = `01_schema.sql` minus pgvector, then the gateway migration, and the 4 modules seeded;
- it writes `.devdb/gateway.env` with a generated DB password and JWT secret (local only).

It's for gateway and mobile work only: no pgvector and no Redis, so the AI service needs Docker.

```powershell
cd F:\Thesis\Thesis-final\apps\gateway
..\..\.venv\Scripts\Activate.ps1
python -m scripts.dev_db start            # first run creates it; later runs just start it
# optional demo account: $env:SEED_USER_PASSWORD = "<choose one>" before 'start'
$env:GATEWAY_ENV_FILE = ".devdb\gateway.env"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

python -m scripts.dev_db status | stop | reset --yes
```

## Phone on Wi-Fi

- Start the gateway with `--host 0.0.0.0` (or `GATEWAY_HOST=0.0.0.0`).
- Set the Wi-Fi profile to **Private**, and allow Python through Windows Firewall when prompted
  (Private networks only).
- Point the app at `http://<PC-LAN-IP>:8000`.

## Tests

```powershell
cd F:\Thesis\Thesis-final\apps\gateway
..\..\.venv\Scripts\python.exe -m pytest -v
```

How the test database works:
- The tests start a **private, throwaway PostgreSQL** with the local install's own `initdb`/`pg_ctl`
  (auto-detected under `C:\Program Files\PostgreSQL\<n>\bin`; override with `PG_BIN`).
- It runs on a random port bound to 127.0.0.1, with a random password, inside pytest's temp folder.
  It is deleted afterwards.
- It never connects to the running PostgreSQL service or to any team database.
- It uses the team's real `01_schema.sql`, minus the pgvector statements (pgvector is not installed
  locally, and the gateway doesn't use `document_chunks`).

## Environment variables (names only)

- **Database:** `DATABASE_HOST`, `DATABASE_PORT`, `POSTGRES_USER`, `DB_PASSWORD` (required),
  `POSTGRES_DB`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`
- **Auth:** `JWT_SECRET` (required, ≥ 32 chars), `JWT_EXPIRES_MINUTES`, `BCRYPT_ROUNDS`
- **Server:** `GATEWAY_HOST`, `GATEWAY_PORT`
- **Seed:** `SEED_USER_USERNAME`, `SEED_USER_EMAIL`, `SEED_USER_PASSWORD`, `SEED_USER_LANGUAGE`
- **Tooling:** `GATEWAY_ENV_FILE` (alternative .env path; tests set it to empty), `PG_BIN`
  (PostgreSQL programs folder), `SCHEMA_FILE` (path to `01_schema.sql`), `DEV_DB_PORT` (dev DB port, default 55432)

## Security notes

- Passwords are stored only as bcrypt hashes (cost 12). Inputs over bcrypt's 72-byte limit are rejected, never truncated.
- Logs contain user IDs only, never passwords, tokens or request bodies. A test asserts this.
- Login answers "wrong username" and "wrong password" identically, including timing (a dummy hash check runs for unknown users).
- A token for a deleted user is rejected (`TOKEN_INVALID`).
- No CORS is configured, because native apps don't need it. Add it only if a web client is introduced.
