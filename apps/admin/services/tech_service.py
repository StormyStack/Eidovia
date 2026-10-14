"""
Technical dashboard for the admin panel: are the services running, who is logged in (and from which IP),
and the gateway's request log ("which request went where, how").

Sources
  request_logs / online_users   Redis, written by the gateway for every request (services/gateway/app/request_log.py)
  logger:heartbeat              Redis, refreshed by the logger service every few seconds
  audit_logs                    login / register / logout events (with IP and device)
"""

import asyncio
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional

import httpx
from sqlalchemy import text

from db import db
from redis_client import get_redis

GATEWAY_URL = os.getenv("GATEWAY_INTERNAL_URL", "http://gateway:8000").rstrip("/")
OLLAMA_URL = os.getenv("OLLAMA_URL", os.getenv("LLM_BASE_URL", "http://ollama:11434")).rstrip("/")
OLLAMA_MODEL = os.getenv("LLM_MODEL", "phi4-mini")
NGROK_DOMAIN = (os.getenv("NGROK_DOMAIN") or "").strip()
JWT_MINUTES = int(os.getenv("JWT_EXPIRES_MINUTES", "10080").split()[0] or 10080)
ACTIVE_MINUTES = 5          # "active now" = a request in the last 5 minutes

REQUEST_LOG_KEY = "request_logs"
ONLINE_KEY = "online_users"


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _service(key: str, name: str, ok: bool, detail: str, latency: Optional[float] = None, warn: bool = False,
             label: Optional[str] = None) -> dict:
    return {"key": key, "name": name, "state": "down" if not ok else "warn" if warn else "up",
            "ok": ok, "latency_ms": latency, "detail": detail, "label": label}


async def _check_gateway() -> dict:
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            res = await client.get(f"{GATEWAY_URL}/health")
        body = res.json() if res.status_code == 200 else {}
        db_state = body.get("database", "?")
        return _service("gateway", "API Gateway (FastAPI :8000 → host :8080)", res.status_code == 200,
                        f"HTTP {res.status_code} · database {db_state}", _ms(t0), warn=db_state != "connected")
    except Exception as e:
        return _service("gateway", "API Gateway (FastAPI :8000 → host :8080)", False, f"unreachable: {type(e).__name__}")


async def _check_postgres() -> dict:
    t0 = time.perf_counter()
    try:
        async with db.get_session() as session:
            row = (await session.execute(text(
                "SELECT split_part(version(), ' ', 2) AS v, pg_database_size(current_database()) AS size, "
                "(SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) AS conns"
            ))).first()
        return _service("postgres", "PostgreSQL (pgvector)", True,
                        f"v{row.v} · {row.size / 1048576:.1f} MB · {row.conns} connections", _ms(t0))
    except Exception as e:
        return _service("postgres", "PostgreSQL (pgvector)", False, f"error: {type(e).__name__}")


async def _check_redis() -> tuple[dict, Optional[Any]]:
    t0 = time.perf_counter()
    try:
        r = await get_redis()
        await r.ping()
        latency = _ms(t0)
        mem = (await r.info("memory")).get("used_memory_human", "?")
        keys = await r.dbsize()
        return _service("redis", "Redis (cache, queues, request log)", True, f"{keys} keys · {mem} memory", latency), r
    except Exception as e:
        return _service("redis", "Redis (cache, queues, request log)", False, f"error: {type(e).__name__}"), None


async def _check_logger(r) -> dict:
    name = "Logger service (audit log writer)"
    if r is None:
        return _service("logger", name, False, "unknown: Redis is down")
    try:
        beat = _parse(await r.get("logger:heartbeat"))
        backlog = await r.llen("raw_audit_logs")
        if beat is None:
            return _service("logger", name, False, f"no heartbeat · {backlog} events waiting")
        age = (datetime.now(timezone.utc) - beat.replace(tzinfo=beat.tzinfo or timezone.utc)).total_seconds()
        return _service("logger", name, age < 30, f"heartbeat {int(age)} s ago · {backlog} events waiting",
                        warn=backlog > 50)
    except Exception as e:
        return _service("logger", name, False, f"error: {type(e).__name__}")


async def ollama_status() -> dict[str, Any]:
    """
    Ollama server and the phi4-mini model separately:
      /api/version  server up?
      /api/tags     model downloaded?
      /api/ps       model loaded in memory right now (answers immediately)?
    """
    out: dict[str, Any] = {"server": False, "version": None, "latency_ms": None, "installed": False,
                           "loaded": False, "size_vram_mb": None, "expires_at": None, "error": None, "model": OLLAMA_MODEL}
    want = OLLAMA_MODEL.split(":")[0]
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            ver = await client.get(f"{OLLAMA_URL}/api/version")
            out["latency_ms"] = _ms(t0)
            out["server"] = ver.status_code == 200
            if not out["server"]:
                out["error"] = f"HTTP {ver.status_code}"
                return out
            out["version"] = ver.json().get("version")
            tags = await client.get(f"{OLLAMA_URL}/api/tags")
            names = [m.get("name", "") for m in tags.json().get("models", [])] if tags.status_code == 200 else []
            out["installed"] = any(n.split(":")[0] == want for n in names)
            ps = await client.get(f"{OLLAMA_URL}/api/ps")
            for m in (ps.json().get("models", []) if ps.status_code == 200 else []):
                if (m.get("name") or m.get("model") or "").split(":")[0] == want:
                    out["loaded"] = True
                    out["size_vram_mb"] = round((m.get("size_vram") or 0) / 1048576)
                    out["expires_at"] = m.get("expires_at")
    except Exception as e:
        out["error"] = type(e).__name__
    return out


async def _check_ollama() -> List[dict]:
    o = await ollama_status()
    server = _service("ollama", "Ollama server (:11434)", o["server"],
                      f"v{o['version']}" if o["server"] else f"unreachable: {o['error']}", o["latency_ms"])
    name = f"AI model {OLLAMA_MODEL}"
    if not o["server"]:
        model = _service("llm", name, False, "not running: Ollama is down", label="Not running")
    elif not o["installed"]:
        model = _service("llm", name, False, f"not installed: run  docker exec eidovia_ollama ollama pull {OLLAMA_MODEL}",
                         label="Not installed")
    elif o["loaded"]:
        model = _service("llm", name, True, f"loaded · {o['size_vram_mb']} MB on GPU" if o["size_vram_mb"] else "loaded (CPU)",
                         label="Running")
    else:
        model = _service("llm", name, True, "installed but not loaded in memory: the next question loads it (slower first answer)",
                         warn=True, label="Not loaded")
    return [server, model]


NGROK_API = os.getenv("NGROK_API_URL", "http://tunnel:4040").rstrip("/")


async def _check_tunnel() -> dict:
    """The ngrok agent (container 'tunnel', API on :4040) and the public URL end to end."""
    name = "Public tunnel (ngrok)"
    public = f"https://{NGROK_DOMAIN}" if NGROK_DOMAIN else None
    agent_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{NGROK_API}/api/tunnels")
        tunnels = res.json().get("tunnels", []) if res.status_code == 200 else []
        agent_ok = res.status_code == 200
        https = [t.get("public_url") for t in tunnels if (t.get("public_url") or "").startswith("https://")]
        if https:
            public = https[0]
    except Exception:
        pass
    if not public:
        return _service("tunnel", name, False, "ngrok agent not reachable and NGROK_DOMAIN not set")
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(f"{public}/health", headers={"ngrok-skip-browser-warning": "1"})
        ok = res.status_code == 200
        return _service("tunnel", name, ok, f"{public} → gateway · HTTP {res.status_code}" + ("" if agent_ok else " · agent API not reachable"),
                        _ms(t0), warn=ok and not agent_ok)
    except Exception as e:
        return _service("tunnel", name, False, f"{public} unreachable from the server: {type(e).__name__}"
                        + (" (agent is online)" if agent_ok else ""), warn=False)


async def _read_requests(r, limit: int = 5000) -> List[dict]:
    if r is None:
        return []
    out = []
    for raw in await r.lrange(REQUEST_LOG_KEY, 0, limit - 1):
        try:
            out.append(json.loads(raw))
        except ValueError:
            pass
    return out


class TechService:
    @staticmethod
    async def get_status() -> dict[str, Any]:
        redis_state, r = await _check_redis()
        gateway, postgres, ollama, tunnel, logger_state = await asyncio.gather(
            _check_gateway(), _check_postgres(), _check_ollama(), _check_tunnel(), _check_logger(r)
        )
        services = [gateway, postgres, redis_state, logger_state, *ollama, tunnel,
                    _service("admin", "Admin panel (FastAPI :8090)", True, "this page")]

        # traffic in the last hour, from the request log
        hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent = [e for e in await _read_requests(r) if (_parse(e.get("ts")) or hour_ago) > hour_ago]
        times = sorted(e.get("ms") or 0 for e in recent)
        online = await TechService.get_logged_in()
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "services": services,
            "services_up": sum(1 for s in services if s["ok"]),
            "logged_in": len(online),
            "active_now": sum(1 for u in online if u["active"]),
            "requests_1h": len(recent),
            "errors_1h": sum(1 for e in recent if (e.get("status") or 0) >= 500),
            "client_errors_1h": sum(1 for e in recent if 400 <= (e.get("status") or 0) < 500),
            "avg_ms_1h": round(sum(times) / len(times), 1) if times else None,
            "p95_ms_1h": times[int(len(times) * 0.95) - 1] if len(times) >= 20 else None,
            "users_1h": len({e.get("user_id") for e in recent if e.get("user_id")}),
        }

    @staticmethod
    async def get_logged_in() -> List[dict[str, Any]]:
        """
        Logged in = last login is newer than last logout and the token (JWT_EXPIRES_MINUTES) has not run out,
        or the user made a request with a valid token and has not logged out since. IP/device = latest request.
        """
        async with db.get_session() as session:
            rows = (await session.execute(text("""
                WITH last AS (
                    SELECT user_id,
                           MAX(created_at) FILTER (WHERE action IN ('login','register')) AS login_at,
                           MAX(created_at) FILTER (WHERE action = 'logout')              AS logout_at,
                           (ARRAY_AGG(details->>'ip' ORDER BY created_at DESC)
                                FILTER (WHERE action IN ('login','register') AND details ? 'ip'))[1]     AS login_ip,
                           (ARRAY_AGG(details->>'device' ORDER BY created_at DESC)
                                FILTER (WHERE action IN ('login','register') AND details ? 'device'))[1] AS login_device
                    FROM audit_logs WHERE action IN ('login','register','logout')
                    GROUP BY user_id
                )
                SELECT l.user_id, u.username, u.is_admin, l.login_at, l.logout_at, l.login_ip, l.login_device
                FROM last l JOIN users u ON u.user_id::text = l.user_id
                WHERE l.login_at IS NOT NULL AND (l.logout_at IS NULL OR l.login_at > l.logout_at)
                  AND l.login_at > now() - make_interval(mins => :mins)
            """), {"mins": JWT_MINUTES})).all()
        users: dict[str, dict] = {}
        for row in rows:
            users[row.user_id] = {
                "user_id": row.user_id, "username": row.username, "is_admin": bool(row.is_admin),
                "logged_in_at": row.login_at.isoformat() if row.login_at else None,
                "ip": row.login_ip, "device": row.login_device, "last_seen": None, "last_request": None,
            }
        try:
            r = await get_redis()
            seen = await r.hgetall(ONLINE_KEY)
        except Exception:
            seen = {}
        now = datetime.now(timezone.utc)
        for uid, raw in seen.items():
            try:
                s = json.loads(raw)
            except ValueError:
                continue
            last = _parse(s.get("last_seen"))
            if last is None or now - last > timedelta(minutes=JWT_MINUTES):
                continue
            u = users.setdefault(uid, {"user_id": uid, "username": s.get("username"), "is_admin": False,
                                       "logged_in_at": None, "ip": None, "device": None})
            u.update(ip=s.get("ip") or u.get("ip"), device=s.get("device") or u.get("device"),
                     last_seen=s.get("last_seen"), last_request=s.get("last_path"))
        for u in users.values():
            last = _parse(u.get("last_seen"))
            u["active"] = bool(last and now - last < timedelta(minutes=ACTIVE_MINUTES))
        return sorted(users.values(), key=lambda u: (not u["active"], u.get("last_seen") or u.get("logged_in_at") or ""), reverse=False)

    @staticmethod
    async def get_requests(limit: int = 300, user: str = "", kind: str = "all", q: str = "") -> List[dict[str, Any]]:
        """Newest first. kind: all | errors (4xx/5xx) | server (5xx) | slow (> 2 s) | chat."""
        try:
            r = await get_redis()
        except Exception:
            return []
        user, q = user.strip().lower(), q.strip().lower()
        out = []
        for e in await _read_requests(r):
            status = e.get("status") or 0
            if kind == "errors" and status < 400:
                continue
            if kind == "server" and status < 500:
                continue
            if kind == "slow" and (e.get("ms") or 0) < 2000:
                continue
            if kind == "chat" and not (e.get("path") or "").startswith("/api/chat"):
                continue
            if user and user not in (e.get("username") or "").lower() and user != (e.get("user_id") or ""):
                continue
            if q and q not in " ".join(str(e.get(k) or "") for k in ("path", "upstream", "ip", "device", "detail", "error", "id")).lower():
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    async def requests_for_user(user_id: str, limit: int = 500) -> List[dict[str, Any]]:
        try:
            r = await get_redis()
        except Exception:
            return []
        return [e for e in await _read_requests(r) if e.get("user_id") == user_id][:limit]
