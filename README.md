# Eidovia

An augmented reality mobile app that teaches biology using adaptive AI.
Students ask questions in a chat interface. The AI answers using a local LLM (**Phi-4 mini on Ollama**).

> Thesis project · FastAPI · PostgreSQL 16 + pgvector · Redis 7 · Ollama (Phi-4 mini) · Docker

---

## Services

Everything runs with Docker Compose.

| Service | Container | Port | URL |
|---|---|---|---|
| API Gateway | `eidovia_gateway` | `8080` | http://localhost:8080/docs |
| Admin Panel | `eidovia_admin` | `8090` | http://localhost:8090 |
| Ollama (Phi-4 mini) | `eidovia_ollama` | `11434` | http://localhost:11434 |
| PostgreSQL + pgvector | `eidovia_postgres` | `6543` | `localhost:6543` |
| Redis | `eidovia_redis` | `6379` | `localhost:6379` |
| Logger | `eidovia_logger` | – | – |

---

## Requirements

- **Docker Desktop**
- **NVIDIA GPU** *(optional)*. Without one, delete the `deploy:` block under `ollama:` in `docker-compose.yml`.

---

## First-Time Setup

Run all commands from the project root (`Thesis/`).

### 1. Create `.env`

```powershell
Copy-Item .env.example .env
```

Fill in `DB_PASSWORD`, `REDIS_PASSWORD`, `JWT_SECRET` and `SEED_USER_PASSWORD`.

### 2. Start the containers

```powershell
docker compose up -d --build
docker compose ps
```

### 3. Install Phi-4 mini (required for AI chat)

```powershell
docker exec eidovia_ollama ollama pull phi4-mini
docker exec eidovia_ollama ollama list
```

`phi4-mini` must appear in the list. You only pull it once, because it's saved in a Docker volume.

### 4. Seed the database

```powershell
docker exec -i eidovia_gateway python -m scripts.setup_db
```

### 5. Create an admin account

```powershell
docker exec -i eidovia_gateway python -m scripts.create_admin <username> <email> <password>
```

---

## Admin Center

Open **[http://localhost:8090](http://localhost:8090)**. It redirects to the dashboard at [http://localhost:8090/admin/dashboard](http://localhost:8090/admin/dashboard).

1. Make sure the containers are running (`docker compose up -d`).
2. Sign in with the username and password you created in setup step 5.
3. Click **Enter Admin Center**.

Only accounts with the admin role can sign in. To give an existing user the admin role, run step 5 again with their username.

---

## Daily Use

```powershell
# Start
docker compose up -d

# Stop (keeps all data)
docker compose stop
```

Don't run `docker compose down -v`. It deletes the database and the Phi-4 mini model.

---

## Check That It Works

```powershell
docker compose ps
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8090/health
docker exec eidovia_ollama ollama list
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Chat says "Port 11434 (Ollama) is being connected…" | Phi-4 mini isn't installed. Run setup step 3 |
| `Set DB_PASSWORD in .env` | Missing values in `.env`. See setup step 1 |
| `port 11434 ... only one usage` | The Windows Ollama app is running. Quit it |
| See logs | `docker compose logs -f gateway` (or `ollama`, `admin`, `logger`, `postgres`) |
