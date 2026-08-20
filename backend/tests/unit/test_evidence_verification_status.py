from __future__ import annotations

import pytest
from app.db.models.enums import (
    EvidenceStatus,
    VerificationStatus,
)
from app.modules.evidence.verification import (
    evidence_status_after_verification,
)


def test_verified_transitions_to_verified() -> None:
    result = evidence_status_after_verification(
        current_status=EvidenceStatus.STORED,
        verification_status=(VerificationStatus.VERIFIED),
    )

    assert result is EvidenceStatus.VERIFIED


@pytest.mark.parametrize(
    "verification_status",
    [
        VerificationStatus.HASH_MISMATCH,
        VerificationStatus.SIGNATURE_INVALID,
    ],
)
def test_integrity_failure_transitions_to_compromised(
    verification_status: VerificationStatus,
) -> None:
    result = evidence_status_after_verification(
        current_status=EvidenceStatus.STORED,
        verification_status=verification_status,
    )

    assert result is EvidenceStatus.COMPROMISED


@pytest.mark.parametrize(
    "current_status",
    [
        EvidenceStatus.STORED,
        EvidenceStatus.VERIFIED,
        EvidenceStatus.COMPROMISED,
        EvidenceStatus.QUARANTINED,
        EvidenceStatus.ARCHIVED,
    ],
)
def test_unavailable_preserves_current_status(
    current_status: EvidenceStatus,
) -> None:
    result = evidence_status_after_verification(
        current_status=current_status,
        verification_status=(VerificationStatus.UNAVAILABLE),
    )

    assert result is current_status
