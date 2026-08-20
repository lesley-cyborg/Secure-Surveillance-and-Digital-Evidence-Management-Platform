from __future__ import annotations

import hashlib
from collections.abc import Iterator
from uuid import UUID, uuid4

import pytest
from app.core.config import (
    Settings,
    get_settings,
)
from app.db.models.enums import EvidenceType
from app.main import app
from app.modules.evidence.ai_bridge import (
    AIDetectionEventNotFoundError,
    AIDetectionEvidenceBridge,
    AIDetectionIncidentMissingError,
    AIEvidenceArtifactCommand,
    AIEvidenceArtifactConflictError,
    AIEvidenceArtifactResult,
)
from app.modules.evidence.dependencies import (
    get_ai_detection_evidence_bridge,
)
from app.modules.evidence.errors import (
    EvidenceIngestionCompensationError,
    EvidenceStorageConfigurationError,
    EvidenceStorageIntegrityError,
    EvidenceStorageUnavailableError,
)
from fastapi.testclient import TestClient
from pydantic import SecretStr

SERVICE_TOKEN = "integration-ai-evidence-service-token"


class StubAIEvidenceBridge(AIDetectionEvidenceBridge):
    """In-memory bridge used by the HTTP contract tests."""

    def __init__(self) -> None:
        self.commands: list[AIEvidenceArtifactCommand] = []
        self.duplicate = False
        self.evidence_id = uuid4()
        self.evidence_number = "EVD-TEST-AI-EVIDENCE"

    async def ingest(
        self,
        *,
        command: AIEvidenceArtifactCommand,
    ) -> AIEvidenceArtifactResult:
        self.commands.append(command)

        return AIEvidenceArtifactResult(
            evidence_id=self.evidence_id,
            evidence_number=self.evidence_number,
            source_event_id=command.source_event_id,
            artifact_id=command.artifact_id,
            duplicate=self.duplicate,
        )


class RaisingAIEvidenceBridge(AIDetectionEvidenceBridge):
    """Bridge that raises one configured domain exception."""

    def __init__(
        self,
        exception: Exception,
    ) -> None:
        self.exception = exception

    async def ingest(
        self,
        *,
        command: AIEvidenceArtifactCommand,
    ) -> AIEvidenceArtifactResult:
        del command
        raise self.exception


def create_settings(
    *,
    max_body_bytes: int | None = None,
) -> Settings:
    update: dict[str, object] = {
        "ai_ingestion_enabled": True,
        "ai_ingestion_service_token": SecretStr(SERVICE_TOKEN),
    }

    if max_body_bytes is not None:
        update["ai_evidence_max_body_bytes"] = max_body_bytes

    return get_settings().model_copy(update=update)


@pytest.fixture
def bridge() -> StubAIEvidenceBridge:
    return StubAIEvidenceBridge()


@pytest.fixture
def client(
    bridge: StubAIEvidenceBridge,
) -> Iterator[TestClient]:
    settings = create_settings()

    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_ai_detection_evidence_bridge] = lambda: bridge

    try:
        with TestClient(
            app,
            base_url="http://localhost",
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(
            get_ai_detection_evidence_bridge,
            None,
        )
        app.dependency_overrides.pop(
            get_settings,
            None,
        )


def install_failing_bridge(
    exception: Exception,
) -> None:
    bridge = RaisingAIEvidenceBridge(exception)
    app.dependency_overrides[get_ai_detection_evidence_bridge] = lambda: bridge


def sha256_digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_path(
    *,
    source_event_id: UUID,
    artifact_id: UUID,
    artifact_kind: str,
) -> str:
    return str(
        app.url_path_for(
            "ingest_ai_detection_evidence",
            source_event_id=str(source_event_id),
            artifact_id=str(artifact_id),
            artifact_kind=artifact_kind,
        )
    )


def request_headers(
    *,
    content: bytes,
    content_type: str,
    correlation_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {SERVICE_TOKEN}",
        "Content-Type": content_type,
        "Idempotency-Key": idempotency_key or sha256_digest(content),
    }

    if correlation_id is not None:
        headers["X-Correlation-ID"] = str(correlation_id)

    return headers


def test_key_frame_is_accepted(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    source_event_id = uuid4()
    artifact_id = uuid4()
    correlation_id = uuid4()
    content = b"jpeg-test-payload"

    response = client.post(
        build_path(
            source_event_id=source_event_id,
            artifact_id=artifact_id,
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
            correlation_id=correlation_id,
        ),
    )

    assert response.status_code == 201

    body = response.json()
    assert body["duplicate"] is False
    assert body["evidence_id"] == str(bridge.evidence_id)
    assert body["evidence_number"] == bridge.evidence_number
    assert body["source_event_id"] == str(source_event_id)
    assert body["artifact_id"] == str(artifact_id)
    assert body["correlation_id"] == str(correlation_id)

    assert response.headers["X-Correlation-ID"] == str(correlation_id)
    assert response.headers["X-Idempotency-Key"] == sha256_digest(content)
    assert response.headers["X-Evidence-ID"] == str(bridge.evidence_id)
    assert response.headers["X-Artifact-ID"] == str(artifact_id)

    assert len(bridge.commands) == 1
    command = bridge.commands[0]

    assert command.source_event_id == source_event_id
    assert command.artifact_id == artifact_id
    assert command.evidence_type is EvidenceType.IMAGE
    assert command.original_filename == f"ai-{artifact_id}.jpg"
    assert command.mime_type == "image/jpeg"
    assert command.content == content
    assert command.correlation_id == str(correlation_id)
    assert command.device_identifier == "ai-engine"


def test_event_clip_is_accepted(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    source_event_id = uuid4()
    artifact_id = uuid4()
    content = b"mp4-test-payload"

    response = client.post(
        build_path(
            source_event_id=source_event_id,
            artifact_id=artifact_id,
            artifact_kind="event-clip",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="video/mp4",
        ),
    )

    assert response.status_code == 201

    body = response.json()
    correlation_id = UUID(body["correlation_id"])

    assert response.headers["X-Correlation-ID"] == str(correlation_id)
    assert len(bridge.commands) == 1

    command = bridge.commands[0]
    assert command.source_event_id == source_event_id
    assert command.artifact_id == artifact_id
    assert command.evidence_type is EvidenceType.VIDEO
    assert command.original_filename == f"ai-{artifact_id}.mp4"
    assert command.mime_type == "video/mp4"
    assert command.content == content
    assert command.correlation_id == str(correlation_id)


def test_duplicate_artifact_returns_200(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    bridge.duplicate = True
    content = b"duplicate-frame"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 200
    assert response.json()["duplicate"] is True
    assert len(bridge.commands) == 1


def test_empty_payload_is_rejected(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    content = b""

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_EMPTY_PAYLOAD",
            "message": "Evidence payload must not be empty.",
        }
    }
    assert bridge.commands == []


def test_malformed_idempotency_key_is_rejected(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    content = b"jpeg-test-payload"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
            idempotency_key="not-a-valid-sha256",
        ),
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_INVALID_IDEMPOTENCY_KEY",
            "message": ("Idempotency-Key must be a 64-character hexadecimal SHA-256 digest."),
        }
    }
    assert bridge.commands == []


def test_idempotency_key_body_mismatch_is_rejected(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    content = b"actual-jpeg-payload"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
            idempotency_key="0" * 64,
        ),
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_IDEMPOTENCY_MISMATCH",
            "message": "Idempotency-Key does not match the evidence body.",
        }
    }
    assert bridge.commands == []


def test_key_frame_rejects_video_content_type(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    content = b"jpeg-test-payload"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="video/mp4",
        ),
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == ("AI_EVIDENCE_UNSUPPORTED_MEDIA_TYPE")
    assert bridge.commands == []


def test_event_clip_rejects_image_content_type(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    content = b"mp4-test-payload"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="event-clip",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == ("AI_EVIDENCE_UNSUPPORTED_MEDIA_TYPE")
    assert bridge.commands == []


def test_oversized_payload_is_rejected(
    client: TestClient,
    bridge: StubAIEvidenceBridge,
) -> None:
    limited_settings = create_settings(max_body_bytes=1024)
    app.dependency_overrides[get_settings] = lambda: limited_settings

    content = b"x" * 1025

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 413
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_PAYLOAD_TOO_LARGE",
            "message": "Evidence payload exceeds the configured limit.",
        }
    }
    assert bridge.commands == []


def test_missing_detection_returns_404(client: TestClient) -> None:
    install_failing_bridge(
        AIDetectionEventNotFoundError("Referenced AI detection event does not exist")
    )
    content = b"missing-detection"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == ("AI_EVIDENCE_DETECTION_NOT_FOUND")


def test_detection_without_incident_returns_409(client: TestClient) -> None:
    install_failing_bridge(
        AIDetectionIncidentMissingError("Referenced AI detection has no linked incident")
    )
    content = b"incident-missing"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "AI_EVIDENCE_INCIDENT_MISSING"


def test_artifact_conflict_returns_409(client: TestClient) -> None:
    install_failing_bridge(AIEvidenceArtifactConflictError("AI artifact ID was already used"))
    content = b"artifact-conflict"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == ("AI_EVIDENCE_ARTIFACT_CONFLICT")


def test_storage_unavailable_returns_503(client: TestClient) -> None:
    install_failing_bridge(EvidenceStorageUnavailableError("internal minio detail"))
    content = b"storage-unavailable"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_STORAGE_UNAVAILABLE",
            "message": "Evidence storage is temporarily unavailable.",
        }
    }
    assert "internal minio detail" not in response.text


def test_storage_configuration_failure_returns_503(client: TestClient) -> None:
    install_failing_bridge(EvidenceStorageConfigurationError("secret bucket configuration detail"))
    content = b"storage-configuration"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_STORAGE_CONFIGURATION_ERROR",
            "message": "Evidence storage is not available.",
        }
    }
    assert "secret bucket configuration detail" not in response.text


def test_storage_integrity_failure_returns_500(client: TestClient) -> None:
    install_failing_bridge(EvidenceStorageIntegrityError("internal storage integrity detail"))
    content = b"storage-integrity"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_STORAGE_INTEGRITY_ERROR",
            "message": "Evidence storage integrity validation failed.",
        }
    }
    assert "internal storage integrity detail" not in response.text


def test_compensation_failure_returns_500(client: TestClient) -> None:
    install_failing_bridge(EvidenceIngestionCompensationError("internal compensation detail"))
    content = b"compensation-failure"

    response = client.post(
        build_path(
            source_event_id=uuid4(),
            artifact_id=uuid4(),
            artifact_kind="key-frame",
        ),
        content=content,
        headers=request_headers(
            content=content,
            content_type="image/jpeg",
        ),
    )

    assert response.status_code == 500
    assert response.json() == {
        "detail": {
            "code": "AI_EVIDENCE_COMPENSATION_FAILED",
            "message": ("Evidence ingestion failed and storage cleanup could not be completed."),
        }
    }
    assert "internal compensation detail" not in response.text
