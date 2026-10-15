from fastapi import APIRouter

from routers.dashboard import router as dashboard_router
from routers.users import router as users_router
from routers.support import router as support_router
from routers.system import router as system_router
from routers.audit import router as audit_router
from routers.ar_game import router as ar_game_router
from routers.tech import router as tech_router
from routers.quiz import router as quiz_router
from routers.accounts import router as accounts_router

admin_router = APIRouter(prefix="/admin")

# Mount modular sub-routers
admin_router.include_router(dashboard_router)
admin_router.include_router(users_router)
admin_router.include_router(support_router)
admin_router.include_router(system_router)
admin_router.include_router(audit_router)
admin_router.include_router(ar_game_router)
admin_router.include_router(tech_router)
admin_router.include_router(quiz_router)
admin_router.include_router(accounts_router)

__all__ = ["admin_router"]
