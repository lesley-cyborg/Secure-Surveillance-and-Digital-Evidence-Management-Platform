from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.db.models.enums import (
    VerificationStatus,
)
from app.modules.evidence.verification import (
    EvidenceRetrievalResult,
    EvidenceVerificationCommand,
    EvidenceVerificationResult,
    VerifiedEvidence,
)

_SHA256 = "a" * 64


def test_verification_command_accepts_valid_input() -> None:
    command = EvidenceVerificationCommand(
        evidence_id=uuid4(),
        verified_by_user_id=None,
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent="pytest",
        device_identifier="pytest",
    )

    assert command.correlation_id


def test_verification_command_rejects_empty_correlation_id() -> None:
    with pytest.raises(
        ValueError,
        match="correlation_id",
    ):
        EvidenceVerificationCommand(
            evidence_id=uuid4(),
            verified_by_user_id=None,
            correlation_id=" ",
        )


def test_verified_result_requires_hash_match() -> None:
    with pytest.raises(
        ValueError,
        match="hash_matches",
    ):
        EvidenceVerificationResult(
            evidence_id=uuid4(),
            verification_id=uuid4(),
            verification_status=(VerificationStatus.VERIFIED),
            expected_sha256=_SHA256,
            calculated_sha256=_SHA256,
            hash_matches=False,
            signature_valid=True,
            verified_at=datetime.now(UTC),
            failure_reason=None,
            custody_record_id=uuid4(),
            audit_log_id=uuid4(),
        )


def test_verified_result_requires_valid_signature() -> None:
    with pytest.raises(
        ValueError,
        match="signature_valid",
    ):
        EvidenceVerificationResult(
            evidence_id=uuid4(),
            verification_id=uuid4(),
            verification_status=(VerificationStatus.VERIFIED),
            expected_sha256=_SHA256,
            calculated_sha256=_SHA256,
            hash_matches=True,
            signature_valid=False,
            verified_at=datetime.now(UTC),
            failure_reason=None,
            custody_record_id=uuid4(),
            audit_log_id=uuid4(),
        )


def test_verified_result_requires_calculated_hash() -> None:
    with pytest.raises(
        ValueError,
        match="calculated_sha256",
    ):
        EvidenceVerificationResult(
            evidence_id=uuid4(),
            verification_id=uuid4(),
            verification_status=(VerificationStatus.VERIFIED),
            expected_sha256=_SHA256,
            calculated_sha256=None,
            hash_matches=True,
            signature_valid=True,
            verified_at=datetime.now(UTC),
            failure_reason=None,
            custody_record_id=uuid4(),
            audit_log_id=uuid4(),
        )


def test_verified_result_rejects_failure_reason() -> None:
    with pytest.raises(
        ValueError,
        match="failure_reason",
    ):
        EvidenceVerificationResult(
            evidence_id=uuid4(),
            verification_id=uuid4(),
            verification_status=(VerificationStatus.VERIFIED),
            expected_sha256=_SHA256,
            calculated_sha256=_SHA256,
            hash_matches=True,
            signature_valid=True,
            verified_at=datetime.now(UTC),
            failure_reason="should-not-exist",
            custody_record_id=uuid4(),
            audit_log_id=uuid4(),
        )


def test_verified_result_requires_custody_record() -> None:
    with pytest.raises(
        ValueError,
        match="custody",
    ):
        EvidenceVerificationResult(
            evidence_id=uuid4(),
            verification_id=uuid4(),
            verification_status=(VerificationStatus.VERIFIED),
            expected_sha256=_SHA256,
            calculated_sha256=_SHA256,
            hash_matches=True,
            signature_valid=True,
            verified_at=datetime.now(UTC),
            failure_reason=None,
            custody_record_id=None,
            audit_log_id=uuid4(),
        )


def test_unavailable_result_may_omit_calculated_hash() -> None:
    result = EvidenceVerificationResult(
        evidence_id=uuid4(),
        verification_id=uuid4(),
        verification_status=(VerificationStatus.UNAVAILABLE),
        expected_sha256=_SHA256,
        calculated_sha256=None,
        hash_matches=False,
        signature_valid=False,
        verified_at=datetime.now(UTC),
        failure_reason=("evidence object unavailable"),
        custody_record_id=None,
        audit_log_id=uuid4(),
    )

    assert result.verification_status is VerificationStatus.UNAVAILABLE


def test_retrieval_content_is_hidden_from_repr() -> None:
    secret_content = b"sensitive-forensic-evidence"

    result = EvidenceRetrievalResult(
        evidence_id=uuid4(),
        evidence_number="EVD-TEST",
        original_filename="frame.jpg",
        mime_type="image/jpeg",
        content=secret_content,
        original_sha256=_SHA256,
        verified_at=datetime.now(UTC),
    )

    assert secret_content.decode() not in repr(result)


def test_verified_evidence_combines_results() -> None:
    evidence_id = uuid4()
    verified_at = datetime.now(UTC)

    verification = EvidenceVerificationResult(
        evidence_id=evidence_id,
        verification_id=uuid4(),
        verification_status=(VerificationStatus.VERIFIED),
        expected_sha256=_SHA256,
        calculated_sha256=_SHA256,
        hash_matches=True,
        signature_valid=True,
        verified_at=verified_at,
        failure_reason=None,
        custody_record_id=uuid4(),
        audit_log_id=uuid4(),
    )

    retrieval = EvidenceRetrievalResult(
        evidence_id=evidence_id,
        evidence_number="EVD-TEST",
        original_filename="frame.jpg",
        mime_type="image/jpeg",
        content=b"verified-content",
        original_sha256=_SHA256,
        verified_at=verified_at,
    )

    result = VerifiedEvidence(
        verification=verification,
        retrieval=retrieval,
    )

    assert result.verification.evidence_id == result.retrieval.evidence_id
