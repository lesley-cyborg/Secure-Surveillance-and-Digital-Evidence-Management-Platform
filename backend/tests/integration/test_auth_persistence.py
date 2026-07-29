from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.security import (
    create_refresh_token,
    hash_password,
)
from app.db.models.enums import AuditOutcome
from app.db.models.identity import Permission, Role, User
from app.modules.audit.repository import AuditRepository
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.rbac.repository import RBACRepository
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


async def create_test_user(
    session: AsyncSession,
) -> tuple[UserRepository, User]:
    suffix = uuid4().hex[:10]
    repository = UserRepository(session)

    user = await repository.create(
        email=f"auth-{suffix}@example.test",
        username=f"auth_{suffix}",
        password_hash=hash_password("Integration-Test-Credential-123!"),
        first_name="Integration",
        last_name="User",
    )

    return repository, user


@pytest.mark.asyncio
async def test_user_authentication_state_persistence(
    db_session: AsyncSession,
) -> None:
    repository, created = await create_test_user(db_session)

    loaded = await repository.get_by_identifier_for_update(created.email.upper())

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.failed_login_attempts == 0

    locked_until = utc_now() + timedelta(minutes=15)

    await repository.record_failed_login(
        loaded,
        locked_until=locked_until,
    )

    assert loaded.failed_login_attempts == 1
    assert loaded.locked_until == locked_until

    logged_in_at = utc_now()

    await repository.record_successful_login(
        loaded,
        logged_in_at=logged_in_at,
    )

    assert loaded.failed_login_attempts == 0
    assert loaded.locked_until is None
    assert loaded.last_login_at == logged_in_at


@pytest.mark.asyncio
async def test_refresh_session_rotation_persistence(
    db_session: AsyncSession,
) -> None:
    _, user = await create_test_user(db_session)
    repository = AuthSessionRepository(db_session)

    original_token = create_refresh_token()

    original_session = await repository.create(
        user_id=user.id,
        refresh_token_hash=original_token.token_hash,
        token_jti=original_token.jti,
        expires_at=original_token.expires_at,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    locked_session = await repository.get_by_refresh_hash_for_update(original_token.token_hash)

    assert locked_session is not None
    assert locked_session.id == original_session.id

    replacement_token = create_refresh_token(family_id=original_token.family_id)
    rotated_at = utc_now()

    replacement_session = await repository.rotate(
        current_session=locked_session,
        new_refresh_token_hash=(replacement_token.token_hash),
        new_token_jti=replacement_token.jti,
        new_expires_at=replacement_token.expires_at,
        rotated_at=rotated_at,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert original_session.revoked_at == rotated_at
    assert original_session.replaced_by_session_id == replacement_session.id
    assert replacement_session.revoked_at is None
    assert replacement_session.user_id == original_session.user_id


@pytest.mark.asyncio
async def test_rbac_access_snapshot(
    db_session: AsyncSession,
) -> None:
    _, user = await create_test_user(db_session)
    repository = RBACRepository(db_session)
    now = utc_now()
    suffix = uuid4().hex[:10]

    role = Role(
        name=f"TEST_ROLE_{suffix}",
        description="Integration test role",
        is_system_role=False,
    )
    permission = Permission(
        code=f"test:{suffix}:read",
        resource=f"test_{suffix}",
        action="read",
        description="Integration test permission",
    )

    db_session.add_all([role, permission])
    await db_session.flush()

    await repository.assign_role(
        user_id=user.id,
        role_id=role.id,
        assigned_by=None,
        assigned_at=now,
    )

    await repository.grant_permission(
        role_id=role.id,
        permission_id=permission.id,
        granted_at=now,
    )

    snapshot = await repository.get_access_snapshot(
        user_id=user.id,
        now=now,
    )

    assert role.name in snapshot.role_names
    assert permission.code in snapshot.permission_codes
    assert snapshot.has_role(role.name) is True
    assert snapshot.has_permission(permission.code) is True


@pytest.mark.asyncio
async def test_audit_event_persistence(
    db_session: AsyncSession,
) -> None:
    _, user = await create_test_user(db_session)
    repository = AuditRepository(db_session)

    # The repository supports your project's actual AuditOutcome enum.
    # Select one existing member without assuming its member names.
    outcome = next(iter(AuditOutcome))

    audit_log = await repository.create(
        actor_user_id=user.id,
        action="AUTH_PERSISTENCE_TEST",
        resource_type="auth_session",
        resource_id=None,
        outcome=outcome,
        source_ip="127.0.0.1",
        user_agent="pytest",
        correlation_id=str(uuid4()),
        details={
            "environment": "test",
            "source": "pytest",
        },
        occurred_at=utc_now(),
    )

    assert audit_log.id is not None
    assert audit_log.actor_user_id == user.id
    assert audit_log.action == "AUTH_PERSISTENCE_TEST"
    assert audit_log.details["source"] == "pytest"
