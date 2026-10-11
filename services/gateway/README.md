# Eidovia — API Gateway

Authentication, user profiles, module catalogue, and direct AI messaging via **Ollama (port 11434)**. Runs on port `8000`.

---

## AI Messaging Architecture

The gateway proxies chat requests (`POST /api/chat`) directly to **Ollama on port 11434** (`http://localhost:11434/api/chat` using `phi4-mini`).
Port 8001 is completely bypassed and not required.

---

## Running

1. **Ensure Docker containers are running:**
   ```powershell
   docker compose up -d
   ```
   *(Starts `eidovia_postgres`, `eidovia_redis`, and `eidovia_ollama`)*

2. **Seed database & module catalogue (first time only):**
   ```powershell
   cd services\gateway
   python -m scripts.setup_db
   ```

3. **Start the API Gateway:**
   ```powershell
   cd services\gateway
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/auth/register` | POST | — | Create account |
| `/api/auth/login` | POST | — | Get JWT token |
| `/api/users/{id}/profile` | GET | Bearer | User profile |
| `/api/modules` | GET | Bearer | Module list |
| `/api/modules/{id}/config` | GET | Bearer | AR module config |
| `/api/chat` | POST | Bearer | Biology AI chat (powered directly by Ollama :11434) |
| `/health` | GET | — | Health check |

Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)
