from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
)
from app.modules.evidence.contracts import (
    PreparedEvidenceKey,
    PreparedEvidenceRecord,
)
from app.modules.evidence.identifiers import (
    generate_evidence_number,
)
from app.modules.evidence.service import (
    EvidenceIngestionCommand,
)


def create_record(
    **overrides: object,
) -> PreparedEvidenceRecord:
    captured_at = datetime.now(UTC)

    values: dict[str, object] = {
        "evidence_number": (generate_evidence_number(captured_at=captured_at)),
        "incident_id": uuid4(),
        "source_detection_id": None,
        "submitted_by_user_id": None,
        "source_type": (EvidenceSourceType.EXTERNAL_IMPORT),
        "evidence_type": EvidenceType.IMAGE,
        "original_filename": "frame.jpg",
        "mime_type": "image/jpeg",
        "file_size_bytes": 4096,
        "storage_bucket": "evidence",
        "storage_object_key": (f"tests/{uuid4().hex}/payload.enc"),
        "storage_version_id": None,
        "original_sha256": "a" * 64,
        "encrypted_sha256": "b" * 64,
        "manifest_sha256": "c" * 64,
        "digital_signature": ("test-signature"),
        "status": EvidenceStatus.STORED,
        "captured_at": captured_at,
        "ingested_at": (captured_at + timedelta(seconds=1)),
    }

    values.update(overrides)

    return PreparedEvidenceRecord(
        **values,  # type: ignore[arg-type]
    )


def test_prepared_evidence_record_is_valid() -> None:
    record = create_record()

    assert record.file_size_bytes == 4096
    assert record.status is EvidenceStatus.STORED


def test_zero_file_size_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="file_size_bytes",
    ):
        create_record(file_size_bytes=0)


@pytest.mark.parametrize(
    "field_name",
    [
        "original_sha256",
        "encrypted_sha256",
        "manifest_sha256",
    ],
)
def test_invalid_sha256_is_rejected(
    field_name: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=field_name,
    ):
        create_record(
            **{
                field_name: "bad-hash",
            }
        )


def test_naive_captured_timestamp_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="captured_at",
    ):
        create_record(
            captured_at=datetime.now(),
        )


def test_ingestion_before_capture_is_rejected() -> None:
    captured_at = datetime.now(UTC)

    with pytest.raises(
        ValueError,
        match="ingested_at",
    ):
        create_record(
            captured_at=captured_at,
            ingested_at=(captured_at - timedelta(seconds=1)),
        )


def test_evidence_number_requires_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        generate_evidence_number(captured_at=datetime.now())


def test_prepared_key_requires_positive_version() -> None:
    with pytest.raises(
        ValueError,
        match="key_version",
    ):
        PreparedEvidenceKey(
            algorithm="AES-256-GCM",
            wrapped_key="wrapped-test-key",
            key_reference="test://master-key",
            key_version=0,
        )


def test_ai_capture_requires_artifact_id() -> None:
    with pytest.raises(
        ValueError,
        match="source_artifact_id",
    ):
        EvidenceIngestionCommand(
            incident_id=uuid4(),
            source_detection_id=uuid4(),
            submitted_by_user_id=None,
            source_type=(EvidenceSourceType.AI_CAPTURE),
            evidence_type=(EvidenceType.IMAGE),
            original_filename="frame.jpg",
            mime_type="image/jpeg",
            captured_at=datetime.now(UTC),
            content=b"frame",
            correlation_id=str(uuid4()),
            source_artifact_id=None,
        )
