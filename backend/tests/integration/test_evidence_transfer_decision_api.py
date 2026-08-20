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
    get_evidence_transfer_decision_service,
)
from app.modules.evidence.transfer_decision_service import (
    EvidenceTransferDecisionActorError,
    EvidenceTransferDecisionCommand,
    EvidenceTransferDecisionIdempotencyConflictError,
    EvidenceTransferDecisionReferenceError,
    EvidenceTransferDecisionResult,
    EvidenceTransferDecisionService,
    EvidenceTransferDecisionStateError,
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


class StubEvidenceTransferDecisionService:
    def __init__(self) -> None:
        self.commands: list[EvidenceTransferDecisionCommand] = []

        self.exception: Exception | None = None

        self.from_user_id = uuid4()
        self.to_user_id = uuid4()

        self.created_at = datetime.now(UTC) - timedelta(minutes=5)

        self.decided_at = datetime.now(UTC)

        self.replayed = False

    async def decide(
        self,
        *,
        command: EvidenceTransferDecisionCommand,
    ) -> EvidenceTransferDecisionResult:
        self.commands.append(command)

        if self.exception is not None:
            raise self.exception

        return EvidenceTransferDecisionResult(
            transfer_id=command.transfer_id,
            evidence_id=command.evidence_id,
            from_user_id=self.from_user_id,
            to_user_id=self.to_user_id,
            purpose=("Transfer evidence for forensic review"),
            status=command.decision_status,
            created_at=self.created_at,
            decided_at=self.decided_at,
            decision_reason=command.comment,
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
                "custody.transfer.accept",
                "custody.transfer.reject",
            }
        ),
    )


@pytest.fixture
def decision_service() -> StubEvidenceTransferDecisionService:
    return StubEvidenceTransferDecisionService()


@pytest.fixture
def client(
    authorization_state: AuthorizationState,
    decision_service: (StubEvidenceTransferDecisionService),
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

    def decision_service_override() -> EvidenceTransferDecisionService:
        return cast(
            EvidenceTransferDecisionService,
            decision_service,
        )

    app.dependency_overrides[get_authorization_context] = authorization_override

    app.dependency_overrides[get_evidence_transfer_decision_service] = decision_service_override

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
            get_evidence_transfer_decision_service,
            None,
        )


def accept_path(
    evidence_id: UUID,
    transfer_id: UUID,
) -> str:
    return str(
        app.url_path_for(
            "accept_evidence_transfer",
            evidence_id=str(evidence_id),
            transfer_id=str(transfer_id),
        )
    )


def reject_path(
    evidence_id: UUID,
    transfer_id: UUID,
) -> str:
    return str(
        app.url_path_for(
            "reject_evidence_transfer",
            evidence_id=str(evidence_id),
            transfer_id=str(transfer_id),
        )
    )


def idempotency_key() -> str:
    return f"decision-http-{uuid4().hex}"


def test_accept_transfer_returns_200_contract(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
    authorization_state: AuthorizationState,
) -> None:
    evidence_id = uuid4()
    transfer_id = uuid4()
    correlation_id = uuid4()
    key = idempotency_key()

    response = client.post(
        accept_path(
            evidence_id,
            transfer_id,
        ),
        json={
            "comment": ("Accepted for forensic review"),
        },
        headers={
            "Idempotency-Key": key,
            "X-Correlation-ID": (str(correlation_id)),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(transfer_id)

    assert body["evidenceId"] == str(evidence_id)

    assert body["fromUserId"] == str(decision_service.from_user_id)

    assert body["toUserId"] == str(decision_service.to_user_id)

    assert body["purpose"] == ("Transfer evidence for forensic review")

    assert body["status"] == "ACCEPTED"

    assert body["decidedAt"] is not None

    assert "decisionReason" not in body
    assert "expiresAt" not in body

    assert len(decision_service.commands) == 1

    command = decision_service.commands[0]

    assert command.evidence_id == evidence_id

    assert command.transfer_id == transfer_id

    assert command.actor_user_id == authorization_state.actor_id

    assert command.decision_status is TransferStatus.ACCEPTED

    assert command.idempotency_key == key

    assert command.comment == "Accepted for forensic review"

    assert command.correlation_id == str(correlation_id)

    assert response.headers["X-Correlation-ID"] == str(correlation_id)


def test_reject_transfer_returns_200_contract(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    evidence_id = uuid4()
    transfer_id = uuid4()

    response = client.post(
        reject_path(
            evidence_id,
            transfer_id,
        ),
        json={
            "comment": "Evidence not required",
        },
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["id"] == str(transfer_id)

    assert body["evidenceId"] == str(evidence_id)

    assert body["status"] == "REJECTED"

    assert len(decision_service.commands) == 1

    command = decision_service.commands[0]

    assert command.decision_status is TransferStatus.REJECTED

    assert command.comment == "Evidence not required"


def test_accept_allows_omitted_body(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    evidence_id = uuid4()
    transfer_id = uuid4()

    response = client.post(
        accept_path(
            evidence_id,
            transfer_id,
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 200

    assert len(decision_service.commands) == 1

    command = decision_service.commands[0]

    assert command.comment is None
    assert command.decision_status is TransferStatus.ACCEPTED


def test_missing_idempotency_key_returns_422(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    response = client.post(
        accept_path(
            uuid4(),
            uuid4(),
        ),
        json={},
    )

    assert response.status_code == 422

    assert decision_service.commands == []


def test_short_idempotency_key_returns_422(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    response = client.post(
        accept_path(
            uuid4(),
            uuid4(),
        ),
        json={},
        headers={
            "Idempotency-Key": "too-short",
        },
    )

    assert response.status_code == 422

    assert decision_service.commands == []


def test_comment_over_1000_characters_returns_422(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    response = client.post(
        reject_path(
            uuid4(),
            uuid4(),
        ),
        json={
            "comment": "x" * 1001,
        },
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 422

    assert decision_service.commands == []


def test_missing_accept_permission_returns_403(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
    authorization_state: AuthorizationState,
) -> None:
    authorization_state.permissions = frozenset(
        {
            "custody.transfer.reject",
        }
    )

    response = client.post(
        accept_path(
            uuid4(),
            uuid4(),
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 403

    assert decision_service.commands == []


def test_missing_reject_permission_returns_403(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
    authorization_state: AuthorizationState,
) -> None:
    authorization_state.permissions = frozenset(
        {
            "custody.transfer.accept",
        }
    )

    response = client.post(
        reject_path(
            uuid4(),
            uuid4(),
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 403

    assert decision_service.commands == []


def test_non_recipient_actor_error_returns_403(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    decision_service.exception = EvidenceTransferDecisionActorError(
        "Only the transfer recipient may decide this transfer."
    )

    response = client.post(
        accept_path(
            uuid4(),
            uuid4(),
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 403

    body = response.json()

    assert body["detail"]["code"] == ("EVIDENCE_TRANSFER_DECISION_FORBIDDEN")


def test_missing_transfer_returns_404(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    decision_service.exception = EvidenceTransferDecisionReferenceError("Transfer does not exist.")

    response = client.post(
        accept_path(
            uuid4(),
            uuid4(),
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 404

    assert response.json()["detail"]["code"] == ("EVIDENCE_TRANSFER_DECISION_NOT_FOUND")


def test_invalid_transfer_state_returns_409(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    decision_service.exception = EvidenceTransferDecisionStateError("Transfer already decided.")

    response = client.post(
        reject_path(
            uuid4(),
            uuid4(),
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 409

    assert response.json()["detail"]["code"] == ("EVIDENCE_TRANSFER_DECISION_CONFLICT")


def test_decision_idempotency_conflict_returns_409(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    decision_service.exception = EvidenceTransferDecisionIdempotencyConflictError(
        "Decision key conflict."
    )

    response = client.post(
        accept_path(
            uuid4(),
            uuid4(),
        ),
        headers={
            "Idempotency-Key": (idempotency_key()),
        },
    )

    assert response.status_code == 409

    assert response.json()["detail"]["code"] == ("EVIDENCE_TRANSFER_DECISION_CONFLICT")


def test_idempotent_decision_replay_keeps_same_http_representation(
    client: TestClient,
    decision_service: (StubEvidenceTransferDecisionService),
) -> None:
    evidence_id = uuid4()
    transfer_id = uuid4()

    key = idempotency_key()

    payload = {
        "comment": "Accepted for review",
    }

    first_response = client.post(
        accept_path(
            evidence_id,
            transfer_id,
        ),
        json=payload,
        headers={
            "Idempotency-Key": key,
        },
    )

    assert first_response.status_code == 200

    decision_service.replayed = True

    replay_response = client.post(
        accept_path(
            evidence_id,
            transfer_id,
        ),
        json=payload,
        headers={
            "Idempotency-Key": key,
        },
    )

    assert replay_response.status_code == 200

    assert replay_response.json() == first_response.json()

    assert len(decision_service.commands) == 2

    first_command = decision_service.commands[0]

    replay_command = decision_service.commands[1]

    assert first_command.evidence_id == replay_command.evidence_id == evidence_id

    assert first_command.transfer_id == replay_command.transfer_id == transfer_id

    assert (
        first_command.decision_status is replay_command.decision_status is TransferStatus.ACCEPTED
    )

    assert first_command.idempotency_key == replay_command.idempotency_key == key

    assert first_command.comment == replay_command.comment == "Accepted for review"
