from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.core.security import hash_password
from app.db.models.identity import (
    AuthSession,
    User,
)
from app.db.models.reporting import AuditLog
from app.modules.audit.actions import AuditAction
from app.modules.auth.dependencies import (
    get_authentication_service,
)
from app.modules.auth.mfa_store import (
    IssuedMfaChallenge,
    MfaChallenge,
)
from app.modules.auth.repository import UserRepository
from app.modules.auth.router import router as auth_router
from app.modules.auth.service import (
    AuthenticationService,
)
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

TEST_PASSWORD = "Mfa-Integration-Credential-123!"

TEST_MFA_CODE = "123456"


@dataclass(frozen=True, slots=True)
class _StoredChallenge:
    """
    Minimal challenge object needed by AuthenticationService.

    It deliberately stores only a digest of the MFA code.
    """

    id: UUID
    user_id: UUID
    expires_at: datetime
    code_digest: str


class InMemoryMfaChallengeStore:
    """
    Deterministic test implementation of MfaChallengeIssuer.

    Production uses Redis. This test implementation preserves the
    important security semantics:

    - expiration
    - constant-time comparison
    - one-time successful consumption
    - no plaintext code stored in the challenge
    """

    def __init__(
        self,
        *,
        code: str = TEST_MFA_CODE,
        lifetime: timedelta = timedelta(minutes=5),
    ) -> None:
        self.code = code
        self.lifetime = lifetime
        self._challenges: dict[
            UUID,
            _StoredChallenge,
        ] = {}

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

        challenge = _StoredChallenge(
            id=uuid4(),
            user_id=user_id,
            expires_at=now + self.lifetime,
            code_digest=self._hash_code(self.code),
        )

        self._challenges[challenge.id] = challenge

        return IssuedMfaChallenge(
            id=challenge.id,
            user_id=challenge.user_id,
            expires_at=challenge.expires_at,
            delivery_code=self.code,
        )

    async def consume(
        self,
        *,
        challenge_id: UUID,
        submitted_code: str,
        now: datetime,
    ) -> MfaChallenge | None:
        challenge = self._challenges.get(challenge_id)

        if challenge is None:
            return None

        if challenge.expires_at <= now:
            self._challenges.pop(
                challenge_id,
                None,
            )
            return None

        submitted_digest = self._hash_code(submitted_code)

        code_valid = hmac.compare_digest(
            submitted_digest,
            challenge.code_digest,
        )

        if not code_valid:
            return None

        # Successful verification consumes the challenge.
        self._challenges.pop(
            challenge_id,
            None,
        )

        return MfaChallenge(
            id=challenge.id,
            user_id=challenge.user_id,
            expires_at=challenge.expires_at,
        )

    async def delete(
        self,
        challenge_id: UUID,
    ) -> None:
        self._challenges.pop(
            challenge_id,
            None,
        )

    def expire(
        self,
        challenge_id: UUID,
    ) -> None:
        challenge = self._challenges[challenge_id]

        self._challenges[challenge_id] = replace(
            challenge,
            expires_at=(datetime.now(UTC) - timedelta(seconds=1)),
        )

    def contains(
        self,
        challenge_id: UUID,
    ) -> bool:
        return challenge_id in self._challenges

    @staticmethod
    def _hash_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def _create_mfa_user(
    session: AsyncSession,
) -> User:
    suffix = uuid4().hex[:10]

    repository = UserRepository(session)

    user = await repository.create(
        email=f"mfa-{suffix}@example.test",
        username=f"mfa_{suffix}",
        password_hash=hash_password(TEST_PASSWORD),
        first_name="MFA",
        last_name="Tester",
    )

    user.mfa_enabled = True

    await session.flush()

    return user


def _create_service(
    session: AsyncSession,
    store: InMemoryMfaChallengeStore,
) -> AuthenticationService:
    return AuthenticationService(
        session=session,
        mfa_challenges=cast(
            IssuedMfaChallenge,
            store,
        ),
    )


def _create_test_app(
    service: AuthenticationService,
) -> FastAPI:
    app = FastAPI()

    app.include_router(
        auth_router,
        prefix="/api/v1",
    )

    app.dependency_overrides[get_authentication_service] = lambda: service

    return app


async def _count_user_sessions(
    session: AsyncSession,
    user_id: UUID,
) -> int:
    statement = select(func.count(AuthSession.id)).where(AuthSession.user_id == user_id)

    result = await session.scalar(statement)

    return int(result or 0)


async def _count_audit_action(
    session: AsyncSession,
    action: AuditAction,
) -> int:
    statement = select(func.count(AuditLog.id)).where(AuditLog.action == action.value)

    result = await session.scalar(statement)

    return int(result or 0)


async def _login(
    client: AsyncClient,
    user: User,
) -> UUID:
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "identifier": user.email,
            "password": TEST_PASSWORD,
        },
        headers={
            "X-Correlation-ID": str(uuid4()),
            "User-Agent": "pytest-mfa",
        },
    )

    assert response.status_code == 202

    body = response.json()

    assert "challengeId" in body
    assert "expiresAt" in body

    return UUID(body["challengeId"])


async def _verify(
    client: AsyncClient,
    *,
    challenge_id: UUID,
    code: str,
):
    return await client.post(
        "/api/v1/auth/mfa/verify",
        json={
            "challengeId": str(challenge_id),
            "code": code,
        },
        headers={
            "X-Correlation-ID": str(uuid4()),
            "User-Agent": "pytest-mfa",
        },
    )


@pytest.mark.asyncio
async def test_password_login_with_mfa_returns_challenge_without_session(
    db_session: AsyncSession,
) -> None:
    user = await _create_mfa_user(db_session)

    store = InMemoryMfaChallengeStore()
    service = _create_service(
        db_session,
        store,
    )
    app = _create_test_app(service)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        challenge_id = await _login(
            client,
            user,
        )

    assert store.contains(challenge_id)

    session_count = await _count_user_sessions(
        db_session,
        user.id,
    )

    # No access or refresh session may be created
    # before MFA verification succeeds.
    assert session_count == 0


@pytest.mark.asyncio
async def test_valid_mfa_code_creates_authenticated_session(
    db_session: AsyncSession,
) -> None:
    user = await _create_mfa_user(db_session)

    store = InMemoryMfaChallengeStore()
    service = _create_service(
        db_session,
        store,
    )
    app = _create_test_app(service)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        challenge_id = await _login(
            client,
            user,
        )

        response = await _verify(
            client,
            challenge_id=challenge_id,
            code=TEST_MFA_CODE,
        )

    assert response.status_code == 200

    body = response.json()

    assert "user" in body
    assert "tokens" in body
    assert body["user"]["id"] == str(user.id)

    assert not store.contains(challenge_id)

    session_count = await _count_user_sessions(
        db_session,
        user.id,
    )

    assert session_count == 1

    await db_session.refresh(user)

    assert user.last_login_at is not None
    assert user.failed_login_attempts == 0
    assert user.locked_until is None

    verification_audits = await _count_audit_action(
        db_session,
        AuditAction.AUTH_MFA_VERIFICATION_SUCCEEDED,
    )

    login_audits = await _count_audit_action(
        db_session,
        AuditAction.AUTH_LOGIN_SUCCEEDED,
    )

    assert verification_audits == 1
    assert login_audits == 1


@pytest.mark.asyncio
async def test_wrong_mfa_code_is_rejected_without_creating_session(
    db_session: AsyncSession,
) -> None:
    user = await _create_mfa_user(db_session)

    store = InMemoryMfaChallengeStore()
    service = _create_service(
        db_session,
        store,
    )
    app = _create_test_app(service)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        challenge_id = await _login(
            client,
            user,
        )

        response = await _verify(
            client,
            challenge_id=challenge_id,
            code="999999",
        )

    assert response.status_code == 401

    body = response.json()

    assert body["detail"]["code"] == ("MFA_VERIFICATION_FAILED")

    session_count = await _count_user_sessions(
        db_session,
        user.id,
    )

    assert session_count == 0

    failed_audits = await _count_audit_action(
        db_session,
        AuditAction.AUTH_MFA_VERIFICATION_FAILED,
    )

    assert failed_audits == 1


@pytest.mark.asyncio
async def test_expired_mfa_challenge_is_rejected(
    db_session: AsyncSession,
) -> None:
    user = await _create_mfa_user(db_session)

    store = InMemoryMfaChallengeStore()
    service = _create_service(
        db_session,
        store,
    )
    app = _create_test_app(service)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        challenge_id = await _login(
            client,
            user,
        )

        store.expire(challenge_id)

        response = await _verify(
            client,
            challenge_id=challenge_id,
            code=TEST_MFA_CODE,
        )

    assert response.status_code == 401

    session_count = await _count_user_sessions(
        db_session,
        user.id,
    )

    assert session_count == 0
    assert not store.contains(challenge_id)


@pytest.mark.asyncio
async def test_consumed_mfa_challenge_cannot_be_reused(
    db_session: AsyncSession,
) -> None:
    user = await _create_mfa_user(db_session)

    store = InMemoryMfaChallengeStore()
    service = _create_service(
        db_session,
        store,
    )
    app = _create_test_app(service)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        challenge_id = await _login(
            client,
            user,
        )

        first_response = await _verify(
            client,
            challenge_id=challenge_id,
            code=TEST_MFA_CODE,
        )

        second_response = await _verify(
            client,
            challenge_id=challenge_id,
            code=TEST_MFA_CODE,
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 401

    session_count = await _count_user_sessions(
        db_session,
        user.id,
    )

    # The replay attempt must not create another session.
    assert session_count == 1


@pytest.mark.asyncio
async def test_inactive_user_cannot_complete_mfa(
    db_session: AsyncSession,
) -> None:
    user = await _create_mfa_user(db_session)

    store = InMemoryMfaChallengeStore()
    service = _create_service(
        db_session,
        store,
    )
    app = _create_test_app(service)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        challenge_id = await _login(
            client,
            user,
        )

        user.is_active = False
        await db_session.flush()
        await db_session.commit()

        response = await _verify(
            client,
            challenge_id=challenge_id,
            code=TEST_MFA_CODE,
        )

    assert response.status_code == 401

    session_count = await _count_user_sessions(
        db_session,
        user.id,
    )

    assert session_count == 0
