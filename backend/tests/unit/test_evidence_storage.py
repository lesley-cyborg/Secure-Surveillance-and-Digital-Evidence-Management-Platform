from __future__ import annotations

from datetime import (
    UTC,
    datetime,
)
from uuid import UUID

import pytest
from app.modules.evidence.minio_storage import (
    parse_minio_endpoint,
)
from app.modules.evidence.storage import (
    build_evidence_object_key,
)

_INCIDENT_ID = UUID("11111111-1111-1111-1111-111111111111")

_CAPTURED_AT = datetime(
    2026,
    8,
    9,
    10,
    53,
    tzinfo=UTC,
)

_SHA256 = "a" * 64


def test_http_minio_endpoint_is_parsed() -> None:
    result = parse_minio_endpoint("http://localhost:9000")

    assert result.endpoint == "localhost:9000"
    assert result.secure is False


def test_https_minio_endpoint_is_parsed() -> None:
    result = parse_minio_endpoint("https://storage.example.com:9443")

    assert result.endpoint == "storage.example.com:9443"
    assert result.secure is True


def test_endpoint_path_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="URL path",
    ):
        parse_minio_endpoint("http://localhost:9000/evidence")


def test_storage_object_key_is_deterministic() -> None:
    result = build_evidence_object_key(
        incident_id=_INCIDENT_ID,
        evidence_number=("EVD-20260809-105300-ABCDEF123456"),
        captured_at=_CAPTURED_AT,
        encrypted_sha256=_SHA256,
    )

    assert result == (
        "incidents/"
        "11111111-1111-1111-1111-111111111111/"
        "2026/08/09/"
        "EVD-20260809-105300-ABCDEF123456/"
        f"{_SHA256}.sspe"
    )


def test_object_key_rejects_unsafe_evidence_number() -> None:
    with pytest.raises(
        ValueError,
        match="unsafe",
    ):
        build_evidence_object_key(
            incident_id=_INCIDENT_ID,
            evidence_number=("../unsafe-evidence"),
            captured_at=_CAPTURED_AT,
            encrypted_sha256=_SHA256,
        )


def test_object_key_rejects_invalid_digest() -> None:
    with pytest.raises(
        ValueError,
        match="encrypted_sha256",
    ):
        build_evidence_object_key(
            incident_id=_INCIDENT_ID,
            evidence_number=("EVD-20260809-105300-ABCDEF123456"),
            captured_at=_CAPTURED_AT,
            encrypted_sha256="invalid",
        )


def test_object_key_rejects_naive_timestamp() -> None:
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        build_evidence_object_key(
            incident_id=_INCIDENT_ID,
            evidence_number=("EVD-20260809-105300-ABCDEF123456"),
            captured_at=datetime(
                2026,
                8,
                9,
                10,
                53,
            ),
            encrypted_sha256=_SHA256,
        )
