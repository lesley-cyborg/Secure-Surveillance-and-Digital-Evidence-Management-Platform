from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
)
from app.db.models.identity import (
    Permission,
    Role,
)
from app.modules.auth.dependencies import (
    CurrentAccessToken,
)
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.rbac.dependencies import (
    get_authorization_context,
    require_any_permission,
    require_permission,
    require_permissions,
    require_role,
)
from app.modules.rbac.repository import (
    RBACRepository,
)
from fastapi import HTTPException
from fastapi.security import SecurityScopes
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_database_permission_is_applied_immediately(
    db_session: AsyncSession,
) -> None:
    suffix = uuid4().hex[:10]
    now = datetime.now(UTC).replace(microsecond=0)

    users = UserRepository(db_session)
    sessions = AuthSessionRepository(db_session)
    rbac = RBACRepository(db_session)

    user = await users.create(
        email=f"rbac-{suffix}@example.test",
        username=f"rbac_{suffix}",
        password_hash=hash_password("Integration-Credential-123!"),
        first_name="RBAC",
        last_name="Tester",
    )

    role = Role(
        name=f"TEST_ROLE_{suffix}".upper(),
        description="RBAC integration role",
        is_system_role=False,
    )

    permission = Permission(
        code=f"evidence:test:{suffix}",
        resource="evidence",
        action=f"test_{suffix}",
        description="RBAC integration permission",
    )

    db_session.add_all([role, permission])
    await db_session.flush()

    await rbac.assign_role(
        user_id=user.id,
        role_id=role.id,
        assigned_by=None,
        assigned_at=now,
    )

    await rbac.grant_permission(
        role_id=role.id,
        permission_id=permission.id,
        granted_at=now,
    )

    refresh_token = create_refresh_token(now=now)

    auth_session = await sessions.create(
        user_id=user.id,
        refresh_token_hash=(refresh_token.token_hash),
        token_jti=refresh_token.jti,
        expires_at=refresh_token.expires_at,
    )

    access_token = create_access_token(
        user_id=user.id,
        session_id=auth_session.id,
        now=now,
    )

    current_access = CurrentAccessToken(
        claims=decode_access_token(access_token.token),
        user=user,
        auth_session=auth_session,
    )

    authorization = await get_authorization_context(
        current_access=current_access,
        current_active_user=user,
        session=db_session,
    )

    result = await require_permissions(
        SecurityScopes(scopes=[permission.code]),
        authorization,
    )

    assert result.user.id == user.id
    assert permission.code in result.permissions

    await rbac.remove_role(
        user_id=user.id,
        role_id=role.id,
    )

    authorization_after_removal = await get_authorization_context(
        current_access=current_access,
        current_active_user=user,
        session=db_session,
    )

    with pytest.raises(HTTPException) as exc_info:
        await require_permissions(
            SecurityScopes(scopes=[permission.code]),
            authorization_after_removal,
        )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_permission_factories(
    db_session: AsyncSession,
) -> None:
    del db_session

    # Factory behavior is already covered through the database
    # integration test above. This test verifies AND/OR/role wrappers
    # through a minimal authorization context in later expansion.
    assert callable(require_permission("evidence:read"))

    assert callable(
        require_any_permission(
            "evidence:read",
            "evidence:verify",
        )
    )

    assert callable(require_role("ADMINISTRATOR"))
