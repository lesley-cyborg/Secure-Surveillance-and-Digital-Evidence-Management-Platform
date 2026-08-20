from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    EvidenceStatus,
    VerificationStatus,
)
from app.db.models.evidence import (
    CustodyRecord,
    Evidence,
    EvidenceVerification,
)
from app.db.models.reporting import AuditLog
from app.modules.audit.actions import AuditAction
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.custody.repository import (
    CustodyRepository,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.signing import (
    RSAPSSSHA256Signer,
)
from app.modules.evidence.verification import (
    EvidenceVerificationCommand,
)
from app.modules.evidence.verification_service import (
    EvidenceVerificationPersistenceService,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.integration.test_evidence_persistence import (
    create_incident,
    create_prepared_record,
)


def create_signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    return RSAPSSSHA256Signer(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference=("test://verification-custody/v1"),
        key_version=1,
        required_key_size=2048,
    )


async def seed_stored_evidence_with_custody(
    db_session: AsyncSession,
    *,
    signer: RSAPSSSHA256Signer,
) -> tuple[Evidence, CustodyRecord]:
    incident = await create_incident(db_session)

    evidence_repository = EvidenceRepository(db_session)

    evidence = await evidence_repository.create(
        record=create_prepared_record(incident_id=incident.id)
    )

    occurred_at = datetime.now(UTC)

    custody_metadata: dict[
        str,
        object,
    ] = {
        "seed": True,
        "evidence_number": (evidence.evidence_number),
    }

    integrity = build_custody_integrity(
        evidence_id=evidence.id,
        actor_user_id=None,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        previous_record_hash=None,
        transfer_id=None,
        event_type=CustodyEventType.ACQUIRED,
        purpose="Test evidence acquisition",
        source_ip=None,
        device_identifier=None,
        event_metadata=custody_metadata,
        occurred_at=occurred_at,
    )

    signature = signer.sign(integrity.canonical_bytes)

    custody = CustodyRepository(db_session)

    acquired = await custody.create(
        evidence_id=evidence.id,
        actor_user_id=None,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        transfer_id=None,
        event_type=CustodyEventType.ACQUIRED,
        purpose="Test evidence acquisition",
        source_ip=None,
        device_identifier=None,
        event_metadata=custody_metadata,
        record_hash=integrity.record_hash,
        digital_signature=(signature.to_json()),
        occurred_at=occurred_at,
    )

    await db_session.commit()

    return evidence, acquired


def create_command(
    evidence_id: UUID,
) -> EvidenceVerificationCommand:
    return EvidenceVerificationCommand(
        evidence_id=evidence_id,
        verified_by_user_id=None,
        correlation_id=("verification-transaction-test"),
        source_ip="127.0.0.1",
        user_agent="pytest",
        device_identifier=("pytest-verifier"),
    )


@pytest.mark.asyncio
async def test_verified_outcome_creates_chained_custody_and_audit(
    db_session: AsyncSession,
) -> None:
    signer = create_signer()

    evidence, acquired = await seed_stored_evidence_with_custody(
        db_session,
        signer=signer,
    )

    service = EvidenceVerificationPersistenceService(
        session=db_session,
        signer=signer,
    )

    verified_at = datetime.now(UTC)

    result = await service.record(
        command=create_command(evidence.id),
        verification_status=(VerificationStatus.VERIFIED),
        expected_sha256=(evidence.encrypted_sha256),
        calculated_sha256=(evidence.encrypted_sha256),
        hash_matches=True,
        signature_valid=True,
        failure_reason=None,
        verified_at=verified_at,
    )

    persisted = await db_session.get(
        type(evidence),
        evidence.id,
    )

    assert persisted is not None
    assert persisted.status is EvidenceStatus.VERIFIED

    verification = await db_session.get(
        EvidenceVerification,
        result.verification_id,
    )

    assert verification is not None
    assert verification.verification_status is VerificationStatus.VERIFIED

    assert result.custody_record_id is not None

    custody = await db_session.get(
        CustodyRecord,
        result.custody_record_id,
    )

    assert custody is not None
    assert custody.event_type is CustodyEventType.VERIFIED
    assert custody.previous_record_id == acquired.id

    assert custody.event_metadata["verification_id"] == str(verification.id)

    audit = await db_session.get(
        AuditLog,
        result.audit_log_id,
    )

    assert audit is not None
    assert audit.action == AuditAction.EVIDENCE_VERIFIED.value
    assert audit.outcome is AuditOutcome.SUCCESS
    assert audit.resource_id == evidence.id
    assert audit.details["custody_record_id"] == str(custody.id)


@pytest.mark.asyncio
async def test_failed_verification_has_audit_but_no_verified_custody(
    db_session: AsyncSession,
) -> None:
    signer = create_signer()

    evidence, _ = await seed_stored_evidence_with_custody(
        db_session,
        signer=signer,
    )

    service = EvidenceVerificationPersistenceService(
        session=db_session,
        signer=signer,
    )

    result = await service.record(
        command=create_command(evidence.id),
        verification_status=(VerificationStatus.SIGNATURE_INVALID),
        expected_sha256=(evidence.encrypted_sha256),
        calculated_sha256=(evidence.encrypted_sha256),
        hash_matches=True,
        signature_valid=False,
        failure_reason=("Stored digital signature verification failed."),
        verified_at=datetime.now(UTC),
    )

    assert result.custody_record_id is None

    persisted = await db_session.get(
        type(evidence),
        evidence.id,
    )

    assert persisted is not None
    assert persisted.status is EvidenceStatus.COMPROMISED

    custody_count = await db_session.scalar(
        select(func.count())
        .select_from(CustodyRecord)
        .where(CustodyRecord.evidence_id == evidence.id)
    )

    assert int(custody_count or 0) == 1

    audit = await db_session.get(
        AuditLog,
        result.audit_log_id,
    )

    assert audit is not None
    assert audit.action == AuditAction.EVIDENCE_VERIFIED.value
    assert audit.outcome is AuditOutcome.FAILURE


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_entire_verification_transaction(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    signer = create_signer()

    evidence, _ = await seed_stored_evidence_with_custody(
        db_session,
        signer=signer,
    )

    evidence_id = evidence.id
    encrypted_sha256 = evidence.encrypted_sha256

    service = EvidenceVerificationPersistenceService(
        session=db_session,
        signer=signer,
    )

    async def fail_audit(
        **_kwargs: object,
    ) -> None:
        raise RuntimeError("forced verification audit failure")

    monkeypatch.setattr(
        service.audit,
        "create",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="forced verification audit failure",
    ):
        await service.record(
            command=create_command(evidence_id),
            verification_status=(VerificationStatus.VERIFIED),
            expected_sha256=encrypted_sha256,
            calculated_sha256=encrypted_sha256,
            hash_matches=True,
            signature_valid=True,
            failure_reason=None,
            verified_at=datetime.now(UTC),
        )

    persisted = await db_session.get(
        Evidence,
        evidence_id,
    )

    assert persisted is not None
    assert persisted.status is EvidenceStatus.STORED

    verification_count = await db_session.scalar(
        select(func.count())
        .select_from(EvidenceVerification)
        .where(EvidenceVerification.evidence_id == evidence_id)
    )

    assert int(verification_count or 0) == 0

    custody_count = await db_session.scalar(
        select(func.count())
        .select_from(CustodyRecord)
        .where(CustodyRecord.evidence_id == evidence_id)
    )

    # Only the original ACQUIRED record survives.
    assert int(custody_count or 0) == 1

    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.correlation_id == "verification-transaction-test")
    )

    assert int(audit_count or 0) == 0
