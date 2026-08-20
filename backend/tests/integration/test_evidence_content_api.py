from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import quote
from uuid import UUID, uuid4

import pytest
from app.main import app
from app.modules.evidence.content_access import (
    EvidenceContentAccessCommand,
    EvidenceContentAccessService,
)
from app.modules.evidence.dependencies import (
    get_evidence_content_access_service,
)
from app.modules.evidence.errors import (
    EvidenceRetrievalHashMismatchError,
    EvidenceRetrievalSignatureInvalidError,
    EvidenceRetrievalUnavailableError,
    EvidenceVerificationReferenceError,
)
from app.modules.evidence.verification import (
    EvidenceRetrievalResult,
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


class StubEvidenceContentAccessService:
    def __init__(self) -> None:
        self.content = b"verified-evidence-plaintext"

        self.original_filename = "frame-001.jpg"

        self.mime_type: str | None = "image/jpeg"

        self.original_sha256 = "b" * 64

        self.exception: Exception | None = None

        self.commands: list[EvidenceContentAccessCommand] = []

    async def retrieve(
        self,
        *,
        command: EvidenceContentAccessCommand,
    ) -> EvidenceRetrievalResult:
        self.commands.append(command)

        if self.exception is not None:
            raise self.exception

        return EvidenceRetrievalResult(
            evidence_id=command.evidence_id,
            evidence_number=("EVD-CONTENT-HTTP-0001"),
            original_filename=(self.original_filename),
            mime_type=self.mime_type,
            content=self.content,
            original_sha256=(self.original_sha256),
            verified_at=datetime.now(UTC),
        )


def authorized_context(
    *,
    actor_id: UUID,
) -> AuthorizationContext:
    value = StubAuthorization(
        user=StubUser(
            id=actor_id,
        ),
        permissions=frozenset(
            {
                "evidence.content.read",
            }
        ),
    )

    return cast(
        AuthorizationContext,
        value,
    )


@pytest.fixture
def content_service() -> StubEvidenceContentAccessService:
    return StubEvidenceContentAccessService()


@pytest.fixture
def actor_id() -> UUID:
    return uuid4()


@pytest.fixture
def client(
    content_service: (StubEvidenceContentAccessService),
    actor_id: UUID,
) -> Iterator[TestClient]:
    async def authorization_override() -> AuthorizationContext:
        return authorized_context(
            actor_id=actor_id,
        )

    def content_service_override() -> EvidenceContentAccessService:
        return cast(
            EvidenceContentAccessService,
            content_service,
        )

    app.dependency_overrides[get_authorization_context] = authorization_override

    app.dependency_overrides[get_evidence_content_access_service] = content_service_override

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
            get_evidence_content_access_service,
            None,
        )


def content_path(
    evidence_id: UUID,
) -> str:
    return str(
        app.url_path_for(
            "stream_evidence",
            evidence_id=str(evidence_id),
        )
    )


def test_inline_content_returns_verified_plaintext(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
    actor_id: UUID,
) -> None:
    evidence_id = uuid4()
    correlation_id = uuid4()

    response = client.get(
        content_path(evidence_id),
        headers={
            "X-Correlation-ID": (str(correlation_id)),
        },
    )

    assert response.status_code == 200

    assert response.content == content_service.content

    assert response.headers["content-type"] == "application/octet-stream"

    assert response.headers["X-Evidence-SHA256"] == content_service.original_sha256

    assert response.headers["X-Correlation-ID"] == str(correlation_id)

    assert response.headers["Content-Disposition"] == ("inline; filename*=UTF-8''frame-001.jpg")

    assert len(content_service.commands) == 1

    command = content_service.commands[0]

    assert command.evidence_id == evidence_id

    assert command.actor_user_id == actor_id

    assert command.correlation_id == str(correlation_id)


def test_attachment_disposition_is_returned(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    evidence_id = uuid4()

    response = client.get(
        content_path(evidence_id),
        params={
            "disposition": "attachment",
        },
    )

    assert response.status_code == 200

    assert response.content == content_service.content

    assert response.headers["Content-Disposition"] == ("attachment; filename*=UTF-8''frame-001.jpg")


def test_invalid_disposition_returns_422(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    response = client.get(
        content_path(uuid4()),
        params={
            "disposition": "download",
        },
    )

    assert response.status_code == 422

    assert content_service.commands == []


def test_missing_evidence_returns_404_without_plaintext(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    content_service.exception = EvidenceVerificationReferenceError("Evidence does not exist.")

    response = client.get(content_path(uuid4()))

    assert response.status_code == 404

    assert response.json() == {
        "detail": {
            "code": "EVIDENCE_NOT_FOUND",
            "message": ("The requested evidence was not found."),
        }
    }

    assert content_service.content not in response.content


def test_unavailable_evidence_returns_503_without_plaintext(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    content_service.exception = EvidenceRetrievalUnavailableError("Evidence unavailable.")

    response = client.get(content_path(uuid4()))

    assert response.status_code == 503

    assert response.json() == {
        "detail": {
            "code": "EVIDENCE_UNAVAILABLE",
            "message": ("Evidence content is temporarily unavailable."),
        }
    }

    assert content_service.content not in response.content


def test_hash_mismatch_returns_409_without_plaintext(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    content_service.exception = EvidenceRetrievalHashMismatchError("Evidence hash mismatch.")

    response = client.get(content_path(uuid4()))

    assert response.status_code == 409

    assert response.json() == {
        "detail": {
            "code": "EVIDENCE_HASH_MISMATCH",
            "message": ("Evidence integrity verification failed."),
        }
    }

    assert content_service.content not in response.content


def test_invalid_signature_returns_409_without_plaintext(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    content_service.exception = EvidenceRetrievalSignatureInvalidError(
        "Evidence signature invalid."
    )

    response = client.get(content_path(uuid4()))

    assert response.status_code == 409

    assert response.json() == {
        "detail": {
            "code": ("EVIDENCE_SIGNATURE_INVALID"),
            "message": ("Evidence authenticity verification failed."),
        }
    }

    assert content_service.content not in response.content


def test_content_disposition_safely_encodes_filename(
    client: TestClient,
    content_service: (StubEvidenceContentAccessService),
) -> None:
    filename = 'report "final"; résumé.jpg'

    content_service.original_filename = filename

    response = client.get(content_path(uuid4()))

    assert response.status_code == 200

    encoded_filename = quote(
        filename,
        safe="",
    )

    assert response.headers["Content-Disposition"] == (
        f"inline; filename*=UTF-8''{encoded_filename}"
    )

    assert filename not in response.headers["Content-Disposition"]
