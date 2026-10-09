# Eidovia

An augmented reality mobile app that teaches biology using adaptive AI.
Students ask questions in a chat interface — the AI retrieves relevant content from a curriculum
and gives personalized answers. AR scenes (Unity) bring the biology to life.

> Thesis project · React Native · FastAPI · PostgreSQL + pgvector · Redis · Docker

---

## How It Works

```
 Phone (Expo Go)
      │
      │  REST / JSON
      ▼
 API Gateway  ──── PostgreSQL  (users, modules, auth)
      │
      │  HTTP
      ▼
 AI Service   ──── pgvector    (curriculum embeddings)
              ──── Redis       (response cache)
```

1. The **mobile app** handles login, the module catalogue, and the chat screen.
2. The **API Gateway** handles all auth (JWT), user profiles, and module data.
3. The **AI Service** takes a student's question, finds the closest curriculum chunks using vector similarity, and returns an answer. Repeated questions are served from Redis cache (~4 ms vs ~300 ms cold).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Mobile | React Native 0.86, Expo SDK 57, TypeScript |
| API Gateway | Python, FastAPI, SQLAlchemy 2 async, asyncpg |
| AI Service | Python, FastAPI, pgvector, sentence-transformers, Redis |
| Database | PostgreSQL 16 with pgvector extension |
| Cache | Redis 7 |
| Runtime | Docker (all backend services run in containers) |

---

## Folder Structure

```
Thesis/
├── docker-compose.yml        all 4 backend services
├── .env                      secrets (never committed)
├── .env.example              template — copy this to .env
│
├── services/
│   ├── ai/                   AI microservice (port 8001)
│   │   ├── app/              FastAPI app code
│   │   ├── data/             curriculum text files
│   │   ├── migrations/       SQL schema files
│   │   └── scripts/          load_curriculum.py
│   │
│   └── gateway/              API gateway (port 8000)
│       ├── app/              FastAPI app code
│       ├── migrations/       SQL schema files
│       └── scripts/          setup_db.py
│
└── apps/
    └── mobile/               React Native app (Expo)
        ├── src/
        └── .env              EXPO_PUBLIC_API_URL only
```

---

## Prerequisites

| Tool | Notes |
|---|---|
| Docker Desktop | Must be running |
| Node.js 18+ | For the mobile app |
| Expo Go | Install on your phone (SDK 57) |

No local Python needed — all backend runs inside Docker.

---

## First-Time Setup

**Step 1 — Create your secrets file**

```powershell
Copy-Item .env.example .env
notepad .env
```

Fill in these 4 values:

| Variable | What to put |
|---|---|
| `DB_PASSWORD` | Any strong password |
| `REDIS_PASSWORD` | Any strong password |
| `JWT_SECRET` | Random string ≥ 32 chars. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `EXPO_PUBLIC_API_URL` | `http://<YOUR-PC-LAN-IP>:8000` — find your IP with `ipconfig` |

**Step 2 — Start all backend services**

```powershell
docker compose up -d --build
```

This starts PostgreSQL, Redis, the AI service, and the API Gateway. First build takes a few minutes (downloads PyTorch). Subsequent starts are instant.

**Step 3 — Seed the database** *(one time only)*

```powershell
docker exec -i eidovia_gateway python -m scripts.setup_db
```

Creates tables, loads the module catalogue, and adds a demo user.

**Step 4 — Load the biology curriculum** *(one time only)*

```powershell
docker exec -it eidovia_ai python -m scripts.load_curriculum
```

Converts the curriculum text into vector embeddings stored in PostgreSQL. Takes ~30 seconds.

**Step 5 — Run the mobile app**

```powershell
cd apps\mobile
npm install
# Confirm apps\mobile\.env has: EXPO_PUBLIC_API_URL=http://<YOUR-PC-LAN-IP>:8000

$env:REACT_NATIVE_PACKAGER_HOSTNAME = "<YOUR-PC-LAN-IP>"
npx expo start --go --clear
```

Scan the QR code with **Expo Go** on your phone. Phone must be on the same Wi-Fi as your PC.

---

## Day-to-Day Start

```powershell
# Backend (from repo root)
docker compose up -d

# Mobile
cd apps\mobile
npx expo start --go --clear
```

---

## Ports

| Service | Port | URL |
|---|---|---|
| API Gateway | `8000` | http://localhost:8000/docs |
| AI Service | `8001` | http://localhost:8001/health |
| PostgreSQL | `6543` (host) | — |
| Redis | `6379` | — |

> Port `5432` is blocked by Windows Hyper-V — that's why PostgreSQL maps to `6543` on the host.
> Inside Docker, containers still talk to each other on `5432`.

---

## Stop Everything

```powershell
docker compose down
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `bind: access denied` on port 5432 | Expected on Windows. Already handled — host port is `6543`. |
| Container won't start | Check logs: `docker logs eidovia_ai --tail 50` |
| Chat returns no results | Re-run: `docker exec -it eidovia_ai python -m scripts.load_curriculum` |
| Phone can't reach the backend | Check Wi-Fi — phone and PC must be on the same network. Set Windows network to **Private**. |
| QR code shows wrong IP | Set `$env:REACT_NATIVE_PACKAGER_HOSTNAME` to your actual LAN IP before running Expo. |

---

## Service Docs

- [AI Service](services/ai/README.md)
- [API Gateway](services/gateway/README.md)
- [Mobile App](apps/mobile/README.md)
