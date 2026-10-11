from fastapi import APIRouter

from routers.dashboard import router as dashboard_router
from routers.users import router as users_router
from routers.support import router as support_router
from routers.system import router as system_router
from routers.audit import router as audit_router

admin_router = APIRouter(prefix="/admin")

# Mount modular sub-routers
admin_router.include_router(dashboard_router)
admin_router.include_router(users_router)
admin_router.include_router(support_router)
admin_router.include_router(system_router)
admin_router.include_router(audit_router)

__all__ = ["admin_router"]
