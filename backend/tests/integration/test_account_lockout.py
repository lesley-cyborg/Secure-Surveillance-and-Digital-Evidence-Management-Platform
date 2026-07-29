from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.core.security import hash_password
from app.db.models.identity import User
from app.modules.auth.exceptions import (
    AuthenticationRejectedError,
)
from app.modules.auth.mfa_store import (
    IssuedMfaChallenge,
    MfaChallenge,
)
from app.modules.auth.repository import (
    UserRepository,
)
from app.modules.auth.schemas import (
    AuthResponse,
    LoginRequest,
)
from app.modules.auth.service import (
    AuthenticationService,
    LoginContext,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_PASSWORD = "Account-Lockout-Test-Password-123!"

WRONG_PASSWORD = "Incorrect-Account-Password-123!"


class _NoopMfaChallengeStore:
    async def issue(
        self,
        *,
        user_id: UUID,
        correlation_id: str,
        source_ip: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> IssuedMfaChallenge:
        del user_id
        del correlation_id
        del source_ip
        del user_agent
        del now

        raise AssertionError("MFA should not be used in account-lockout tests")

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

    async def delete(
        self,
        challenge_id: UUID,
    ) -> None:
        del challenge_id


def _context() -> LoginContext:
    return LoginContext(
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest-account-lockout",
    )


async def _create_user(
    session: AsyncSession,
) -> User:
    suffix = uuid4().hex[:12]

    repository = UserRepository(session)

    user = await repository.create(
        email=(f"lockout-{suffix}@example.test"),
        username=f"lockout_{suffix}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="Lockout",
        last_name="Tester",
        is_active=True,
    )

    user.mfa_enabled = False

    await session.commit()

    return user


def _service(
    session: AsyncSession,
) -> AuthenticationService:
    return AuthenticationService(
        session=session,
        mfa_challenges=(_NoopMfaChallengeStore()),
    )


@pytest.mark.asyncio
async def test_account_is_locked_after_maximum_failed_attempts(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    maximum_attempts = service.settings.auth_max_failed_attempts

    payload = LoginRequest(
        identifier=user.email,
        password=WRONG_PASSWORD,
    )

    for _ in range(maximum_attempts):
        with pytest.raises(AuthenticationRejectedError):
            await service.login(
                payload,
                _context(),
            )

    await db_session.refresh(user)

    assert user.failed_login_attempts == (maximum_attempts)
    assert user.locked_until is not None
    assert user.locked_until > datetime.now(UTC)

    maximum_expected_lock = datetime.now(UTC) + timedelta(
        minutes=(service.settings.auth_lockout_minutes),
        seconds=30,
    )

    assert user.locked_until <= maximum_expected_lock

    # A correct password must still be rejected
    # while the account lock is active.
    with pytest.raises(AuthenticationRejectedError):
        await service.login(
            LoginRequest(
                identifier=user.email,
                password=TEST_PASSWORD,
            ),
            _context(),
        )

    await db_session.refresh(user)

    assert user.last_login_at is None
    assert user.failed_login_attempts == (maximum_attempts)


@pytest.mark.asyncio
async def test_successful_login_clears_expired_lockout_state(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    user.failed_login_attempts = service.settings.auth_max_failed_attempts
    user.locked_until = datetime.now(UTC) - timedelta(minutes=1)

    await db_session.commit()

    result = await service.login(
        LoginRequest(
            identifier=user.email,
            password=TEST_PASSWORD,
        ),
        _context(),
    )

    assert isinstance(result, AuthResponse)

    await db_session.refresh(user)

    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login_at is not None
