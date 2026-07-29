from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db_session
from app.modules.health.schemas import LivenessResponse, ReadinessResponse
from app.modules.health.service import check_database, check_redis

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/live", response_model=LivenessResponse, operation_id="healthLiveness")
async def liveness() -> LivenessResponse:
    settings = get_settings()
    return LivenessResponse(service=settings.app_name)


@router.get("/ready", response_model=ReadinessResponse, operation_id="healthReadiness")
async def readiness(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> ReadinessResponse | JSONResponse:
    settings = get_settings()
    redis: Redis = request.app.state.redis
    dependencies = {
        "postgresql": await check_database(session),
        "redis": await check_redis(redis),
    }
    ready = all(item.status == "up" for item in dependencies.values())
    payload = ReadinessResponse(
        status="ready" if ready else "not_ready",
        service=settings.app_name,
        dependencies=dependencies,
    )
    if ready:
        return payload
    return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=payload.model_dump())
