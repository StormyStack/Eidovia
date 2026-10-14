"""
Technical request log for the admin panel ("Technical" tab).

Every request to the gateway is written to Redis:
  request_logs   newest first, the last 5000 requests: when, who, from where (IP, device), method, path,
                 which backend served it (upstream), status, time taken, error
  online_users   hash user_id -> last request of that user (last seen, IP, device); removed on logout
Handlers say where a request really went with note(upstream=...), e.g. the chat route: Redis cache or Ollama.
push_log_event() adds the request's IP and device to audit events (login, chat, AR ...), so the user history
in the admin panel shows where each action came from.
"""

import contextvars
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request

logger = logging.getLogger(__name__)

REQUEST_LOG_KEY = "request_logs"
REQUEST_LOG_MAX = 5000
ONLINE_KEY = "online_users"
SKIP_PATHS = {"/health", "/favicon.ico"}

# the request being handled (a dict, so handlers can add to it with note())
current: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("eidovia_request", default=None)

# where a request goes when the handler does not say otherwise
UPSTREAMS = [
    ("/api/auth", "gateway → PostgreSQL (users)"),
    ("/api/users", "gateway → PostgreSQL (users)"),
    ("/api/modules", "gateway → PostgreSQL (modules)"),
    ("/api/ar/progress", "gateway → PostgreSQL (audit_logs, wildcard_wallets)"),
    ("/api/wildcards/request", "gateway → PostgreSQL (support_tickets)"),
    ("/api/wildcards", "gateway → PostgreSQL (wildcard_wallets)"),
    ("/api/events", "gateway → Redis queue → logger → PostgreSQL (audit_logs)"),
    ("/api/chat", "gateway → AI"),
    ("/api/cache-flush", "gateway → Redis (cache)"),
    ("/docs", "gateway (API docs)"),
    ("/openapi.json", "gateway (API docs)"),
]


def note(**fields: Any) -> None:
    """Add facts to the current request's log line (user, upstream, detail)."""
    ctx = current.get()
    if ctx is not None:
        ctx.update({k: v for k, v in fields.items() if v is not None})


def client_ip(request: Request) -> Optional[str]:
    """Real client address: ngrok and other proxies put it in X-Forwarded-For."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else None


def device(request: Request) -> str:
    """The mobile app sends X-Client (app, OS, phone model); others are known by their User-Agent."""
    return (request.headers.get("x-client") or request.headers.get("user-agent") or "unknown")[:160]


def _default_upstream(path: str) -> str:
    for prefix, upstream in UPSTREAMS:
        if path.startswith(prefix):
            return upstream
    return "gateway"


async def middleware(request: Request, call_next):
    path = request.url.path
    if request.method == "OPTIONS" or path in SKIP_PATHS:
        return await call_next(request)

    ctx: dict[str, Any] = {"id": uuid.uuid4().hex[:12], "ip": client_ip(request), "device": device(request)}
    token = current.set(ctx)
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = ctx["id"]
        return response
    except Exception as exc:
        ctx.setdefault("error", f"{type(exc).__name__}: {exc}"[:300])
        raise
    finally:
        current.reset(token)
        await _record(request, ctx, status, round((time.perf_counter() - started) * 1000, 1))


async def _record(request: Request, ctx: dict, status: int, ms: float) -> None:
    from app.logger_client import get_redis   # avoids a circular import

    now = datetime.now(timezone.utc).isoformat()
    path = request.url.path
    entry = {
        "id": ctx["id"],
        "ts": now,
        "method": request.method,
        "path": path,
        "query": str(request.url.query)[:200] or None,
        "status": status,
        "ms": ms,
        "ip": ctx.get("ip"),
        "device": ctx.get("device"),
        "user_id": ctx.get("user_id"),
        "username": ctx.get("username"),
        "upstream": ctx.get("upstream") or _default_upstream(path),
        "detail": ctx.get("detail"),
        "error": ctx.get("error"),
    }
    try:
        r = await get_redis()
        pipe = r.pipeline()
        pipe.lpush(REQUEST_LOG_KEY, json.dumps(entry))
        pipe.ltrim(REQUEST_LOG_KEY, 0, REQUEST_LOG_MAX - 1)
        if entry["user_id"]:
            if path == "/api/auth/logout" and status < 400:
                pipe.hdel(ONLINE_KEY, entry["user_id"])
            else:
                pipe.hset(ONLINE_KEY, entry["user_id"], json.dumps({
                    "username": entry["username"], "ip": entry["ip"], "device": entry["device"],
                    "last_seen": now, "last_path": f"{request.method} {path}",
                }))
        await pipe.execute()
    except Exception as e:  # the log must never break a request
        logger.warning("request log not written: %s", e)
