from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.security import (
    create_refresh_token,
    hash_password,
)
from app.db.models.identity import Role
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.rbac.repository import (
    RBACRepository,
)
from app.modules.users.schemas import (
    UserCreateRequest,
)
from app.modules.users.service import (
    UserManagementContext,
    UserManagementService,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_PASSWORD = "User-Management-Test-Password-123!"


def _context(
    actor_user_id,
) -> UserManagementContext:
    return UserManagementContext(
        actor_user_id=actor_user_id,
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest-user-management",
    )


@pytest.mark.asyncio
async def test_administrator_can_create_user_with_role(
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    rbac = RBACRepository(db_session)

    actor = await users.create(
        email=f"actor-{uuid4().hex}@example.test",
        username=f"actor_{uuid4().hex[:10]}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="Admin",
        last_name="Actor",
        is_active=True,
    )

    roles_result = await db_session.scalars(select(Role).order_by(Role.name))

    roles = list(roles_result.all())

    assert roles, "No RBAC roles were found. Run the RBAC seed migration."

    role = next(
        (candidate for candidate in roles if candidate.name.casefold() != "administrator"),
        roles[0],
    )

    assert role is not None

    service = UserManagementService(db_session)

    payload = UserCreateRequest(
        email=f"user-{uuid4().hex}@example.test",
        username=f"user_{uuid4().hex[:10]}",
        password=TEST_PASSWORD,
        first_name="Created",
        last_name="User",
        role_ids=[role.id],
    )

    created = await service.create_user(
        payload=payload,
        context=_context(actor.id),
    )

    assert created.id is not None
    assert created.is_active is True

    has_role = await rbac.user_has_role(
        user_id=created.id,
        role_id=role.id,
        now=datetime.now(UTC),
    )

    assert has_role is True


@pytest.mark.asyncio
async def test_deactivating_user_revokes_sessions(
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    sessions = AuthSessionRepository(db_session)

    actor = await users.create(
        email=f"actor-{uuid4().hex}@example.test",
        username=f"actor_{uuid4().hex[:10]}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="Admin",
        last_name="Actor",
        is_active=True,
    )

    target = await users.create(
        email=f"target-{uuid4().hex}@example.test",
        username=f"target_{uuid4().hex[:10]}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="Target",
        last_name="User",
        is_active=True,
    )

    refresh_token = create_refresh_token(now=datetime.now(UTC))

    auth_session = await sessions.create(
        user_id=target.id,
        refresh_token_hash=(refresh_token.token_hash),
        token_jti=refresh_token.jti,
        expires_at=(datetime.now(UTC) + timedelta(days=7)),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    await db_session.commit()

    service = UserManagementService(db_session)

    updated = await service.set_active_status(
        user_id=target.id,
        is_active=False,
        context=_context(actor.id),
    )

    assert updated.is_active is False

    await db_session.refresh(auth_session)

    assert auth_session.revoked_at is not None
