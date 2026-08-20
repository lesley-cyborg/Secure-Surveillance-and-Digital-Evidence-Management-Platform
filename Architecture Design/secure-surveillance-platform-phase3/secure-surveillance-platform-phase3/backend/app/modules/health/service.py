from __future__ import annotations

from time import perf_counter

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.health.schemas import DependencyStatus


async def check_database(session: AsyncSession) -> DependencyStatus:
    started = perf_counter()
    try:
        await session.execute(text("SELECT 1"))
        return DependencyStatus(status="up", latency_ms=(perf_counter() - started) * 1000)
    except Exception as exc:
        return DependencyStatus(status="down", detail=type(exc).__name__)


async def check_redis(redis: Redis) -> DependencyStatus:
    started = perf_counter()
    try:
        await redis.ping()
        return DependencyStatus(status="up", latency_ms=(perf_counter() - started) * 1000)
    except Exception as exc:
        return DependencyStatus(status="down", detail=type(exc).__name__)
