from __future__ import annotations

import json
from datetime import datetime
from ipaddress import ip_address
from uuid import UUID, uuid4

import pytest
from app.core.security import (
    hash_password,
    hash_refresh_token,
)
from app.db.models.enums import AuditOutcome
from app.db.models.identity import User
from app.db.models.reporting import AuditLog
from app.modules.audit.actions import AuditAction
from app.modules.auth.exceptions import (
    AuthenticationRejectedError,
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
    AuthResponse,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
)
from app.modules.auth.service import (
    AccessSessionContext,
    AuthenticationService,
    LoginContext,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_PASSWORD = "Audit-Events-Test-Password-123!"

WRONG_PASSWORD = "Wrong-Audit-Password-123!"


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

        raise AssertionError("MFA should not be used in these audit tests")

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


def _context(
    correlation_id: str | None = None,
) -> LoginContext:
    return LoginContext(
        correlation_id=(correlation_id or str(uuid4())),
        source_ip="127.0.0.1",
        user_agent="pytest-audit-events",
    )


async def _create_user(
    session: AsyncSession,
) -> User:
    suffix = uuid4().hex[:12]

    repository = UserRepository(session)

    user = await repository.create(
        email=(f"audit-{suffix}@example.test"),
        username=f"audit_{suffix}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="Audit",
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


async def _events_for_correlation(
    session: AsyncSession,
    correlation_id: str,
) -> list[AuditLog]:
    statement = (
        select(AuditLog)
        .where(AuditLog.correlation_id == correlation_id)
        .order_by(
            AuditLog.occurred_at,
            AuditLog.id,
        )
    )

    result = await session.scalars(statement)

    return list(result.all())


@pytest.mark.asyncio
async def test_failed_login_writes_safe_audit_event(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    correlation_id = str(uuid4())

    with pytest.raises(AuthenticationRejectedError):
        await service.login(
            LoginRequest(
                identifier=user.email,
                password=WRONG_PASSWORD,
            ),
            _context(correlation_id),
        )

    events = await _events_for_correlation(
        db_session,
        correlation_id,
    )

    assert len(events) == 1

    event = events[0]

    assert event.action == (AuditAction.AUTH_LOGIN_FAILED.value)
    assert event.outcome == (AuditOutcome.FAILURE)
    assert event.actor_user_id == user.id
    assert event.resource_id == user.id
    assert event.source_ip == ip_address("127.0.0.1")

    details = event.details or {}

    assert details["reason"] == ("invalid_password")
    assert "identifier_fingerprint" in details

    serialized_details = json.dumps(details).casefold()

    assert user.email.casefold() not in (serialized_details)
    assert TEST_PASSWORD.casefold() not in (serialized_details)
    assert WRONG_PASSWORD.casefold() not in (serialized_details)


@pytest.mark.asyncio
async def test_unknown_user_login_audit_has_no_actor(
    db_session: AsyncSession,
) -> None:
    service = _service(db_session)
    correlation_id = str(uuid4())

    unknown_email = f"missing-{uuid4().hex}@example.test"

    with pytest.raises(AuthenticationRejectedError):
        await service.login(
            LoginRequest(
                identifier=unknown_email,
                password=WRONG_PASSWORD,
            ),
            _context(correlation_id),
        )

    events = await _events_for_correlation(
        db_session,
        correlation_id,
    )

    assert len(events) == 1

    event = events[0]

    assert event.action == (AuditAction.AUTH_LOGIN_FAILED.value)
    assert event.actor_user_id is None
    assert event.resource_id is None
    assert event.details["reason"] == ("user_not_found")


@pytest.mark.asyncio
async def test_successful_login_and_refresh_are_audited(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    login_correlation_id = str(uuid4())

    login_result = await service.login(
        LoginRequest(
            identifier=user.email,
            password=TEST_PASSWORD,
        ),
        _context(login_correlation_id),
    )

    assert isinstance(
        login_result,
        AuthResponse,
    )

    login_events = await _events_for_correlation(
        db_session,
        login_correlation_id,
    )

    assert len(login_events) == 1

    login_event = login_events[0]

    assert login_event.action == (AuditAction.AUTH_LOGIN_SUCCEEDED.value)
    assert login_event.outcome == (AuditOutcome.SUCCESS)
    assert login_event.actor_user_id == user.id

    refresh_correlation_id = str(uuid4())

    await service.refresh(
        RefreshTokenRequest(refresh_token=(login_result.tokens.refresh_token)),
        _context(refresh_correlation_id),
    )

    refresh_events = await _events_for_correlation(
        db_session,
        refresh_correlation_id,
    )

    assert any(
        event.action == AuditAction.AUTH_TOKEN_REFRESHED.value
        and event.outcome == AuditOutcome.SUCCESS
        for event in refresh_events
    )


@pytest.mark.asyncio
async def test_refresh_token_reuse_is_audited(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    login_result = await service.login(
        LoginRequest(
            identifier=user.email,
            password=TEST_PASSWORD,
        ),
        _context(),
    )

    assert isinstance(
        login_result,
        AuthResponse,
    )

    original_refresh_token = login_result.tokens.refresh_token

    await service.refresh(
        RefreshTokenRequest(refresh_token=(original_refresh_token)),
        _context(),
    )

    reuse_correlation_id = str(uuid4())

    with pytest.raises(RefreshTokenReuseDetectedError):
        await service.refresh(
            RefreshTokenRequest(refresh_token=(original_refresh_token)),
            _context(reuse_correlation_id),
        )

    events = await _events_for_correlation(
        db_session,
        reuse_correlation_id,
    )

    assert any(
        event.action == (AuditAction.AUTH_REFRESH_REUSE_DETECTED.value)
        and event.outcome == AuditOutcome.DENIED
        for event in events
    )


@pytest.mark.asyncio
async def test_logout_all_is_audited(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    login_result = await service.login(
        LoginRequest(
            identifier=user.email,
            password=TEST_PASSWORD,
        ),
        _context(),
    )

    assert isinstance(
        login_result,
        AuthResponse,
    )

    refresh_token = login_result.tokens.refresh_token

    sessions = AuthSessionRepository(db_session)

    auth_session = await sessions.get_by_refresh_hash(hash_refresh_token(refresh_token))

    assert auth_session is not None

    correlation_id = str(uuid4())

    access_context = AccessSessionContext(
        user_id=user.id,
        session_id=auth_session.id,
        access_token_jti=uuid4(),
        access_token_expires_at=(login_result.tokens.access_token_expires_at),
        correlation_id=correlation_id,
        source_ip="127.0.0.1",
        user_agent="pytest-audit-events",
    )

    await service.logout(
        LogoutRequest(all_sessions=True),
        access_context,
    )

    events = await _events_for_correlation(
        db_session,
        correlation_id,
    )

    assert any(
        event.action == AuditAction.AUTH_LOGOUT_ALL.value and event.outcome == AuditOutcome.SUCCESS
        for event in events
    )


@pytest.mark.asyncio
async def test_account_lock_event_is_written_at_threshold(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    service = _service(db_session)

    maximum_attempts = service.settings.auth_max_failed_attempts

    payload = LoginRequest(
        identifier=user.email,
        password=WRONG_PASSWORD,
    )

    for _ in range(maximum_attempts - 1):
        with pytest.raises(AuthenticationRejectedError):
            await service.login(
                payload,
                _context(),
            )

    final_correlation_id = str(uuid4())

    with pytest.raises(AuthenticationRejectedError):
        await service.login(
            payload,
            _context(final_correlation_id),
        )

    events = await _events_for_correlation(
        db_session,
        final_correlation_id,
    )

    actions = {event.action for event in events}

    assert AuditAction.AUTH_LOGIN_FAILED.value in actions
    assert AuditAction.AUTH_ACCOUNT_LOCKED.value in actions
