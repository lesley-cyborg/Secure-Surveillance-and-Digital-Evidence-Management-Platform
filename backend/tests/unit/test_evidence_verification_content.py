from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    ForensicManifestArtifact,
    build_manifest_artifact,
)
from app.modules.evidence.verification import (
    EvidenceContentVerificationResult,
    verify_evidence_content,
)

_CONTENT = b"phase-6.2i.6-original-forensic-evidence"

_ORIGINAL_SHA256 = hashlib.sha256(_CONTENT).hexdigest()

_INCIDENT_ID = uuid4()

_SOURCE_DETECTION_ID: UUID | None = uuid4()

_CAPTURED_AT = datetime(
    2026,
    8,
    13,
    14,
    0,
    tzinfo=UTC,
)


def create_manifest(
    *,
    evidence_number: str = ("EVD-VERIFY-CONTENT"),
) -> ForensicManifestArtifact:
    manifest = EvidenceForensicManifest(
        evidence_number=evidence_number,
        incident_id=_INCIDENT_ID,
        source_detection_id=(_SOURCE_DETECTION_ID),
        source_type=(EvidenceSourceType.AI_CAPTURE),
        evidence_type=EvidenceType.IMAGE,
        original_filename="frame.jpg",
        mime_type="image/jpeg",
        file_size_bytes=len(_CONTENT),
        original_sha256=(_ORIGINAL_SHA256),
        captured_at=_CAPTURED_AT,
    )

    return build_manifest_artifact(manifest)


def test_plaintext_and_manifest_match() -> None:
    manifest = create_manifest()

    result = verify_evidence_content(
        plaintext=_CONTENT,
        expected_original_sha256=(_ORIGINAL_SHA256),
        manifest=manifest,
        expected_manifest_sha256=(manifest.sha256),
    )

    assert isinstance(
        result,
        EvidenceContentVerificationResult,
    )

    assert result.calculated_original_sha256 == _ORIGINAL_SHA256

    assert result.calculated_manifest_sha256 == manifest.sha256

    assert result.original_hash_matches is True

    assert result.manifest_hash_matches is True

    assert result.matches is True


def test_tampered_plaintext_is_detected() -> None:
    manifest = create_manifest()

    tampered_content = b"tampered-original-forensic-evidence"

    calculated_sha256 = hashlib.sha256(tampered_content).hexdigest()

    result = verify_evidence_content(
        plaintext=tampered_content,
        expected_original_sha256=(_ORIGINAL_SHA256),
        manifest=manifest,
        expected_manifest_sha256=(manifest.sha256),
    )

    assert result.calculated_original_sha256 == calculated_sha256

    assert result.original_hash_matches is False

    assert result.manifest_hash_matches is True

    assert result.matches is False


def test_tampered_manifest_is_detected() -> None:
    original_manifest = create_manifest()

    tampered_manifest = create_manifest(evidence_number=("EVD-TAMPERED-MANIFEST"))

    result = verify_evidence_content(
        plaintext=_CONTENT,
        expected_original_sha256=(_ORIGINAL_SHA256),
        manifest=tampered_manifest,
        expected_manifest_sha256=(original_manifest.sha256),
    )

    assert result.original_hash_matches is True

    assert result.manifest_hash_matches is False

    assert result.calculated_manifest_sha256 == tampered_manifest.sha256

    assert result.matches is False


def test_invalid_expected_original_digest_is_rejected() -> None:
    manifest = create_manifest()

    with pytest.raises(
        ValueError,
        match="expected_original_sha256",
    ):
        verify_evidence_content(
            plaintext=_CONTENT,
            expected_original_sha256=("invalid-original-digest"),
            manifest=manifest,
            expected_manifest_sha256=(manifest.sha256),
        )


def test_invalid_expected_manifest_digest_is_rejected() -> None:
    manifest = create_manifest()

    with pytest.raises(
        ValueError,
        match="expected_manifest_sha256",
    ):
        verify_evidence_content(
            plaintext=_CONTENT,
            expected_original_sha256=(_ORIGINAL_SHA256),
            manifest=manifest,
            expected_manifest_sha256=("invalid-manifest-digest"),
        )
