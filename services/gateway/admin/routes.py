import logging
import asyncio
import json
from typing import List, Any
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from sqlalchemy import text
from app.deps import CurrentUser, get_current_user
from app.db import db
from app.security import decode_access_token
from app.repositories import get_user_profile
from app.logger_client import get_redis

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(current_user: CurrentUser = Depends(get_current_user)):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

@router.get("/logs")
async def get_logs(current_user: CurrentUser = Depends(require_admin)) -> List[dict[str, Any]]:
    """API endpoint to get audit logs."""
    async with db.get_session() as session:
        result = await session.execute(
            text("""
                SELECT id, user_id, username, action, details, created_at
                FROM audit_logs
                ORDER BY created_at DESC
                LIMIT 100
            """)
        )
        logs = []
        for row in result.all():
            logs.append({
                "id": str(row.id),
                "user_id": row.user_id,
                "username": row.username or "unknown",
                "action": row.action,
                "details": row.details,
                "created_at": row.created_at.isoformat() if row.created_at else None
            })
        return logs

@router.websocket("/ws")
async def websocket_logs(websocket: WebSocket, token: str):
    """Realtime WebSocket logs."""
    await websocket.accept()
    try:
        user_id = decode_access_token(token)
        async with db.get_session() as session:
            profile = await get_user_profile(session, user_id)
            if not profile or not profile.get("is_admin"):
                await websocket.close(code=1008)
                return
    except Exception:
        await websocket.close(code=1008)
        return

    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("realtime_logs")

    async def reader():
        try:
            while True:
                # Wait for any client message (which we ignore), mainly to detect disconnects.
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass

    async def writer():
        try:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message:
                    await websocket.send_text(message["data"])
        except Exception:
            pass

    # Run both concurrently, if either fails/exits, cancel the other.
    read_task = asyncio.create_task(reader())
    write_task = asyncio.create_task(writer())
    
    done, pending = await asyncio.wait(
        [read_task, write_task],
        return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()
        
    await pubsub.unsubscribe("realtime_logs")
    await pubsub.close()


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Admin Dashboard</title>
        <style>
            body { font-family: sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { text-align: left; padding: 8px; border-bottom: 1px solid #ddd; }
            th { background-color: #f2f2f2; }
            #login-section { margin-bottom: 20px; }
            .realtime-pulse { 
                display: inline-block; width: 10px; height: 10px; border-radius: 50%;
                background-color: red; margin-right: 5px;
            }
            .connected { background-color: green; }
        </style>
    </head>
    <body>
        <h1><span id="status-dot" class="realtime-pulse"></span>Admin Dashboard - System Logs</h1>
        
        <div id="login-section">
            <input type="text" id="username" placeholder="Username" value="admin">
            <input type="password" id="password" placeholder="Password" value="secretpassword">
            <button onclick="login()">Login & Load Logs</button>
        </div>

        <div id="logs-container" style="display:none;">
            <p style="color: green;">Logged in successfully! Real-time logs are streaming.</p>
            <table id="logs-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Username</th>
                        <th>Action</th>
                        <th>Details</th>
                    </tr>
                </thead>
                <tbody>
                </tbody>
            </table>
        </div>

        <script>
            let jwtToken = '';
            let ws;

            async function login() {
                const u = document.getElementById('username').value;
                const p = document.getElementById('password').value;
                try {
                    const res = await fetch('/api/auth/login', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({username: u, password: p})
                    });
                    if (!res.ok) {
                        alert("Login failed");
                        return;
                    }
                    const data = await res.json();
                    jwtToken = data.token;
                    document.getElementById('login-section').style.display = 'none';
                    document.getElementById('logs-container').style.display = 'block';
                    
                    // Fetch historical logs
                    await fetchLogs();
                    // Connect WebSocket for real-time
                    connectWebSocket();
                } catch(e) { alert(e.message); }
            }

            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = protocol + '//' + window.location.host + '/admin/ws?token=' + jwtToken;
                ws = new WebSocket(wsUrl);
                
                ws.onopen = () => {
                    document.getElementById('status-dot').classList.add('connected');
                };
                
                ws.onmessage = (event) => {
                    const log = JSON.parse(event.data);
                    const tbody = document.querySelector('#logs-table tbody');
                    const tr = document.createElement('tr');
                    tr.style.backgroundColor = '#e6ffe6';
                    tr.innerHTML = `
                        <td>${new Date(log.created_at).toLocaleString()}</td>
                        <td>${log.username}</td>
                        <td>${log.action}</td>
                        <td><pre>${JSON.stringify(log.details, null, 2)}</pre></td>
                    `;
                    tbody.insertBefore(tr, tbody.firstChild);
                    
                    // Remove highlight after a moment
                    setTimeout(() => tr.style.backgroundColor = '', 2000);
                };
                
                ws.onclose = () => {
                    document.getElementById('status-dot').classList.remove('connected');
                    setTimeout(connectWebSocket, 5000); // Reconnect
                };
            }

            async function fetchLogs() {
                try {
                    const response = await fetch('/admin/logs', {
                        headers: {
                            'Authorization': 'Bearer ' + jwtToken
                        }
                    });
                    if (!response.ok) {
                        alert("Failed to fetch logs.");
                        return;
                    }
                    const logs = await response.json();
                    const tbody = document.querySelector('#logs-table tbody');
                    tbody.innerHTML = '';
                    logs.forEach(log => {
                        const tr = document.createElement('tr');
                        tr.innerHTML = `
                            <td>${new Date(log.created_at).toLocaleString()}</td>
                            <td>${log.username}</td>
                            <td>${log.action}</td>
                            <td><pre>${JSON.stringify(log.details, null, 2)}</pre></td>
                        `;
                        tbody.appendChild(tr);
                    });
                } catch (e) {
                    alert("Error: " + e.message);
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
