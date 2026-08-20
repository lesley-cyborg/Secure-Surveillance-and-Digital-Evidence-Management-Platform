from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    RSAPSSSHA256Signer,
    build_evidence_signature_payload,
)
from app.modules.evidence.verification import (
    EvidenceSignatureVerificationResult,
    verify_evidence_signature,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)

_EVIDENCE_NUMBER = "EVD-VERIFY-SIGNATURE"
_INCIDENT_ID = uuid4()
_SOURCE_DETECTION_ID: UUID | None = uuid4()
_STORAGE_BUCKET = "evidence"
_STORAGE_OBJECT_KEY = "verification/signature/payload.sspe"
_STORAGE_VERSION_ID = "version-1"

_ORIGINAL_SHA256 = hashlib.sha256(b"original").hexdigest()

_ENCRYPTED_SHA256 = hashlib.sha256(b"encrypted").hexdigest()

_MANIFEST_SHA256 = hashlib.sha256(b"manifest").hexdigest()

_CAPTURED_AT = datetime(
    2026,
    8,
    12,
    12,
    0,
    tzinfo=UTC,
)

_INGESTED_AT = datetime(
    2026,
    8,
    12,
    12,
    0,
    1,
    tzinfo=UTC,
)


@pytest.fixture
def signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    return RSAPSSSHA256Signer(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference=("test://verification-signing/v1"),
        key_version=1,
        required_key_size=2048,
    )


def create_signature_payload(
    *,
    evidence_number: str = (_EVIDENCE_NUMBER),
) -> bytes:
    return build_evidence_signature_payload(
        evidence_number=evidence_number,
        incident_id=_INCIDENT_ID,
        source_detection_id=(_SOURCE_DETECTION_ID),
        storage_bucket=_STORAGE_BUCKET,
        storage_object_key=(_STORAGE_OBJECT_KEY),
        storage_version_id=(_STORAGE_VERSION_ID),
        original_sha256=(_ORIGINAL_SHA256),
        encrypted_sha256=(_ENCRYPTED_SHA256),
        manifest_sha256=(_MANIFEST_SHA256),
        captured_at=_CAPTURED_AT,
        ingested_at=_INGESTED_AT,
    )


def verify(
    *,
    signer: RSAPSSSHA256Signer,
    digital_signature: str,
    evidence_number: str = (_EVIDENCE_NUMBER),
) -> EvidenceSignatureVerificationResult:
    return verify_evidence_signature(
        signer=signer,
        digital_signature=(digital_signature),
        evidence_number=evidence_number,
        incident_id=_INCIDENT_ID,
        source_detection_id=(_SOURCE_DETECTION_ID),
        storage_bucket=_STORAGE_BUCKET,
        storage_object_key=(_STORAGE_OBJECT_KEY),
        storage_version_id=(_STORAGE_VERSION_ID),
        original_sha256=(_ORIGINAL_SHA256),
        encrypted_sha256=(_ENCRYPTED_SHA256),
        manifest_sha256=(_MANIFEST_SHA256),
        captured_at=_CAPTURED_AT,
        ingested_at=_INGESTED_AT,
    )


def test_valid_persisted_signature_is_verified(
    signer: RSAPSSSHA256Signer,
) -> None:
    signature = signer.sign(create_signature_payload())

    result = verify(
        signer=signer,
        digital_signature=(signature.to_json()),
    )

    assert result.signature_valid is True

    assert result.signature_format_valid is True

    assert result.failure_reason is None


def test_tampered_evidence_metadata_invalidates_signature(
    signer: RSAPSSSHA256Signer,
) -> None:
    signature = signer.sign(create_signature_payload())

    result = verify(
        signer=signer,
        digital_signature=(signature.to_json()),
        evidence_number=("EVD-TAMPERED-SIGNATURE"),
    )

    assert result.signature_valid is False

    assert result.signature_format_valid is True

    assert result.failure_reason == ("Stored digital signature verification failed.")


def test_malformed_signature_json_is_classified(
    signer: RSAPSSSHA256Signer,
) -> None:
    result = verify(
        signer=signer,
        digital_signature="{not-valid-json",
    )

    assert result.signature_valid is False

    assert result.signature_format_valid is False

    assert result.failure_reason == ("Stored digital signature envelope is invalid.")


def test_wrong_signature_key_reference_is_invalid(
    signer: RSAPSSSHA256Signer,
) -> None:
    signature = signer.sign(create_signature_payload())

    wrong_reference = DigitalSignatureEnvelope(
        algorithm=signature.algorithm,
        key_reference=("test://wrong-signing-key/v1"),
        key_version=(signature.key_version),
        signature=signature.signature,
    )

    result = verify(
        signer=signer,
        digital_signature=(wrong_reference.to_json()),
    )

    assert result.signature_valid is False

    assert result.signature_format_valid is True


def test_signature_from_different_rsa_key_is_invalid(
    signer: RSAPSSSHA256Signer,
) -> None:
    other_private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    other_signer = RSAPSSSHA256Signer(
        public_key=(other_private_key.public_key()),
        private_key=other_private_key,
        key_reference=("test://verification-signing/v1"),
        key_version=1,
        required_key_size=2048,
    )

    foreign_signature = other_signer.sign(create_signature_payload())

    result = verify(
        signer=signer,
        digital_signature=(foreign_signature.to_json()),
    )

    assert result.signature_valid is False

    assert result.signature_format_valid is True
