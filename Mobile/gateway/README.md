# EduAR-AI API Gateway (`apps/gateway`)

FastAPI service on **port 8000** providing auth, user profile and the module catalogue for the
mobile app.

## Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | Create account |
| POST | `/api/auth/login` | — | Get JWT token |
| GET | `/api/users/{user_id}/profile` | Bearer | User profile |
| GET | `/api/modules` | Bearer | Module list for Home screen |
| GET | `/api/modules/{module_id}/config` | Bearer | Module config for AR |
| GET | `/health` | — | Liveness + DB status |

Interactive docs: `http://127.0.0.1:8000/docs` while the server runs.

## Layout

```
apps/gateway/
├── app/
│   ├── main.py          FastAPI app, lifespan, /health
│   ├── config.py        Settings from env + .env file
│   ├── db.py            Async SQLAlchemy engine + session management
│   ├── security.py      bcrypt hashing, JWT issue/verify
│   ├── deps.py          get_current_user (Bearer token dependency)
│   ├── errors.py        Contract error format { detail: { code, message, fields? } }
│   ├── schemas.py       Pydantic request/response models
│   ├── repositories.py  All SQL queries (parameterised)
│   └── routers/         auth.py, users.py, modules.py
├── migrations/          Additive SQL migrations (idempotent)
├── scripts/
│   ├── setup_db.py      Run migrations + seed modules & test user
│   ├── dev_db.py        Local dev PostgreSQL (no Docker needed)
│   └── local_pg.py      Private-cluster helpers for tests & dev_db
└── tests/               pytest suite (runs on a throwaway PostgreSQL)
```

## Database

The gateway uses **SQLAlchemy 2.0 async** with `asyncpg` to connect to PostgreSQL.

### Tables

**`users`** — registered accounts
| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID (PK) | Auto-generated |
| `username` | TEXT | Unique |
| `email` | TEXT | Unique (case-insensitive), added by migration 001 |
| `password_hash` | TEXT | bcrypt hash (cost 12) |
| `language` | TEXT | 2-letter code, default `"en"` |
| `detail_level` | INT | Schema default |
| `created_at` | TIMESTAMP | Auto-generated |

**`modules`** — AR learning modules
| Column | Type | Notes |
|---|---|---|
| `module_id` | TEXT (PK) | e.g. `"cell-explore"` |
| `name` | TEXT | Display title |
| `scene_name` | TEXT | Unity scene name |
| `cdn_bundle_url` | TEXT | Asset bundle URL |
| `difficulty` | INT | 1–3 |
| `config` | JSONB | `{"display": {"description": "...", "thumbnail_url": "..."}}` |

### Connection Architecture

```
FastAPI request
  └─► db.get_session()  →  AsyncSession
        ├─► repositories.py  (parameterised SQL via text())
        ├─► auto-commit on success
        └─► auto-rollback on error
```

- **Engine**: async, with `pool_pre_ping=True`, `pool_size=5`, `max_overflow=10`
- **Health**: `GET /health` runs `SELECT 1` to check connectivity
- **Startup**: fails fast if `DB_PASSWORD` or `JWT_SECRET` is missing/invalid

## Requirements

- Python **3.11+**
- PostgreSQL with the base `users` and `modules` tables already created
- One of: a running PostgreSQL instance (Docker or native), or the local dev DB below

## Setup (standard)

Prerequisite: PostgreSQL is running with the base tables (`users`, `modules`) created.

```powershell
cd apps\gateway
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Fill in DB_PASSWORD, JWT_SECRET, optionally SEED_USER_PASSWORD
# Generate JWT_SECRET:
python -c "import secrets; print(secrets.token_urlsafe(48))"

python -m scripts.setup_db          # apply migrations + seed data
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

curl http://127.0.0.1:8000/health    # {"status":"ok","database":"connected"}
```

## Local Dev Database (no Docker)

`scripts/dev_db.py` runs a **private** PostgreSQL using your locally installed PostgreSQL binaries
(auto-detected under `C:\Program Files\PostgreSQL\<version>\bin`, or set `PG_BIN`):

- Data in `apps/gateway/.devdb/` (gitignored), on `127.0.0.1:55432`
- Writes `.devdb/gateway.env` with a generated DB password and JWT secret

```powershell
cd apps\gateway
python -m scripts.dev_db start       # first run creates the cluster
$env:GATEWAY_ENV_FILE = ".devdb\gateway.env"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

python -m scripts.dev_db status       # check status
python -m scripts.dev_db stop         # stop the cluster
python -m scripts.dev_db reset --yes  # delete and recreate
```

## Reaching From Phone (Wi-Fi)

1. Start the gateway with `--host 0.0.0.0`
2. Set your Wi-Fi profile to **Private** in Windows settings
3. Allow Python through Windows Firewall (Private networks)
4. Point the mobile app at `http://<PC-LAN-IP>:8000`

## Tests

```powershell
cd apps\gateway
python -m pytest -v
```

Tests start a **private, throwaway PostgreSQL** (auto-detected local install). It runs on a random
port, uses a random password, and is deleted after the run. It never touches your running database.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DB_PASSWORD` | ✅ | — | PostgreSQL password |
| `JWT_SECRET` | ✅ | — | ≥ 32 chars |
| `DATABASE_HOST` | | `localhost` | PostgreSQL host |
| `DATABASE_PORT` | | `5432` | PostgreSQL port |
| `POSTGRES_USER` | | `appuser` | PostgreSQL user |
| `POSTGRES_DB` | | `eduarai` | Database name |
| `DB_POOL_SIZE` | | `5` | Connection pool size |
| `DB_MAX_OVERFLOW` | | `10` | Max overflow connections |
| `JWT_EXPIRES_MINUTES` | | `10080` | Token expiry (7 days) |
| `BCRYPT_ROUNDS` | | `12` | bcrypt cost factor (4–15) |
| `GATEWAY_HOST` | | `127.0.0.1` | Server bind host |
| `GATEWAY_PORT` | | `8000` | Server bind port |
| `SEED_USER_USERNAME` | | `demo_student` | Test user name |
| `SEED_USER_EMAIL` | | `demo.student@example.com` | Test user email |
| `SEED_USER_PASSWORD` | | — | Test user password (if set, seeds user) |
| `SEED_USER_LANGUAGE` | | `en` | Test user language |
| `GATEWAY_ENV_FILE` | | `apps/gateway/.env` | Alternative .env path |
| `PG_BIN` | | auto-detect | PostgreSQL binaries folder |
| `SCHEMA_FILE` | | auto-detect | Path to base schema SQL |
| `DEV_DB_PORT` | | `55432` | Dev DB port |

## Security Notes

- Passwords stored as **bcrypt hashes** (cost 12). Inputs over 72 bytes are rejected.
- Logs contain user IDs only — never passwords, tokens, or request bodies.
- Login responds identically for wrong username and wrong password (including timing).
- A token for a deleted user is rejected (`TOKEN_INVALID`).
- No CORS configured (native apps don't need it).
