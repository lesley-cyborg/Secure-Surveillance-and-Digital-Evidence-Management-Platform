from __future__ import annotations

import hashlib

import pytest
from app.modules.evidence.verification import (
    EncryptedEvidenceDigestResult,
    verify_encrypted_evidence_digest,
)


def test_matching_encrypted_digest_is_reported() -> None:
    encrypted_payload = b"stored-encrypted-evidence"

    expected_sha256 = hashlib.sha256(encrypted_payload).hexdigest()

    result = verify_encrypted_evidence_digest(
        encrypted_payload=encrypted_payload,
        expected_sha256=expected_sha256,
    )

    assert isinstance(
        result,
        EncryptedEvidenceDigestResult,
    )

    assert result.expected_sha256 == expected_sha256

    assert result.calculated_sha256 == expected_sha256

    assert result.matches is True


def test_tampered_encrypted_payload_is_reported_as_mismatch() -> None:
    original_payload = b"original-encrypted-evidence"

    tampered_payload = b"tampered-encrypted-evidence"

    expected_sha256 = hashlib.sha256(original_payload).hexdigest()

    calculated_sha256 = hashlib.sha256(tampered_payload).hexdigest()

    result = verify_encrypted_evidence_digest(
        encrypted_payload=tampered_payload,
        expected_sha256=expected_sha256,
    )

    assert result.expected_sha256 == expected_sha256

    assert result.calculated_sha256 == calculated_sha256

    assert result.calculated_sha256 != result.expected_sha256

    assert result.matches is False


def test_empty_stored_object_is_still_hashable() -> None:
    expected_sha256 = hashlib.sha256(b"expected-encrypted-evidence").hexdigest()

    empty_sha256 = hashlib.sha256(b"").hexdigest()

    result = verify_encrypted_evidence_digest(
        encrypted_payload=b"",
        expected_sha256=expected_sha256,
    )

    assert result.calculated_sha256 == empty_sha256

    assert result.matches is False


def test_invalid_expected_digest_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="expected_sha256",
    ):
        verify_encrypted_evidence_digest(
            encrypted_payload=(b"encrypted-evidence"),
            expected_sha256="not-a-sha256",
        )


def test_uppercase_expected_digest_is_rejected() -> None:
    encrypted_payload = b"encrypted-evidence"

    expected_sha256 = hashlib.sha256(encrypted_payload).hexdigest().upper()

    with pytest.raises(
        ValueError,
        match="expected_sha256",
    ):
        verify_encrypted_evidence_digest(
            encrypted_payload=(encrypted_payload),
            expected_sha256=(expected_sha256),
        )
