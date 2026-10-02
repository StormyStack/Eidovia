# EduAR-AI

An augmented reality educational app for learning biology. The project has two apps:

| App | Tech | Path |
|---|---|---|
| **API Gateway** | FastAPI, PostgreSQL, SQLAlchemy 2 (async) | `apps/gateway/` |
| **Mobile App** | React Native 0.86, Expo SDK 57, TypeScript | `apps/mobile/` |

## Architecture

```
┌──────────────────┐       HTTP/JSON       ┌──────────────────┐
│   Mobile App     │  ◄──────────────────►  │   API Gateway    │
│   (Expo / RN)    │                        │   (FastAPI)      │
└──────────────────┘                        └────────┬─────────┘
                                                     │
                                                     │  asyncpg
                                                     ▼
                                            ┌──────────────────┐
                                            │   PostgreSQL     │
                                            │   (users,        │
                                            │    modules)      │
                                            └──────────────────┘
```

## How the Database Works

The gateway connects to PostgreSQL using **SQLAlchemy 2.0 async** with the **asyncpg** driver.

### Tables

#### `users`
| Column | Type | Notes |
|---|---|---|
| `user_id` | UUID (PK) | Auto-generated |
| `username` | TEXT | Unique |
| `email` | TEXT | Added by `migrations/001_add_user_email.sql`, unique (case-insensitive) |
| `password_hash` | TEXT | bcrypt hash (cost 12) |
| `language` | TEXT | 2-letter code, default `"en"` |
| `detail_level` | INT | Schema default |
| `created_at` | TIMESTAMP | Auto-generated |

#### `modules`
| Column | Type | Notes |
|---|---|---|
| `module_id` | TEXT (PK) | e.g. `"cell-explore"` |
| `name` | TEXT | Display title |
| `scene_name` | TEXT | Unity scene name |
| `cdn_bundle_url` | TEXT | Asset bundle URL |
| `difficulty` | INT | 1 = beginner, 2 = intermediate, 3 = advanced |
| `config` | JSONB | Contains `display.description`, `display.thumbnail_url` |

### Connection Flow

1. **Startup**: `app/db.py` creates an async SQLAlchemy engine with connection pooling (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`).
2. **Per request**: `db.get_session()` yields an `AsyncSession` — auto-commits on success, rolls back on error.
3. **Health check**: `GET /health` runs `SELECT 1` to report database reachability.
4. **Shutdown**: All pooled connections are disposed.

### Seed Data

`python -m scripts.setup_db` seeds 4 AR modules and optionally a test user:

| Module ID | Title | Difficulty |
|---|---|---|
| `cell-explore` | Explore the Cell | 1 (Beginner) |
| `cell-puzzle` | Cell Puzzle | 2 (Intermediate) |
| `cell-process` | Cell Processes | 3 (Advanced) |
| `cell-quiz` | Cell Quiz | 3 (Advanced) |

## Quick Start

### 1. Gateway

```powershell
cd apps\gateway
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env
# Fill in: DB_PASSWORD, JWT_SECRET (min 32 chars)
# Generate JWT_SECRET: python -c "import secrets; print(secrets.token_urlsafe(48))"

python -m scripts.setup_db
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Mobile

```powershell
cd apps\mobile
npm install
copy .env.example .env
# Set EXPO_PUBLIC_API_URL=http://<your-PC-IP>:8000
npx expo start --go --clear
```

Scan the QR code with Expo Go on your phone (same Wi-Fi network).

## Environment Variables

See:
- [`apps/gateway/.env.example`](apps/gateway/.env.example)
- [`apps/mobile/.env.example`](apps/mobile/.env.example)
