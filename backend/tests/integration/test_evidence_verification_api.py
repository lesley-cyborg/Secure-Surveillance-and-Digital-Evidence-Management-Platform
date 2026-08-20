from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.db.models.enums import (
    VerificationStatus,
)
from app.main import app
from app.modules.evidence.dependencies import (
    get_evidence_verification_http_service,
)
from app.modules.evidence.verification import (
    EvidenceVerificationCommand,
)
from app.modules.evidence.verification_http import (
    EvidenceVerificationHTTPOutcome,
    EvidenceVerificationHTTPService,
    EvidenceVerificationNotFoundError,
    EvidenceVerificationResponse,
)
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    get_authorization_context,
)
from fastapi.testclient import TestClient


@dataclass(frozen=True, slots=True)
class StubUser:
    id: UUID


@dataclass(frozen=True, slots=True)
class StubAuthorization:
    user: StubUser
    permissions: frozenset[str]


class StubVerificationHTTPService:
    def __init__(self) -> None:
        self.status = VerificationStatus.VERIFIED

        self.evidence_id: UUID | None = None
        self.not_found = False
        self.replayed = False

        self.commands: list[EvidenceVerificationCommand] = []

    async def verify(
        self,
        *,
        command: EvidenceVerificationCommand,
    ) -> EvidenceVerificationHTTPOutcome:
        self.commands.append(command)

        if self.not_found:
            raise EvidenceVerificationNotFoundError("missing evidence")

        evidence_id = self.evidence_id or command.evidence_id

        calculated_sha256: str | None = "b" * 64

        hash_matches = True
        signature_valid = True
        failure_reason: str | None = None

        if self.status is VerificationStatus.HASH_MISMATCH:
            hash_matches = False
            signature_valid = False
            calculated_sha256 = "c" * 64
            failure_reason = "Evidence integrity verification failed."

        elif self.status is VerificationStatus.SIGNATURE_INVALID:
            hash_matches = True
            signature_valid = False
            failure_reason = "Stored digital signature verification failed."

        elif self.status is VerificationStatus.UNAVAILABLE:
            hash_matches = False
            signature_valid = False
            calculated_sha256 = None
            failure_reason = "Evidence object unavailable."

        return EvidenceVerificationHTTPOutcome(
            verification=(
                EvidenceVerificationResponse(
                    id=uuid4(),
                    evidence_id=evidence_id,
                    verified_by_user_id=(command.verified_by_user_id),
                    expected_sha256="b" * 64,
                    calculated_sha256=(calculated_sha256),
                    hash_matches=hash_matches,
                    signature_valid=(signature_valid),
                    verification_status=(self.status),
                    failure_reason=(failure_reason),
                    verified_at=(datetime.now(UTC)),
                )
            ),
            replayed=self.replayed,
        )


@pytest.fixture
def verification_service() -> StubVerificationHTTPService:
    return StubVerificationHTTPService()


@pytest.fixture
def actor_id() -> UUID:
    return uuid4()


def authorized_context(
    *,
    actor_id: UUID,
    permissions: frozenset[str],
) -> AuthorizationContext:
    value = StubAuthorization(
        user=StubUser(id=actor_id),
        permissions=permissions,
    )

    return cast(
        AuthorizationContext,
        value,
    )


@pytest.fixture
def client(
    verification_service: (StubVerificationHTTPService),
    actor_id: UUID,
) -> Iterator[TestClient]:
    async def authorization_override() -> AuthorizationContext:
        return authorized_context(
            actor_id=actor_id,
            permissions=frozenset(
                {
                    "evidence.verify",
                    "evidence.read",
                    "evidence.content.read",
                }
            ),
        )

    def service_override() -> EvidenceVerificationHTTPService:
        return cast(
            EvidenceVerificationHTTPService,
            verification_service,
        )

    app.dependency_overrides[get_authorization_context] = authorization_override

    app.dependency_overrides[get_evidence_verification_http_service] = service_override

    try:
        with TestClient(
            app,
            base_url="http://localhost",
        ) as test_client:
            yield test_client

    finally:
        app.dependency_overrides.pop(
            get_authorization_context,
            None,
        )

        app.dependency_overrides.pop(
            get_evidence_verification_http_service,
            None,
        )


def verification_path(
    evidence_id: UUID,
) -> str:
    return str(
        app.url_path_for(
            "verify_evidence",
            evidence_id=str(evidence_id),
        )
    )


def verification_headers(
    *,
    idempotency_key: str = ("verification-test-key-0001"),
    correlation_id: UUID | None = None,
) -> dict[str, str]:
    headers = {
        "Idempotency-Key": idempotency_key,
    }

    if correlation_id is not None:
        headers["X-Correlation-ID"] = str(correlation_id)

    return headers


def test_verified_evidence_returns_200(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
    actor_id: UUID,
) -> None:
    evidence_id = uuid4()
    correlation_id = uuid4()

    response = client.post(
        verification_path(evidence_id),
        headers=verification_headers(
            correlation_id=correlation_id,
        ),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["evidenceId"] == str(evidence_id)

    assert body["verifiedByUserId"] == str(actor_id)

    assert body["verificationStatus"] == VerificationStatus.VERIFIED.value

    assert body["hashMatches"] is True
    assert body["signatureValid"] is True

    assert response.headers["X-Correlation-ID"] == str(correlation_id)

    assert len(verification_service.commands) == 1

    command = verification_service.commands[0]

    assert command.evidence_id == evidence_id

    assert command.verified_by_user_id == actor_id

    assert command.idempotency_key == "verification-test-key-0001"


def test_missing_evidence_returns_404(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    verification_service.not_found = True

    response = client.post(
        verification_path(uuid4()),
        headers=verification_headers(),
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": {
            "code": "EVIDENCE_NOT_FOUND",
            "message": ("The requested evidence was not found."),
        }
    }


def test_hash_mismatch_returns_409(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    verification_service.status = VerificationStatus.HASH_MISMATCH

    response = client.post(
        verification_path(uuid4()),
        headers=verification_headers(),
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": {
            "code": "EVIDENCE_HASH_MISMATCH",
            "message": ("Evidence integrity verification failed."),
        }
    }


def test_invalid_signature_returns_409(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    verification_service.status = VerificationStatus.SIGNATURE_INVALID

    response = client.post(
        verification_path(uuid4()),
        headers=verification_headers(),
    )

    assert response.status_code == 409

    assert response.json() == {
        "detail": {
            "code": ("EVIDENCE_SIGNATURE_INVALID"),
            "message": ("Evidence authenticity verification failed."),
        }
    }


def test_unavailable_evidence_returns_503(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    verification_service.status = VerificationStatus.UNAVAILABLE

    response = client.post(
        verification_path(uuid4()),
        headers=verification_headers(),
    )

    assert response.status_code == 503

    assert response.json() == {
        "detail": {
            "code": "EVIDENCE_UNAVAILABLE",
            "message": ("Evidence verification is temporarily unavailable."),
        }
    }


def test_missing_idempotency_key_returns_422(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    response = client.post(
        verification_path(uuid4()),
    )

    assert response.status_code == 422

    assert verification_service.commands == []


def test_short_idempotency_key_returns_422(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    response = client.post(
        verification_path(uuid4()),
        headers={
            "Idempotency-Key": "short",
        },
    )

    assert response.status_code == 422

    assert verification_service.commands == []


def test_replayed_verification_returns_same_http_result(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    evidence_id = uuid4()

    verification_service.replayed = True

    response = client.post(
        verification_path(evidence_id),
        headers=verification_headers(),
    )

    assert response.status_code == 200

    assert response.json()["verificationStatus"] == VerificationStatus.VERIFIED.value


def test_invalid_correlation_id_returns_422(
    client: TestClient,
    verification_service: (StubVerificationHTTPService),
) -> None:
    response = client.post(
        verification_path(uuid4()),
        headers={
            **verification_headers(),
            "X-Correlation-ID": "not-a-uuid",
        },
    )

    assert response.status_code == 422

    assert verification_service.commands == []
