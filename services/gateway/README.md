# Eidovia — API Gateway

Auth, user profile, module catalogue. Runs on port `8000`.

## Start

```powershell
# From repo root:
docker compose up -d

# First time only — apply migrations + seed data:
docker exec -i eidovia_gateway python -m scripts.setup_db
```

## Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/auth/register` | POST | — | Create account |
| `/api/auth/login` | POST | — | Get JWT token |
| `/api/users/{id}/profile` | GET | Bearer | User profile |
| `/api/modules` | GET | Bearer | Module list |
| `/api/modules/{id}/config` | GET | Bearer | AR module config |
| `/health` | GET | — | Health check |

Swagger docs: [http://localhost:8000/docs](http://localhost:8000/docs)
