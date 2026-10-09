# EduAR-AI

An augmented-reality mobile app for teaching biology, powered by adaptive AI tutoring.

> **Thesis project** — React Native (Expo) · FastAPI · PostgreSQL + pgvector · Redis · Docker

---

## Architecture

```
┌─────────────────────┐     HTTP/JSON      ┌─────────────────────┐
│   Mobile App        │ ◄─────────────────► │   API Gateway       │
│   React Native      │                     │   FastAPI · port 8000│
│   Expo SDK 57       │                     └──────────┬──────────┘
└─────────────────────┘                               │
                                                      │ asyncpg
                                         ┌────────────▼────────────┐
                                         │   PostgreSQL 16          │
                                         │   users · modules        │
                                         └─────────────────────────┘
                                                      ▲
                                          HTTP        │
                                         ┌────────────┴────────────┐
                                         │   AI Service            │
                                         │   FastAPI · port 8001   │
                                         │   RAG · Bandit · Redis  │
                                         └─────────────────────────┘
```

| Layer | Path | Tech |
|---|---|---|
| Mobile App | `apps/mobile/` | React Native 0.86, Expo SDK 57, TypeScript |
| API Gateway | `services/gateway/` | FastAPI, SQLAlchemy 2 async, asyncpg |
| AI Service | `services/ai/` | FastAPI, pgvector, Redis 7, PyTorch |

---

## Repository Layout

```
Thesis/                              ← repo root
├── .env                             (gitignored — real secrets)
├── .env.example                     (committed — template)
├── .gitignore
├── .dockerignore
├── docker-compose.yml               (orchestrates postgres, redis, ai-service)
├── package.json                     (root scripts — proxies into apps/mobile)
├── README.md
│
├── services/                        ← all backend services
│   ├── ai/                          ← AI microservice
│   │   ├── app/                     ← Python package
│   │   │   ├── main.py              FastAPI app, REST + WebSocket
│   │   │   ├── config.py            Settings from root .env
│   │   │   ├── database.py          Async SQLAlchemy engine
│   │   │   ├── rag.py               RAG retrieval (pgvector)
│   │   │   ├── cache.py             Redis cache service
│   │   │   ├── bandit.py            Contextual bandit
│   │   │   ├── scheduler.py         ETL background jobs
│   │   │   └── events.py            Learner event logging
│   │   ├── data/                    ← curriculum text files
│   │   ├── migrations/              ← SQL schema files
│   │   │   ├── 001_schema.sql
│   │   │   └── 002_events.sql
│   │   ├── scripts/                 ← one-off admin scripts
│   │   │   ├── load_curriculum.py
│   │   │   └── create_curriculum.py
│   │   ├── tests/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── README.md
│   │
│   └── gateway/                     ← API gateway
│       ├── app/
│       │   ├── main.py              FastAPI app, lifespan, /health
│       │   ├── config.py            Settings from root .env
│       │   ├── db.py                Async SQLAlchemy + session
│       │   ├── security.py          bcrypt, JWT
│       │   ├── deps.py              Bearer token dependency
│       │   ├── errors.py            Error contract format
│       │   ├── schemas.py           Pydantic models
│       │   ├── repositories.py      All SQL queries
│       │   └── routers/             auth, users, modules, chat
│       ├── migrations/
│       ├── scripts/
│       ├── tests/
│       ├── requirements.txt
│       └── README.md
│
└── apps/                            ← frontend / client apps
    └── mobile/                      ← React Native app
        ├── src/
        │   ├── App.tsx
        │   ├── config.ts
        │   ├── theme.ts
        │   ├── components/
        │   ├── navigation/
        │   ├── screens/
        │   ├── services/
        │   ├── store/
        │   ├── utils/
        │   └── test-utils/
        ├── .env                     (Expo-only — EXPO_PUBLIC_* must live here)
        ├── app.json
        ├── package.json
        ├── tsconfig.json
        └── README.md
```

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.11+ |
| Node.js | 18+ |
| Docker Desktop | latest (running) |
| Expo Go | SDK 57 (on your phone) |

---

## Environment Setup

All secrets live in **one** file at the repo root:

```powershell
Copy-Item .env.example .env
notepad .env          # fill in the values below
```

**Required values to set:**

| Variable | Used by | Notes |
|---|---|---|
| `DB_PASSWORD` | AI, Gateway | PostgreSQL password |
| `REDIS_PASSWORD` | AI | Redis password |
| `JWT_SECRET` | Gateway | ≥ 32 chars — generate with: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `EXPO_PUBLIC_API_URL` | Mobile app | Your PC's LAN IP, e.g. `http://192.168.1.10:8000` |

> ⚠ Port `5432` is blocked by Windows Hyper-V on this machine. The `.env` uses `DATABASE_PORT=6543` as the host-side mapping — do not change it.

The `apps/mobile/.env` file still exists because **Expo requires `EXPO_PUBLIC_*` variables to sit next to `package.json`**. It contains only that one variable; everything else is in the root `.env`.

---

## Quick Start

### 1 — AI Service

```powershell
docker-compose up -d --build      # starts PostgreSQL, Redis, AI service
# First build: 15–40 min (PyTorch download). Subsequent starts are instant.

docker-compose ps                 # wait until all 3 containers are healthy

# Load curriculum (first time only)
cd services\ai
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\load_curriculum.py

# Verify
curl http://localhost:8001/health
```

### 2 — API Gateway

```powershell
cd services\gateway
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m scripts.setup_db        # apply migrations + seed modules & demo user
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

curl http://localhost:8000/health
```

### 3 — Mobile App

```powershell
cd apps\mobile
npm install

# Set EXPO_PUBLIC_API_URL in apps\mobile\.env to your PC's LAN IP
notepad .env

$env:REACT_NATIVE_PACKAGER_HOSTNAME = "<PC-LAN-IP>"
npx expo start --go --clear       # scan QR with Expo Go on your phone
```

---

## Ports

| Service | Host Port | Notes |
|---|---|---|
| API Gateway | `8000` | REST + JWT auth |
| AI Service | `8001` | REST + WebSocket |
| PostgreSQL | `6543` | Host-side (container still uses 5432 internally) |
| Redis | `6379` | |

---

## API Overview

### Gateway (`localhost:8000`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/auth/register` | — | Create account |
| POST | `/api/auth/login` | — | Get JWT |
| GET | `/api/users/{id}/profile` | Bearer | User profile |
| GET | `/api/modules` | Bearer | Module list |
| GET | `/api/modules/{id}/config` | Bearer | Module config for AR |
| GET | `/health` | — | Liveness + DB status |

> Interactive docs: `http://127.0.0.1:8000/docs`

### AI Service (`localhost:8001`)

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/api/chat` | RAG-based biology Q&A |
| GET | `/api/cache-stats` | Redis hit/miss stats |
| POST | `/api/cache-flush` | Clear Redis cache |
| WS | `/ws/adapt/{session_id}` | Adaptive learning (prototype) |

---

## Running Tests

```powershell
# Gateway (pytest — spins up a throwaway PostgreSQL)
cd services\gateway
python -m pytest -v

# Mobile app (Jest)
cd apps\mobile
npm test
npm test -- --coverage
npx tsc --noEmit
```

---

## `EXPO_PUBLIC_API_URL` Cheat Sheet

| Where the app runs | Value |
|---|---|
| Physical phone (same Wi-Fi) | `http://<PC-LAN-IP>:8000` |
| Android emulator | `http://10.0.2.2:8000` |
| iOS Simulator (macOS) | `http://localhost:8000` |

After editing `apps/mobile/.env`, restart Metro: `npx expo start --clear`

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `bind: access denied` on port 5432/5433 | Windows Hyper-V blocks those ports. Use `DATABASE_PORT=6543` |
| `No module named 'greenlet'` | Use `SQLAlchemy[asyncio]` in `requirements.txt` (already fixed) |
| `Query encoding timeout` | Set `RAG_TIMEOUT=5.0` in `.env` |
| Container still loading | Wait 40 s after `docker-compose up`; `docker logs eduarai_ai --tail 30` |
| No documents returned from RAG | Run `python scripts\load_curriculum.py` inside `services\ai\` |
| QR code opens wrong IP | Set `REACT_NATIVE_PACKAGER_HOSTNAME=<PC-LAN-IP>` before `expo start` |
| 401 errors from app | Check `EXPO_PUBLIC_API_URL` points to the gateway, not AI service |

---

## Detailed Docs

- [AI Service →](services/ai/README.md)
- [API Gateway →](services/gateway/README.md)
- [Mobile App →](apps/mobile/README.md)
