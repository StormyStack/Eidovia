# Eidovia

An augmented reality mobile app that teaches biology using adaptive AI.
Students ask questions in a chat interface — the AI generates personalized answers directly via a local LLM (**Phi-4 mini on Ollama :11434**). AR scenes bring the biology to life.

> Thesis project · React Native (Expo SDK 57) · FastAPI · PostgreSQL 16 + pgvector · Redis 7 · Ollama (Phi-4 mini) · Docker

---

## Architecture

```
 Phone (Expo Go)
      │
      │  REST / JSON
      ▼
 API Gateway (8000) ────── PostgreSQL 16 (6543) [users, modules, auth]
      │             ────── Redis 7 (6379)       [cache]
      │
      │  HTTP (Docker internal: http://ollama:11434)
      ▼
 Ollama (11434)     ────── Phi-4 mini local LLM (Handles AI Messaging directly)
```

- **All backend services run via Docker Compose**:
  - `eidovia_postgres` (port `6543`) — Database with pgvector
  - `eidovia_redis` (port `6379`) — Cache
  - `eidovia_ollama` (port `11434`) — Local AI runtime running Phi-4 mini with GPU acceleration
  - `eidovia_gateway` (port `8000`) — API Gateway (proxies chat directly to Ollama)
- **Mobile Client**:
  - `apps/mobile` (Expo SDK 57) connects to API Gateway on port `8000`

---

## Tech Stack & Ports

| Service / Container | Port | Host URL | Description |
|---|---|---|---|
| **API Gateway** | `8000` | http://localhost:8000/docs | Auth, profiles, module catalogue, AI chat proxy |
| **Ollama (AI Container)** | `11434` | http://localhost:11434 | Local LLM inference (Phi-4 mini) handling AI messaging |
| **PostgreSQL** | `6543` | `localhost:6543` | Relational & vector database |
| **Redis** | `6379` | `localhost:6379` | Response & session caching |

---

## Configuration & Network

- Unified environment file: [`.env`](.env)
- Mobile configuration: [`apps/mobile/.env`](apps/mobile/.env)
- Active PC Wi-Fi IP is set to: **`10.14.5.133`**
  - `EXPO_PUBLIC_API_URL=http://10.14.5.133:8000`

---

## How to Run Everything (3 Steps)

### Step 1: Start All Backend Services (Docker)

From project root (`Thesis/`):

```powershell
docker compose up -d --build
docker compose ps
```

*Starts `eidovia_postgres`, `eidovia_redis`, `eidovia_ollama`, and `eidovia_gateway`.*

---

### Step 2: Initialize Database & Models *(First time only)*

```powershell
# 1. Pull Phi-4 mini in Ollama:
docker exec eidovia_ollama ollama pull phi4-mini

# 2. Seed database tables, demo student, and AR module catalogue:
docker exec -i eidovia_gateway python -m scripts.setup_db
```

---

### Step 3: Start the Mobile App

In a separate terminal window:

```powershell
cd apps\mobile
$env:REACT_NATIVE_PACKAGER_HOSTNAME = "10.14.5.133"
npx expo start --go --clear
```

1. Ensure your physical phone and PC are connected to the **same Wi-Fi network**.
2. Open **Expo Go** on your phone.
3. Scan the displayed QR code to launch the application.

---

## Stopping Services

```powershell
# Stop all Docker containers (preserves volume data):
docker compose stop

# Tear down containers:
docker compose down
```

---

## Troubleshooting

- **Phone cannot reach backend**: Ensure Windows Network Profile is set to **Private** so Windows Firewall permits incoming connections on port `8000`.
- **IP changed**: Check current IP with `ipconfig` and update `EXPO_PUBLIC_API_URL` in `.env` and `apps/mobile/.env`.
- **Swagger Docs**: Test backend endpoints directly at [http://localhost:8000/docs](http://localhost:8000/docs).
