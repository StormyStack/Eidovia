import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["admin-dashboard"])

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates", "dashboard.html")


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard() -> HTMLResponse:
    """Serve the enterprise Admin Center interactive single-page application."""
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)
