from __future__ import annotations

from uuid import uuid4

import pytest
from app.cli.bootstrap_admin import (
    AdminBootstrapError,
    bootstrap_admin,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_PASSWORD = "Bootstrap-Administrator-Password-123!"


@pytest.mark.asyncio
async def test_bootstrap_creates_first_administrator(
    db_session: AsyncSession,
) -> None:
    suffix = uuid4().hex[:10]

    user_id = await bootstrap_admin(
        db_session,
        email=f"bootstrap-{suffix}@example.test",
        username=f"bootstrap_{suffix}",
        password=TEST_PASSWORD,
        first_name="Bootstrap",
        last_name="Administrator",
    )

    assert user_id


@pytest.mark.asyncio
async def test_bootstrap_refuses_second_administrator(
    db_session: AsyncSession,
) -> None:
    first_suffix = uuid4().hex[:10]

    await bootstrap_admin(
        db_session,
        email=(f"bootstrap-{first_suffix}@example.test"),
        username=f"bootstrap_{first_suffix}",
        password=TEST_PASSWORD,
        first_name="First",
        last_name="Administrator",
    )

    second_suffix = uuid4().hex[:10]

    with pytest.raises(
        AdminBootstrapError,
        match="already exists",
    ):
        await bootstrap_admin(
            db_session,
            email=(f"bootstrap-{second_suffix}@example.test"),
            username=(f"bootstrap_{second_suffix}"),
            password=TEST_PASSWORD,
            first_name="Second",
            last_name="Administrator",
        )
