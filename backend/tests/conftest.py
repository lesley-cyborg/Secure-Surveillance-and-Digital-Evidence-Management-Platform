from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
)

# These must exist before importing any application modules.
# setdefault preserves real values supplied by your environment.
os.environ.setdefault(
    "DATABASE_URL",
    ("postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/secure_surveillance_test"),
)
os.environ.setdefault(
    "REDIS_URL",
    "redis://127.0.0.1:6379/15",
)
os.environ.setdefault(
    "JWT_SECRET_KEY",
    ("phase-6-testing-jwt-secret-key-not-for-production-use-0123456789"),
)
os.environ.setdefault(
    "AI_INGESTION_ENABLED",
    "false",
)

import pytest
import pytest_asyncio
from app.core.config import get_settings
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()

    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for database integration tests")

    test_engine = create_async_engine(
        settings.test_database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={
            "ssl": False,
            "timeout": 30.0,
        },
    )

    connection = await connect_with_retry(test_engine)

    try:
        outer_transaction = await connection.begin()

        session_factory = async_sessionmaker(
            bind=connection,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
            join_transaction_mode="create_savepoint",
        )

        async with session_factory() as session:
            yield session

        if outer_transaction.is_active:
            await outer_transaction.rollback()

    finally:
        await connection.close()
        await test_engine.dispose()


async def connect_with_retry(
    engine: AsyncEngine,
    *,
    attempts: int = 4,
) -> AsyncConnection:
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return await engine.connect()

        except (
            TimeoutError,
            ConnectionError,
            OSError,
            DBAPIError,
        ) as exc:
            last_error = exc

            if attempt == attempts:
                raise

            await asyncio.sleep(0.75 * attempt)

    raise RuntimeError("PostgreSQL connection retries exhausted") from last_error
