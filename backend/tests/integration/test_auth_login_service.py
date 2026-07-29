from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.core.config import get_settings
from app.core.security import (
    decode_access_token,
    hash_password,
)
from app.db.models.enums import AuditOutcome
from app.db.models.identity import AuthSession, User
from app.db.models.reporting import AuditLog
from app.modules.audit.actions import AuditAction
from app.modules.auth.exceptions import (
    AuthenticationRejectedError,
)
from app.modules.auth.mfa_store import (
    IssuedMfaChallenge,
    MfaChallenge,
)
from app.modules.auth.repository import UserRepository
from app.modules.auth.schemas import (
    AuthResponse,
    LoginRequest,
    MfaChallengeResponse,
)
from app.modules.auth.service import (
    AuthenticationService,
    LoginContext,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_PASSWORD = "Integration-Credential-123!"


class FakeMfaChallengeStore:
    def __init__(self) -> None:
        self.deleted: list[UUID] = []

    async def issue(
        self,
        *,
        user_id: UUID,
        correlation_id: str,
        source_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> IssuedMfaChallenge:
        del correlation_id
        del source_ip
        del user_agent

        return IssuedMfaChallenge(
            id=uuid4(),
            user_id=user_id,
            expires_at=(now + timedelta(minutes=5)),
            delivery_code="123456",
        )

    async def delete(
        self,
        challenge_id: UUID,
    ) -> None:
        self.deleted.append(challenge_id)


def login_context() -> LoginContext:
    return LoginContext(
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest",
    )

    async def consume(
        self,
        *,
        challenge_id: UUID,
        submitted_code: str,
        now: datetime,
    ) -> MfaChallenge | None:
        del challenge_id
        del submitted_code
        del now

        return None


async def create_login_user(
    session: AsyncSession,
    *,
    mfa_enabled: bool = False,
    is_active: bool = True,
) -> User:
    suffix = uuid4().hex[:10]
    repository = UserRepository(session)

    user = await repository.create(
        email=f"login-{suffix}@example.test",
        username=f"login_{suffix}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="Login",
        last_name="Tester",
        is_active=is_active,
    )

    user.mfa_enabled = mfa_enabled
    await session.flush()

    return user


@pytest.mark.asyncio
async def test_successful_login_creates_session_and_tokens(
    db_session: AsyncSession,
) -> None:
    user = await create_login_user(db_session)

    service = AuthenticationService(
        db_session,
        FakeMfaChallengeStore(),
    )

    result = await service.login(
        LoginRequest(
            identifier=user.email.upper(),
            password=TEST_PASSWORD,
        ),
        login_context(),
    )

    assert isinstance(result, AuthResponse)

    claims = decode_access_token(result.tokens.access_token)

    assert claims.sub == user.id

    stored_session = await db_session.get(
        AuthSession,
        claims.sid,
    )

    assert stored_session is not None
    assert stored_session.user_id == user.id
    assert stored_session.revoked_at is None
    assert stored_session.refresh_token_hash != result.tokens.refresh_token

    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login_at is not None

    audit = await db_session.scalar(
        select(AuditLog)
        .where(
            AuditLog.actor_user_id == user.id,
            AuditLog.action == AuditAction.AUTH_LOGIN_SUCCEEDED.value,
            AuditLog.outcome == AuditOutcome.SUCCESS,
        )
        .order_by(AuditLog.occurred_at.desc())
    )

    assert audit is not None
    assert audit.details["reason"] == "authenticated"


@pytest.mark.asyncio
async def test_invalid_password_locks_at_threshold(
    db_session: AsyncSession,
) -> None:
    settings = get_settings()
    user = await create_login_user(db_session)

    user.failed_login_attempts = settings.auth_max_failed_attempts - 1
    await db_session.flush()

    service = AuthenticationService(
        db_session,
        FakeMfaChallengeStore(),
    )

    with pytest.raises(AuthenticationRejectedError):
        await service.login(
            LoginRequest(
                identifier=user.username,
                password="Incorrect-Credential-999!",
            ),
            login_context(),
        )

    assert user.failed_login_attempts == settings.auth_max_failed_attempts
    assert user.locked_until is not None

    lock_event = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.actor_user_id == user.id,
            AuditLog.action == "AUTH_ACCOUNT_LOCKED",
        )
    )

    assert lock_event is not None
    assert lock_event.outcome == AuditOutcome.DENIED


@pytest.mark.asyncio
async def test_expired_lock_is_cleared_on_login(
    db_session: AsyncSession,
) -> None:
    user = await create_login_user(db_session)

    user.failed_login_attempts = 5
    user.locked_until = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()

    service = AuthenticationService(
        db_session,
        FakeMfaChallengeStore(),
    )

    result = await service.login(
        LoginRequest(
            identifier=user.email,
            password=TEST_PASSWORD,
        ),
        login_context(),
    )

    assert isinstance(result, AuthResponse)
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


@pytest.mark.asyncio
async def test_mfa_user_receives_challenge_not_tokens(
    db_session: AsyncSession,
) -> None:
    user = await create_login_user(
        db_session,
        mfa_enabled=True,
    )

    service = AuthenticationService(
        db_session,
        FakeMfaChallengeStore(),
    )

    result = await service.login(
        LoginRequest(
            identifier=user.email,
            password=TEST_PASSWORD,
        ),
        login_context(),
    )

    assert isinstance(
        result,
        MfaChallengeResponse,
    )
    assert result.mfa_required is True

    session_count = await db_session.scalar(
        select(func.count()).select_from(AuthSession).where(AuthSession.user_id == user.id)
    )

    assert session_count == 0
