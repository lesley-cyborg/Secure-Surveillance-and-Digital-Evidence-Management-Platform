from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.db.models.enums import TransferStatus
from app.main import app
from app.modules.evidence.dependencies import (
    get_evidence_transfer_initiation_service,
)
from app.modules.evidence.transfer_service import (
    EvidenceTransferIdempotencyConflictError,
    EvidenceTransferInitiationCommand,
    EvidenceTransferInitiationResult,
    EvidenceTransferInitiationService,
    EvidenceTransferReferenceError,
    EvidenceTransferStateError,
)
from app.modules.rbac.dependencies import (
    AuthorizationContext,
    get_authorization_context,
)
from fastapi.testclient import TestClient


@dataclass(
    frozen=True,
    slots=True,
)
class StubUser:
    id: UUID


@dataclass(
    frozen=True,
    slots=True,
)
class StubAuthorization:
    user: StubUser
    permissions: frozenset[str]


@dataclass(
    slots=True,
)
class AuthorizationState:
    actor_id: UUID
    permissions: frozenset[str]


class StubEvidenceTransferInitiationService:
    def __init__(self) -> None:
        self.commands: list[EvidenceTransferInitiationCommand] = []

        self.exception: Exception | None = None

        self.transfer_id = uuid4()
        self.from_user_id = uuid4()

        self.created_at = datetime.now(UTC)

        self.replayed = False

    async def initiate(
        self,
        *,
        command: EvidenceTransferInitiationCommand,
    ) -> EvidenceTransferInitiationResult:
        self.commands.append(command)

        if self.exception is not None:
            raise self.exception

        return EvidenceTransferInitiationResult(
            transfer_id=self.transfer_id,
            evidence_id=command.evidence_id,
            from_user_id=self.from_user_id,
            to_user_id=command.to_user_id,
            initiated_by_user_id=(command.initiated_by_user_id),
            purpose=command.purpose,
            status=TransferStatus.PENDING,
            expires_at=command.expires_at,
            created_at=self.created_at,
            custody_record_id=(None if self.replayed else uuid4()),
            audit_log_id=(None if self.replayed else uuid4()),
            replayed=self.replayed,
        )


@pytest.fixture
def authorization_state() -> AuthorizationState:
    return AuthorizationState(
        actor_id=uuid4(),
        permissions=frozenset(
            {
                "custody.transfer",
            }
        ),
    )


@pytest.fixture
def transfer_service() -> StubEvidenceTransferInitiationService:
    return StubEvidenceTransferInitiationService()


@pytest.fixture
def client(
    authorization_state: AuthorizationState,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> Iterator[TestClient]:
    async def authorization_override() -> AuthorizationContext:
        value = StubAuthorization(
            user=StubUser(
                id=authorization_state.actor_id,
            ),
            permissions=(authorization_state.permissions),
        )

        return cast(
            AuthorizationContext,
            value,
        )

    def transfer_service_override() -> EvidenceTransferInitiationService:
        return cast(
            EvidenceTransferInitiationService,
            transfer_service,
        )

    app.dependency_overrides[get_authorization_context] = authorization_override

    app.dependency_overrides[get_evidence_transfer_initiation_service] = transfer_service_override

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
            get_evidence_transfer_initiation_service,
            None,
        )


def transfer_path(
    evidence_id: UUID,
) -> str:
    return str(
        app.url_path_for(
            "initiate_evidence_transfer",
            evidence_id=str(evidence_id),
        )
    )


def valid_payload(
    *,
    recipient_id: UUID | None = None,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "toUserId": str(recipient_id or uuid4()),
        "purpose": ("Transfer evidence for forensic examination"),
    }

    if expires_at is not None:
        payload["expiresAt"] = expires_at.isoformat()

    return payload


def idempotency_key() -> str:
    return f"transfer-http-{uuid4().hex}"


def test_valid_transfer_returns_201_contract(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
    authorization_state: AuthorizationState,
) -> None:
    evidence_id = uuid4()
    recipient_id = uuid4()
    correlation_id = uuid4()

    expires_at = datetime.now(UTC) + timedelta(hours=4)

    key = idempotency_key()

    response = client.post(
        transfer_path(evidence_id),
        json=valid_payload(
            recipient_id=recipient_id,
            expires_at=expires_at,
        ),
        headers={
            "Idempotency-Key": key,
            "X-Correlation-ID": (str(correlation_id)),
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["id"] == str(transfer_service.transfer_id)

    assert body["evidenceId"] == str(evidence_id)

    assert body["fromUserId"] == str(transfer_service.from_user_id)

    assert body["toUserId"] == str(recipient_id)

    assert body["purpose"] == ("Transfer evidence for forensic examination")

    assert body["status"] == "PENDING"

    assert body["decidedAt"] is None

    assert "expiresAt" not in body
    assert "initiatedByUserId" not in body

    created_at = datetime.fromisoformat(
        str(body["createdAt"]).replace(
            "Z",
            "+00:00",
        )
    )

    assert created_at == transfer_service.created_at

    assert response.headers["X-Correlation-ID"] == str(correlation_id)

    assert len(transfer_service.commands) == 1

    command = transfer_service.commands[0]

    assert command.evidence_id == evidence_id

    assert command.to_user_id == recipient_id

    assert command.initiated_by_user_id == authorization_state.actor_id

    assert command.idempotency_key == key

    assert command.correlation_id == str(correlation_id)

    assert command.expires_at == expires_at


def test_omitted_expiry_uses_future_default(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    evidence_id = uuid4()

    before = datetime.now(UTC)

    response = client.post(
        transfer_path(evidence_id),
        json=valid_payload(),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 201

    assert len(transfer_service.commands) == 1

    command = transfer_service.commands[0]

    delta = command.expires_at - before

    assert delta > timedelta(
        hours=23,
        minutes=59,
    )

    assert delta < timedelta(
        hours=24,
        minutes=1,
    )


def test_missing_idempotency_key_returns_422(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    response = client.post(
        transfer_path(uuid4()),
        json=valid_payload(),
    )

    assert response.status_code == 422

    assert transfer_service.commands == []


def test_short_idempotency_key_returns_422(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    response = client.post(
        transfer_path(uuid4()),
        json=valid_payload(),
        headers={
            "Idempotency-Key": "too-short",
        },
    )

    assert response.status_code == 422

    assert transfer_service.commands == []


def test_short_purpose_returns_422(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    response = client.post(
        transfer_path(uuid4()),
        json={
            "toUserId": str(uuid4()),
            "purpose": "bad",
        },
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 422

    assert transfer_service.commands == []


def test_reference_error_returns_404(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    transfer_service.exception = EvidenceTransferReferenceError("Evidence does not exist.")

    response = client.post(
        transfer_path(uuid4()),
        json=valid_payload(),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 404

    assert response.json() == {
        "detail": {
            "code": ("EVIDENCE_TRANSFER_REFERENCE_NOT_FOUND"),
            "message": ("Evidence or transfer recipient was not found."),
        }
    }


def test_state_conflict_returns_409(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    transfer_service.exception = EvidenceTransferStateError(
        "Evidence already has a pending custody transfer."
    )

    response = client.post(
        transfer_path(uuid4()),
        json=valid_payload(),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 409

    body = response.json()

    assert body["detail"]["code"] == "EVIDENCE_TRANSFER_CONFLICT"


def test_idempotency_conflict_returns_409(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    transfer_service.exception = EvidenceTransferIdempotencyConflictError(
        "Idempotency key was already used for another transfer request."
    )

    response = client.post(
        transfer_path(uuid4()),
        json=valid_payload(),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 409

    body = response.json()

    assert body["detail"]["code"] == "EVIDENCE_TRANSFER_CONFLICT"


def test_missing_custody_transfer_permission_returns_403(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
    authorization_state: AuthorizationState,
) -> None:
    authorization_state.permissions = frozenset()

    response = client.post(
        transfer_path(uuid4()),
        json=valid_payload(),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 403

    assert transfer_service.commands == []


def test_idempotent_replay_keeps_same_http_representation(
    client: TestClient,
    transfer_service: (StubEvidenceTransferInitiationService),
) -> None:
    evidence_id = uuid4()
    recipient_id = uuid4()

    key = idempotency_key()

    payload = valid_payload(
        recipient_id=recipient_id,
        expires_at=(datetime.now(UTC) + timedelta(hours=4)),
    )

    first_response = client.post(
        transfer_path(evidence_id),
        json=payload,
        headers={
            "Idempotency-Key": key,
        },
    )

    assert first_response.status_code == 201

    transfer_service.replayed = True

    replay_response = client.post(
        transfer_path(evidence_id),
        json=payload,
        headers={
            "Idempotency-Key": key,
        },
    )

    assert replay_response.status_code == 201

    assert replay_response.json() == first_response.json()

    assert len(transfer_service.commands) == 2

    first_command = transfer_service.commands[0]

    replay_command = transfer_service.commands[1]

    assert first_command.evidence_id == replay_command.evidence_id == evidence_id

    assert first_command.to_user_id == replay_command.to_user_id == recipient_id

    assert first_command.idempotency_key == replay_command.idempotency_key == key
