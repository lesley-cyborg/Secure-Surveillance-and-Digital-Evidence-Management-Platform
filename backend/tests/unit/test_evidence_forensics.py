from __future__ import annotations

import hashlib
import json
from datetime import (
    UTC,
    datetime,
    timedelta,
    timezone,
)
from io import BytesIO
from uuid import UUID

import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    analyze_evidence_bytes,
    build_manifest_artifact,
    sha256_bytes,
    sha256_stream,
)

_INCIDENT_ID = UUID("11111111-1111-1111-1111-111111111111")

_DETECTION_ID = UUID("22222222-2222-2222-2222-222222222222")

_CAPTURED_AT = datetime(
    2026,
    8,
    8,
    12,
    30,
    45,
    123456,
    tzinfo=UTC,
)


def create_manifest(
    *,
    evidence_number: str = ("EVD-20260808-123045-ABCDEF123456"),
    incident_id: UUID = _INCIDENT_ID,
    source_detection_id: UUID | None = (_DETECTION_ID),
    source_type: EvidenceSourceType = (EvidenceSourceType.AI_CAPTURE),
    evidence_type: EvidenceType = (EvidenceType.IMAGE),
    original_filename: str = ("camera-frame.jpg"),
    mime_type: str = "image/jpeg",
    file_size_bytes: int = 4,
    original_sha256: str | None = None,
    captured_at: datetime = _CAPTURED_AT,
) -> EvidenceForensicManifest:
    digest = original_sha256 if original_sha256 is not None else hashlib.sha256(b"test").hexdigest()

    return EvidenceForensicManifest(
        evidence_number=evidence_number,
        incident_id=incident_id,
        source_detection_id=(source_detection_id),
        source_type=source_type,
        evidence_type=evidence_type,
        original_filename=(original_filename),
        mime_type=mime_type,
        file_size_bytes=file_size_bytes,
        original_sha256=digest,
        captured_at=captured_at,
    )


def test_sha256_bytes_matches_known_digest() -> None:
    content = b"forensic-evidence"

    expected = hashlib.sha256(content).hexdigest()

    assert sha256_bytes(content) == expected


def test_one_byte_change_changes_digest() -> None:
    first = b"forensic-evidence-A"
    second = b"forensic-evidence-B"

    assert sha256_bytes(first) != sha256_bytes(second)


def test_stream_hash_matches_bytes_hash() -> None:
    content = b"0123456789" * 10_000

    result = sha256_stream(
        BytesIO(content),
        chunk_size=4096,
    )

    assert result.sha256 == sha256_bytes(content)
    assert result.file_size_bytes == len(content)


def test_seekable_stream_position_is_restored() -> None:
    stream = BytesIO(b"0123456789")

    stream.seek(3)

    result = sha256_stream(stream)

    assert result.file_size_bytes == 7

    assert stream.tell() == 3


def test_analyze_evidence_bytes_records_size() -> None:
    content = b"evidence-payload"

    result = analyze_evidence_bytes(content)

    assert result.file_size_bytes == len(content)

    assert result.sha256 == hashlib.sha256(content).hexdigest()


def test_manifest_serialization_is_deterministic() -> None:
    manifest = create_manifest()

    first = manifest.canonical_bytes()
    second = manifest.canonical_bytes()

    assert first == second

    parsed = json.loads(first.decode("utf-8"))

    assert parsed["schema_version"] == "1.0"

    assert parsed["incident_id"] == str(_INCIDENT_ID)


def test_equivalent_timestamps_have_same_manifest_hash() -> None:
    utc_manifest = create_manifest()

    offset_time = _CAPTURED_AT.astimezone(timezone(timedelta(hours=2)))

    offset_manifest = create_manifest(captured_at=offset_time)

    first = build_manifest_artifact(utc_manifest)

    second = build_manifest_artifact(offset_manifest)

    assert first.sha256 == second.sha256


def test_manifest_field_change_changes_hash() -> None:
    first = build_manifest_artifact(create_manifest())

    second = build_manifest_artifact(create_manifest(original_filename=("different-frame.jpg")))

    assert first.sha256 != second.sha256


def test_original_hash_change_changes_manifest_hash() -> None:
    first = build_manifest_artifact(create_manifest())

    second = build_manifest_artifact(create_manifest(original_sha256="f" * 64))

    assert first.sha256 != second.sha256


def test_naive_manifest_timestamp_is_rejected() -> None:
    naive = datetime(
        2026,
        8,
        8,
        12,
        30,
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        create_manifest(captured_at=naive)
