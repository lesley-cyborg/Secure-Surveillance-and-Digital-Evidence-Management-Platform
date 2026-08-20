from fastapi import APIRouter

from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.cameras.router import router as cameras_router
from app.modules.custody.router import router as custody_router
from app.modules.evidence.router import router as evidence_router
from app.modules.health.router import router as health_router
from app.modules.incidents.router import router as incidents_router
from app.modules.notifications.router import router as notifications_router
from app.modules.reports.router import router as reports_router
from app.modules.users.router import router as users_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(cameras_router)
api_router.include_router(incidents_router)
api_router.include_router(evidence_router)
api_router.include_router(custody_router)
api_router.include_router(reports_router)
api_router.include_router(notifications_router)
api_router.include_router(audit_router)
