from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from app.core.security import (
    create_refresh_token,
    hash_password,
    hash_refresh_token,
)
from app.db.models.identity import AuthSession
from app.modules.auth.exceptions import (
    RefreshTokenReuseDetectedError,
)
from app.modules.auth.mfa_store import (
    IssuedMfaChallenge,
    MfaChallenge,
)
from app.modules.auth.repository import (
    AuthSessionRepository,
    UserRepository,
)
from app.modules.auth.schemas import (
    LogoutRequest,
    RefreshTokenRequest,
)
from app.modules.auth.service import (
    AccessSessionContext,
    AuthenticationService,
    LoginContext,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


class FakeMfaStore:
    async def issue(
        self,
        *,
        user_id: UUID,
        correlation_id: str,
        source_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> IssuedMfaChallenge:
        del user_id, correlation_id, source_ip, user_agent, now
        raise AssertionError("MFA should not run in token tests")

    async def consume(
        self,
        *,
        challenge_id: UUID,
        submitted_code: str,
        now: datetime,
    ) -> MfaChallenge | None:
        del challenge_id, submitted_code, now
        raise AssertionError("MFA verification should not run in token tests")

    async def delete(
        self,
        challenge_id: UUID,
    ) -> None:
        del challenge_id


class FakeRevocationStore:
    def __init__(self) -> None:
        self.access_jtis: list[UUID] = []
        self.session_ids: list[UUID] = []

    async def revoke_access_token(
        self,
        *,
        jti: UUID,
        expires_at: datetime,
        now: datetime,
    ) -> None:
        del expires_at, now
        self.access_jtis.append(jti)

    async def revoke_session(
        self,
        session_id: UUID,
    ) -> None:
        self.session_ids.append(session_id)

    async def revoke_sessions(
        self,
        session_ids: list[UUID],
    ) -> None:
        self.session_ids.extend(session_ids)

    async def is_revoked(
        self,
        *,
        jti: UUID,
        session_id: UUID,
    ) -> bool:
        return jti in self.access_jtis or session_id in self.session_ids


def request_context() -> LoginContext:
    return LoginContext(
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest",
    )


@pytest.mark.asyncio
async def test_refresh_rotates_session(
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    sessions = AuthSessionRepository(db_session)

    user = await users.create(
        email=f"{uuid4()}@example.test",
        username=f"user_{uuid4().hex[:10]}",
        password_hash=hash_password("Integration-Credential-123!"),
        first_name="Token",
        last_name="Tester",
    )

    original = create_refresh_token()

    original_session = await sessions.create(
        user_id=user.id,
        refresh_token_hash=original.token_hash,
        token_jti=original.jti,
        expires_at=original.expires_at,
    )

    revocations = FakeRevocationStore()

    service = AuthenticationService(
        db_session,
        FakeMfaStore(),
        revocations,
    )

    result = await service.refresh(
        RefreshTokenRequest(refresh_token=original.token),
        request_context(),
    )

    await db_session.refresh(original_session)

    assert original_session.revoked_at is not None
    assert original_session.replaced_by_session_id is not None
    assert original_session.id in revocations.session_ids
    assert hash_refresh_token(result.refresh_token) != original.token_hash


@pytest.mark.asyncio
async def test_reused_refresh_token_revokes_chain(
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    sessions = AuthSessionRepository(db_session)

    user = await users.create(
        email=f"{uuid4()}@example.test",
        username=f"user_{uuid4().hex[:10]}",
        password_hash=hash_password("Integration-Credential-123!"),
        first_name="Replay",
        last_name="Tester",
    )

    original = create_refresh_token()

    original_session = await sessions.create(
        user_id=user.id,
        refresh_token_hash=original.token_hash,
        token_jti=original.jti,
        expires_at=original.expires_at,
    )

    revocations = FakeRevocationStore()

    service = AuthenticationService(
        db_session,
        FakeMfaStore(),
        revocations,
    )

    await service.refresh(
        RefreshTokenRequest(refresh_token=original.token),
        request_context(),
    )

    with pytest.raises(RefreshTokenReuseDetectedError):
        await service.refresh(
            RefreshTokenRequest(refresh_token=original.token),
            request_context(),
        )

    await db_session.refresh(original_session)

    replacement = await db_session.get(
        AuthSession,
        original_session.replaced_by_session_id,
    )

    assert replacement is not None
    assert replacement.revoked_at is not None


@pytest.mark.asyncio
async def test_logout_all_revokes_every_session(
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    sessions = AuthSessionRepository(db_session)

    user = await users.create(
        email=f"{uuid4()}@example.test",
        username=f"user_{uuid4().hex[:10]}",
        password_hash=hash_password("Integration-Credential-123!"),
        first_name="Logout",
        last_name="Tester",
    )

    first_token = create_refresh_token()
    second_token = create_refresh_token()

    first = await sessions.create(
        user_id=user.id,
        refresh_token_hash=first_token.token_hash,
        token_jti=first_token.jti,
        expires_at=first_token.expires_at,
    )

    second = await sessions.create(
        user_id=user.id,
        refresh_token_hash=second_token.token_hash,
        token_jti=second_token.jti,
        expires_at=second_token.expires_at,
    )

    revocations = FakeRevocationStore()

    service = AuthenticationService(
        db_session,
        FakeMfaStore(),
        revocations,
    )

    access_jti = uuid4()

    await service.logout(
        LogoutRequest(all_sessions=True),
        AccessSessionContext(
            user_id=user.id,
            session_id=first.id,
            access_token_jti=access_jti,
            access_token_expires_at=(first.expires_at),
            correlation_id=str(uuid4()),
            source_ip="127.0.0.1",
            user_agent="pytest",
        ),
    )

    await db_session.refresh(first)
    await db_session.refresh(second)

    assert first.revoked_at is not None
    assert second.revoked_at is not None
    assert access_jti in revocations.access_jtis
    assert first.id in revocations.session_ids
    assert second.id in revocations.session_ids
