from __future__ import annotations

from collections.abc import AsyncIterator

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
        pytest.skip("TEST_DATABASE_URL is required for integration tests")

    test_engine = create_async_engine(
        settings.test_database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
    )

    async with test_engine.connect() as connection:
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

    await test_engine.dispose()
