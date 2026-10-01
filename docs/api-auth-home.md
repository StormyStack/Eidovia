# API contract — Auth + Home (Sprint 1)

Status: **Approved by the RN developer (2026-10-01) and implemented** in `apps/gateway` + `apps/mobile`.
Items marked **NEW** / **Diagram** still need **SE (team) agreement**.
Owner: React Native Developer (Team Member #4) · Date: 2026-10-01

This is the REST contract between the mobile app (`apps/mobile/`) and the API Gateway
(`apps/gateway/`, FastAPI, port **8000**) for Sign Up, Login and Home.
It follows the *RN Dev Reference Document* (PDF) and the system architecture diagram.

**Source** column legend:
- **PDF**: path and shape come from the RN Dev Reference Document. Kept exactly; do not change without the team.
- **Diagram**: the path appears in `System_Architecture_Diagram.drawio`, but no response shape was defined there. **Shape needs team agreement.**
- **NEW**: proposed here. **Needs team agreement (SE owns the Gateway).**

## Endpoint summary

| # | Method | Path | Auth | Source |
|---|---|---|---|---|
| 1 | `POST` | `/api/auth/register` | none | **NEW** |
| 2 | `POST` | `/api/auth/login` | none | **PDF** (exact) |
| 3 | `GET` | `/api/users/{user_id}/profile` | Bearer | path **PDF**, response shape **NEW** |
| 4 | `GET` | `/api/modules` | Bearer | path **Diagram**, response shape **NEW** |
| 5 | `GET` | `/api/modules/{module_id}/config` | Bearer | **PDF** (exact) |
| 6 | `GET` | `/health` | none | path **Diagram**, response shape **NEW** |

Out of scope for this sprint (must not be blocked by this design): `POST /api/sessions`,
`POST /api/chat`, `POST /api/adapt`, `WSS /ws/session/{session_id}` (token goes in the query param per PDF).

---

## Conventions

- **Base URL:** `http://<gateway-host>:8000`. The mobile app reads it from `EXPO_PUBLIC_API_URL` and never hardcodes it.
- **Content type:** `application/json; charset=utf-8` for requests and responses.
- **Authentication:** `Authorization: Bearer <token>` on every endpoint marked *Bearer*.
- **Token:** JWT, HS256, signed with the server env var `JWT_SECRET` (never in the repo).
  - Claims: `sub` = `user_id` (UUID string), `iat`, `exp`.
  - Lifetime comes from `JWT_EXPIRES_MINUTES` (default 10080 = 7 days).
  - There is no refresh endpoint yet. When the token expires, the app returns to Login. A refresh
    endpoint is future work; the PDF's AuthService comment mentions "token refresh".
- **IDs:** `user_id` is a UUID string. `module_id` is a free-text string (e.g. `"cell-explore"`).
- **Case rules:**
  - Usernames are matched **case-insensitively** for uniqueness and login, but stored and shown as typed.
  - Emails are stored **lower-cased** and are unique case-insensitively.
- **Logging:** the server never logs passwords, tokens or `Authorization` headers.

### Error format (all endpoints)

Every non-2xx response uses FastAPI's existing `detail` convention (the same key the AI service
uses), with a structured object:

```json
{
  "detail": {
    "code": "VALIDATION_ERROR",
    "message": "Please fix the highlighted fields.",
    "fields": { "email": "Enter a valid email address." }
  }
}
```

| Field | Type | Notes |
|---|---|---|
| `code` | string | Stable, machine-readable. The app switches on this value, never on `message`. |
| `message` | string | Human-readable English text, safe to show to the user. |
| `fields` | object (optional) | Only for `VALIDATION_ERROR`. Maps a request field to its error message. |

| HTTP | `code` | When |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Missing, malformed or out-of-range input. The Gateway returns **400 instead of FastAPI's default 422**. |
| 401 | `INVALID_CREDENTIALS` | Login with a wrong username or password. The response is identical in both cases, so it never reveals which one was wrong. |
| 401 | `TOKEN_MISSING` | Bearer endpoint called without an `Authorization` header. |
| 401 | `TOKEN_INVALID` | Malformed token, bad signature, or a user that no longer exists. |
| 401 | `TOKEN_EXPIRED` | `exp` is in the past. |
| 403 | `FORBIDDEN` | Valid token, but asking for another user's data. |
| 404 | `MODULE_NOT_FOUND` | The module doesn't exist. |
| 409 | `USERNAME_TAKEN` / `EMAIL_TAKEN` | Registration conflict. |
| 500 | `INTERNAL_ERROR` | Unexpected server error. The message is generic and no stack trace is returned. |

Every 401 also carries the header `WWW-Authenticate: Bearer`.

---

## 1. `POST /api/auth/register` — **NEW**

Creates an account and logs the user in immediately (auto-login after sign-up).

**Request**
```json
{ "username": "shanto", "email": "shanto@example.com", "password": "********", "language": "en" }
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `username` | string | yes | Trimmed. 3–32 characters, `A–Z a–z 0–9 _ . -` only. Unique case-insensitively. |
| `email` | string | yes | Trimmed and lower-cased. Valid email format, max 254 characters. Unique. |
| `password` | string | yes | 8–72 **bytes** (72 is bcrypt's limit; longer passwords are rejected, not silently truncated). Stored only as a bcrypt hash. |
| `language` | string | no | 2-letter lowercase code (`^[a-z]{2}$`). Default `"en"`. |

`detail_level` cannot be set here. New users get the schema default `1`.

**Response `201 Created`**: exactly the login response shape (see §2).
```json
{
  "user_id": "3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718",
  "token": "<jwt>",
  "profile": { "detail_level": 1, "language": "en" }
}
```

**Errors:** `400 VALIDATION_ERROR` · `409 USERNAME_TAKEN` · `409 EMAIL_TAKEN` · `500 INTERNAL_ERROR`

---

## 2. `POST /api/auth/login` — **PDF (exact)**

**Request** (exactly the PDF's shape)
```json
{ "username": "shanto", "password": "********" }
```
| Field | Type | Required | Rules |
|---|---|---|---|
| `username` | string | yes | Non-empty after trimming. Matched case-insensitively. |
| `password` | string | yes | Non-empty. |

**Response `200 OK`** (exactly the PDF's shape: no extra fields)
```json
{
  "user_id": "3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718",
  "token": "<jwt>",
  "profile": { "detail_level": 1, "language": "en" }
}
```
| Field | Type | Source column |
|---|---|---|
| `user_id` | string (UUID) | `users.user_id` |
| `token` | string (JWT) | issued by the Gateway |
| `profile.detail_level` | integer | `users.detail_level` |
| `profile.language` | string | `users.language` |

**Errors:** `400 VALIDATION_ERROR` (missing field) · `401 INVALID_CREDENTIALS` · `500 INTERNAL_ERROR`

---

## 3. `GET /api/users/{user_id}/profile` — path **PDF**, shape **NEW**

Returns the logged-in user's profile. The PDF names this path but doesn't define a body. The
Home screen uses it to greet the user by name.

**Path parameter:** `user_id`, which must be a UUID and must equal the token's `sub`.

**Response `200 OK`**
```json
{
  "user_id": "3f8a1c2e-5b7d-4e9f-a1b2-c3d4e5f60718",
  "username": "shanto",
  "email": "shanto@example.com",
  "detail_level": 1,
  "language": "en",
  "created_at": "2026-10-01T12:34:56.789000+00:00"
}
```
`email` may be `null` for accounts created outside `/api/auth/register` (e.g. inserted by other team tooling).
`created_at` is ISO 8601 with a timezone.

**Errors:**
- `400 VALIDATION_ERROR`: `user_id` isn't a UUID.
- `401 TOKEN_MISSING / TOKEN_INVALID / TOKEN_EXPIRED`
- `403 FORBIDDEN`: `user_id` ≠ token `sub`.
- `500 INTERNAL_ERROR`

Every Bearer endpoint checks that the token's user still exists. A token for a deleted account
gets `401 TOKEN_INVALID`, so the app logs out. That is why this endpoint has no 404.

---

## 4. `GET /api/modules` — path **Diagram**, shape **NEW**

Lists the AR learning modules for the Home screen.

**Response `200 OK`**: a JSON array, which is empty (`[]`) when there are no modules. It is
ordered by `difficulty` and then `module_id`.
```json
[
  {
    "module_id": "cell-explore",
    "title": "Explore the Cell",
    "description": "Tap organelles in AR to discover what each one does.",
    "difficulty": 1,
    "thumbnail_url": null
  }
]
```
| Field | Type | Source (no schema change) |
|---|---|---|
| `module_id` | string | `modules.module_id` |
| `title` | string | `modules.name` |
| `description` | string | `modules.config -> 'display' ->> 'description'`. `""` if absent. |
| `difficulty` | integer | `modules.difficulty` |
| `thumbnail_url` | string \| null | `modules.config -> 'display' ->> 'thumbnail_url'`. `null` if absent. |

**Convention (needs team agreement):** display-only metadata lives under a `display` key inside
the existing `modules.config` JSONB column, so the `modules` table needs no new columns:
`{ "display": { "description": "...", "thumbnail_url": "..." }, ...other config... }`.

**Errors:** `401 TOKEN_MISSING / TOKEN_INVALID / TOKEN_EXPIRED` · `500 INTERNAL_ERROR`

---

## 5. `GET /api/modules/{module_id}/config` — **PDF (exact)**

Fetched when the user taps a module. The result is passed to `ARGameScreen`. In Sprint 2 it goes
to Unity via `UnityBridge.sendModuleConfig()`.

**Response `200 OK`** (exactly the PDF's shape)
```json
{
  "module_id": "cell-explore",
  "scene_name": "GameScene_CellExplore",
  "cdn_bundle_url": "https://cdn.example.com/bundles/cell-explore",
  "difficulty": 1,
  "config": { "display": { "description": "Tap organelles in AR to discover what each one does." } }
}
```
| Field | Type | Source column |
|---|---|---|
| `module_id` | string | `modules.module_id` |
| `scene_name` | string | `modules.scene_name` (must equal a Unity scene name) |
| `cdn_bundle_url` | string | `modules.cdn_bundle_url` |
| `difficulty` | integer | `modules.difficulty` |
| `config` | object | `modules.config` as stored (`{}` if empty) |

**Team note:** Unity's `ModuleConfig` class (Unity Dev Reference) also has a `name` field, which
this PDF contract doesn't return. This contract is kept exactly as the PDF defines it. Unity's
`JsonUtility` leaves `name` empty. The team should decide whether to add it.

**Errors:** `401 TOKEN_MISSING / TOKEN_INVALID / TOKEN_EXPIRED` · `404 MODULE_NOT_FOUND` · `500 INTERNAL_ERROR`

---

## 6. `GET /health` — path **Diagram**, shape **NEW**

Unauthenticated liveness check, used in run instructions and for diagnosing "backend offline".

**Response `200 OK`**
```json
{ "status": "ok", "service": "gateway", "database": "connected" }
```
`database` is `"connected"` or `"disconnected"`. When it is disconnected the endpoint still returns 200 with `"status": "degraded"`.

---

## Mobile client behaviour (how `ApiClient.ts` uses this contract)

- **Timeout:** every request times out after **5 s** (PDF API-testing requirement).
- **Token:** the request interceptor adds `Authorization: Bearer <token>` when a token is stored.
- **401 handling:**
  - A 401 from a **Bearer** endpoint clears the stored credentials and returns the app to Login.
  - 401s from `/api/auth/login` and `/api/auth/register` are **not** treated as a logout. They are shown as form errors.
- **Client-side error codes:** these are added by the app for failures that never reach the server.
  The UI handles them the same way as server codes:
  - `NETWORK_ERROR`: no connection, or the server is unreachable.
  - `TIMEOUT`: more than 5 s.
  - `UNKNOWN_ERROR`: an unexpected response shape.

---

## Proposed database migration — **needs SE agreement (NOT applied yet)**

`users` has no `email` column. This additive, idempotent migration will live at
`apps/gateway/migrations/001_add_user_email.sql`. The Gateway's setup script runs it.
It does **not** edit `01_schema.sql` or `docker-compose.yml`.

```sql
-- 001_add_user_email.sql — additive, safe to run more than once.
ALTER TABLE users ADD COLUMN IF NOT EXISTS email TEXT;

-- Unique, case-insensitive. Multiple NULLs are allowed, so existing users without email stay valid.
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_lower ON users (lower(email));
```

- The column is nullable and unique (case-insensitive via the `lower(email)` index). Existing rows are untouched.
- Rollback, if ever needed: `DROP INDEX IF EXISTS uq_users_email_lower; ALTER TABLE users DROP COLUMN IF EXISTS email;`

## Items needing team agreement (summary)

1. `POST /api/auth/register`: the whole endpoint.
2. The `email` column migration above.
3. Response shapes for `GET /api/users/{user_id}/profile`, `GET /api/modules` and `GET /health`.
4. The `modules.config.display` convention for list metadata.
5. The error format, and returning `400` instead of FastAPI's `422`.
6. JWT claims, 7-day default lifetime, and no refresh endpoint yet.
7. Whether the module config response should also return `name` (Unity's `ModuleConfig` expects it).
