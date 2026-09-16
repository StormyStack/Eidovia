# EduAR-AI Storage Stack (Postgres + pgvector, Redis)

You don't need to configure Postgres or Redis. Just set your `.env`, run one command,
and connect using the URLs below.

## 1. Setup (one time)

```bash
cp .env.example .env
```

Edit `.env` and set real passwords for `DB_PASSWORD` and `REDIS_PASSWORD`.
Everyone on the team should use the **same** `.env` values if you're pointing at a
shared/staging instance, or your own values if running locally.

## 2. Run

```bash
docker compose up -d
```

That's it. Postgres schema (users, sessions, events, modules, document_chunks + the
pgvector `ivfflat` index) is created automatically on first boot from `01_schema.sql`.
Redis starts with AOF persistence enabled and password auth on.

Check both are healthy:
```bash
docker compose ps
```

---

## 3. Web UI Access (Browser Dashboards)

You can manage and view both databases directly from your web browser.

### A. PostgreSQL Web Dashboard (Adminer)

Run Adminer connected to the compose network:
```bash
docker run -d --name eduarai_adminer -p 8080:8080 --network files_default adminer
```

1. Open in your browser: **http://localhost:8080**
2. Fill in the login form:
   * **System:** `PostgreSQL`
   * **Server:** `postgres` (or `eduarai_postgres`)
   * **Username:** your `POSTGRES_USER` (default: `appuser`)
   * **Password:** your `DB_PASSWORD`
   * **Database:** your `POSTGRES_DB` (default: `eduarai`)
3. Click **Login** to inspect tables, run SQL queries, and view records.

---

### B. Redis Web Dashboard (RedisInsight)

Run official RedisInsight connected to the compose network:
```bash
docker run -d --name eduarai_redisinsight -p 5540:5540 --network files_default redis/redisinsight:latest
```

1. Open in your browser: **http://localhost:5540**
2. Click **"Add Redis Database"** (or **"Connect to a Redis Database"**)
3. Either paste the connection URL:
   ```text
   redis://default:<REDIS_PASSWORD>@redis:6379#EduAR_Redis
   ```
   Or fill in manually:
   * **Host:** `redis` (or `eduarai_redis`)
   * **Port:** `6379`
   * **Database Alias (Display Name):** `EduAR-AI Redis`
   * **Username:** `default` (or leave empty)
   * **Password:** your `REDIS_PASSWORD`
4. Click **Add Redis Database** to browse real-time keys, state vectors, memory, and stats.

---

## 4. Connect from your backend service

Build connection strings from your `.env` values:

**Postgres (asyncpg style):**
```
postgresql+asyncpg://appuser:<DB_PASSWORD>@localhost:<POSTGRES_PORT>/eduarai
```

**Redis:**
```
redis://:<REDIS_PASSWORD>@localhost:<REDIS_PORT>/0
```

If your service runs in another Docker container on the same network:
```
postgresql+asyncpg://appuser:<DB_PASSWORD>@eduarai_postgres:5432/eduarai
redis://default:<REDIS_PASSWORD>@eduarai_redis:6379/0
```

---

## 5. Redis Key Contract (Used by AI Service & Gateway)

| Key pattern | Type | TTL | Payload |
|---|---|---|---|
| `session:{session_id}:state` | String (JSON array) | 3600s sliding | 8D normalized learner state vector `[correct_rate, hints, diff, ar_taps, skips, time, sessions, recent]` |
| `user:{user_id}:profile_cache` | Hash | 7200s | `{detail_level, language}` |
| `lock:etl_refresh:{id}` | String (mutex) | 15s | Distributed lock for ETL background worker |

---

## 6. Postgres Schema Summary

* `users` — `user_id` (UUID PK), `username`, `password_hash`, `detail_level`, `language`, `created_at`
* `sessions` — `session_id` (UUID PK), `user_id` (FK → users), `started_at`, `ended_at`
* `events` — high-frequency interaction telemetry (`event_id` UUID PK, `scene_name`, `event_type`, `object_id`, `module_id`, `correct`, `time_spent_ms`, `payload` JSONB, `client_timestamp`, `server_timestamp`), FK to users/sessions
* `modules` — curriculum & CDN bundle metadata (`module_id` TEXT PK, `name`, `scene_name`, `cdn_bundle_url`, `difficulty`, `config` JSONB)
* `document_chunks` — RAG knowledge vector store (`chunk_id` UUID PK, `module_id` FK → modules with `ON DELETE CASCADE`, `content` TEXT, `embedding vector(384)`, `created_at`), indexed with `ivfflat` cosine similarity

---

## 7. Stopping / Resetting

```bash
docker compose down          # Stop containers, preserve data volumes
docker compose down -v       # Stop and completely WIPE all volume data (fresh start)
```

To stop web tools when no longer needed:
```bash
docker rm -f eduarai_adminer eduarai_redisinsight
```

---

## 8. Troubleshooting

* **"password authentication failed"** → Your `.env` does not match the password used when the volume was first initialized. Either fix `.env` or run `docker compose down -v` and `docker compose up -d` to re-initialize an empty database.
* **Schema not created** → `01_schema.sql` executes only on an *empty* Postgres volume. If a volume already existed from an earlier run, run `docker compose down -v` followed by `docker compose up -d`.
* **Port already in use** → Change `POSTGRES_PORT` or `REDIS_PORT` in your `.env`.
* **Web tools can't connect** → Ensure you connect to host `postgres` or `redis` (not `localhost` or `127.0.0.1`), because web containers communicate through Docker's internal bridge network.
