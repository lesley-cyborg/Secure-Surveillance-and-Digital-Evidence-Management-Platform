from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.db.models.enums import (
    AuditOutcome,
    CameraStatus,
    CustodyEventType,
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
    TransferStatus,
)
from app.db.models.evidence import (
    CustodyRecord,
    Evidence,
    EvidenceTransfer,
)
from app.db.models.incidents import Incident
from app.db.models.reporting import AuditLog
from app.db.models.surveillance import Camera, Site
from app.modules.audit.actions import AuditAction
from app.modules.auth.repository import UserRepository
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    RSAPSSSHA256Signer,
)
from app.modules.evidence.transfer_decision_service import (
    EvidenceTransferDecisionActorError,
    EvidenceTransferDecisionCommand,
    EvidenceTransferDecisionIdempotencyConflictError,
    EvidenceTransferDecisionReferenceError,
    EvidenceTransferDecisionService,
    EvidenceTransferDecisionStateError,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(
    frozen=True,
    slots=True,
)
class DecisionSeed:
    evidence_id: UUID
    custodian_id: UUID
    recipient_id: UUID
    outsider_id: UUID
    transfer_id: UUID
    acquired_custody_id: UUID
    initiated_custody_id: UUID


@pytest.fixture(scope="module")
def signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAPSSSHA256Signer(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference="test://transfer-decision-signing/v1",
        key_version=1,
    )


async def seed_user(
    session: AsyncSession,
    *,
    label: str,
) -> UUID:
    unique = uuid4().hex[:12]

    repository = UserRepository(session)

    user = await repository.create(
        email=f"{label}-{unique}@example.test",
        username=f"{label}_{unique}",
        password_hash="integration-test-hash",
        first_name="Evidence",
        last_name="Investigator",
        is_active=True,
    )

    return user.id


async def seed_incident(
    session: AsyncSession,
    *,
    detected_at: datetime,
) -> UUID:
    unique = uuid4().hex[:12]

    site = Site(
        name=f"Decision Site {unique}",
        address="Integration test location",
        latitude=Decimal("-24.6282"),
        longitude=Decimal("25.9231"),
        timezone="Africa/Gaborone",
        is_active=True,
    )

    session.add(site)
    await session.flush()

    camera = Camera(
        site_id=site.id,
        registered_by=None,
        name=f"Decision Camera {unique}",
        camera_code=f"DEC-CAM-{unique}",
        ip_address="10.77.88.99",
        protocol="RTSP",
        stream_url_encrypted="encrypted://decision-test",
        credentials_secret_ref=f"secret://camera/{unique}",
        status=CameraStatus.ONLINE,
        location_description=("Evidence transfer decision integration camera"),
        is_active=True,
        last_seen_at=detected_at,
    )

    session.add(camera)
    await session.flush()

    incident = Incident(
        incident_number=f"INC-DEC-{unique}",
        primary_camera_id=camera.id,
        created_by_user_id=None,
        source_type=IncidentSourceType.MANUAL,
        incident_type="EVIDENCE_TRANSFER_DECISION_TEST",
        severity=Severity.MEDIUM,
        priority=Priority.NORMAL,
        status=IncidentStatus.NEW,
        title="Evidence transfer decision test",
        description=("Integration fixture for custody transfer decisions"),
        disposition=None,
        detected_at=detected_at,
        confirmed_at=None,
        closed_at=None,
    )

    session.add(incident)
    await session.flush()

    return incident.id


async def seed_decision_fixture(
    session: AsyncSession,
    *,
    signer: RSAPSSSHA256Signer,
    expired: bool = False,
) -> DecisionSeed:
    custodian_id = await seed_user(
        session,
        label="decision-custodian",
    )

    recipient_id = await seed_user(
        session,
        label="decision-recipient",
    )

    outsider_id = await seed_user(
        session,
        label="decision-outsider",
    )

    now = datetime.now(UTC)

    if expired:
        acquired_at = now - timedelta(hours=3)
        transfer_created_at = now - timedelta(hours=2)
        initiated_at = now - timedelta(
            hours=1,
            minutes=30,
        )
        expires_at = now - timedelta(hours=1)
    else:
        acquired_at = now - timedelta(minutes=3)
        transfer_created_at = now - timedelta(minutes=2)
        initiated_at = now - timedelta(minutes=1)
        expires_at = now + timedelta(hours=4)

    incident_id = await seed_incident(
        session,
        detected_at=acquired_at,
    )

    unique = uuid4().hex

    evidence = Evidence(
        evidence_number=f"EVD-DEC-{unique[:16]}",
        incident_id=incident_id,
        source_detection_id=None,
        source_artifact_id=None,
        submitted_by_user_id=custodian_id,
        source_type=EvidenceSourceType.EXTERNAL_IMPORT,
        evidence_type=EvidenceType.IMAGE,
        original_filename="decision-fixture.jpg",
        mime_type="image/jpeg",
        file_size_bytes=128,
        storage_bucket="evidence-test",
        storage_object_key=(f"decision/{unique}/fixture.sspe"),
        storage_version_id="test-version-1",
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        digital_signature=signer.sign(f"evidence:{unique}".encode()).to_json(),
        status=EvidenceStatus.STORED,
        captured_at=acquired_at,
        ingested_at=acquired_at,
    )

    session.add(evidence)
    await session.flush()

    acquired_metadata: dict[str, object] = {
        "fixture": "transfer-decision",
        "stage": "acquired",
    }

    acquired_integrity = build_custody_integrity(
        evidence_id=evidence.id,
        actor_user_id=custodian_id,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        previous_record_hash=None,
        transfer_id=None,
        event_type=CustodyEventType.ACQUIRED,
        purpose="Initial secure evidence acquisition",
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=acquired_metadata,
        occurred_at=acquired_at,
    )

    acquired_signature = signer.sign(acquired_integrity.canonical_bytes)

    acquired = CustodyRecord(
        evidence_id=evidence.id,
        actor_user_id=custodian_id,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        transfer_id=None,
        event_type=CustodyEventType.ACQUIRED,
        purpose="Initial secure evidence acquisition",
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=acquired_metadata,
        record_hash=acquired_integrity.record_hash,
        digital_signature=acquired_signature.to_json(),
        occurred_at=acquired_at,
    )

    session.add(acquired)
    await session.flush()

    transfer = EvidenceTransfer(
        evidence_id=evidence.id,
        from_user_id=custodian_id,
        to_user_id=recipient_id,
        initiated_by_user_id=custodian_id,
        idempotency_key=f"init-{uuid4().hex}",
        decision_idempotency_key=None,
        purpose="Transfer evidence for forensic review",
        status=TransferStatus.PENDING,
        expires_at=expires_at,
        decided_at=None,
        decision_reason=None,
        created_at=transfer_created_at,
    )

    session.add(transfer)
    await session.flush()

    initiated_metadata: dict[str, object] = {
        "fixture": "transfer-decision",
        "stage": "transfer-initiated",
        "transfer_id": str(transfer.id),
    }

    initiated_integrity = build_custody_integrity(
        evidence_id=evidence.id,
        actor_user_id=custodian_id,
        from_user_id=custodian_id,
        to_user_id=recipient_id,
        previous_record_id=acquired.id,
        previous_record_hash=acquired.record_hash,
        transfer_id=transfer.id,
        event_type=(CustodyEventType.TRANSFER_INITIATED),
        purpose=transfer.purpose,
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=initiated_metadata,
        occurred_at=initiated_at,
    )

    initiated_signature = signer.sign(initiated_integrity.canonical_bytes)

    initiated = CustodyRecord(
        evidence_id=evidence.id,
        actor_user_id=custodian_id,
        from_user_id=custodian_id,
        to_user_id=recipient_id,
        previous_record_id=acquired.id,
        transfer_id=transfer.id,
        event_type=(CustodyEventType.TRANSFER_INITIATED),
        purpose=transfer.purpose,
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=initiated_metadata,
        record_hash=initiated_integrity.record_hash,
        digital_signature=initiated_signature.to_json(),
        occurred_at=initiated_at,
    )

    session.add(initiated)

    await session.commit()

    return DecisionSeed(
        evidence_id=evidence.id,
        custodian_id=custodian_id,
        recipient_id=recipient_id,
        outsider_id=outsider_id,
        transfer_id=transfer.id,
        acquired_custody_id=acquired.id,
        initiated_custody_id=initiated.id,
    )


def create_decision_command(
    seed: DecisionSeed,
    *,
    status: TransferStatus,
    actor_user_id: UUID | None = None,
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
    comment: str | None = None,
) -> EvidenceTransferDecisionCommand:
    return EvidenceTransferDecisionCommand(
        evidence_id=seed.evidence_id,
        transfer_id=seed.transfer_id,
        actor_user_id=(actor_user_id if actor_user_id is not None else seed.recipient_id),
        decision_status=status,
        idempotency_key=(idempotency_key or f"decision-{uuid4().hex}"),
        correlation_id=(correlation_id or str(uuid4())),
        comment=comment,
        source_ip="127.0.0.1",
        user_agent="pytest/transfer-decision",
        device_identifier="pytest",
    )


async def get_transfer(
    session: AsyncSession,
    *,
    transfer_id: UUID,
) -> EvidenceTransfer:
    transfer = await session.scalar(
        select(EvidenceTransfer).where(EvidenceTransfer.id == transfer_id)
    )

    assert transfer is not None

    return transfer


async def decision_custody_count(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(CustodyRecord)
        .where(
            CustodyRecord.evidence_id == evidence_id,
            CustodyRecord.event_type.in_(
                (
                    CustodyEventType.TRANSFER_ACCEPTED,
                    CustodyEventType.TRANSFER_REJECTED,
                )
            ),
        )
    )

    return int(value or 0)


async def latest_custodian_anchor(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> CustodyRecord:
    anchor = await session.scalar(
        select(CustodyRecord)
        .where(
            CustodyRecord.evidence_id == evidence_id,
            CustodyRecord.event_type.in_(
                (
                    CustodyEventType.ACQUIRED,
                    CustodyEventType.TRANSFER_ACCEPTED,
                )
            ),
        )
        .order_by(
            CustodyRecord.occurred_at.desc(),
            CustodyRecord.created_at.desc(),
            CustodyRecord.id.desc(),
        )
        .limit(1)
    )

    assert anchor is not None

    return anchor


@pytest.mark.asyncio
async def test_recipient_can_accept_transfer_atomically(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
        comment="  Accepted for forensic review  ",
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    result = await service.decide(command=command)

    assert result.replayed is False
    assert result.status is TransferStatus.ACCEPTED
    assert result.evidence_id == seed.evidence_id
    assert result.transfer_id == seed.transfer_id
    assert result.from_user_id == seed.custodian_id
    assert result.to_user_id == seed.recipient_id
    assert result.decision_reason == "Accepted for forensic review"
    assert result.custody_record_id is not None
    assert result.audit_log_id is not None

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.ACCEPTED
    assert transfer.decided_at is not None
    assert transfer.decision_idempotency_key == command.idempotency_key
    assert transfer.decision_reason == "Accepted for forensic review"

    custody = await db_session.get(
        CustodyRecord,
        result.custody_record_id,
    )

    assert custody is not None
    assert custody.event_type is CustodyEventType.TRANSFER_ACCEPTED
    assert custody.previous_record_id == seed.initiated_custody_id
    assert custody.transfer_id == seed.transfer_id
    assert custody.from_user_id == seed.custodian_id
    assert custody.to_user_id == seed.recipient_id
    assert custody.actor_user_id == seed.recipient_id

    previous = await db_session.get(
        CustodyRecord,
        seed.initiated_custody_id,
    )

    assert previous is not None

    integrity = build_custody_integrity(
        evidence_id=custody.evidence_id,
        actor_user_id=custody.actor_user_id,
        from_user_id=custody.from_user_id,
        to_user_id=custody.to_user_id,
        previous_record_id=(custody.previous_record_id),
        previous_record_hash=previous.record_hash,
        transfer_id=custody.transfer_id,
        event_type=custody.event_type,
        purpose=custody.purpose,
        source_ip=(str(custody.source_ip) if custody.source_ip is not None else None),
        device_identifier=(custody.device_identifier),
        event_metadata=custody.event_metadata,
        occurred_at=custody.occurred_at,
    )

    assert integrity.record_hash == custody.record_hash

    signature = DigitalSignatureEnvelope.from_json(custody.digital_signature)

    assert signer.verify(
        integrity.canonical_bytes,
        signature,
    )

    audit = await db_session.get(
        AuditLog,
        result.audit_log_id,
    )

    assert audit is not None
    assert audit.action == AuditAction.CUSTODY_TRANSFER_ACCEPTED.value
    assert audit.outcome is AuditOutcome.SUCCESS
    assert audit.resource_type == "evidence"
    assert audit.resource_id == seed.evidence_id
    assert audit.details["transfer_id"] == str(seed.transfer_id)

    anchor = await latest_custodian_anchor(
        db_session,
        evidence_id=seed.evidence_id,
    )

    assert anchor.event_type is CustodyEventType.TRANSFER_ACCEPTED
    assert anchor.to_user_id == seed.recipient_id


@pytest.mark.asyncio
async def test_recipient_can_reject_transfer_atomically(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.REJECTED,
        comment="Evidence not required",
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    result = await service.decide(command=command)

    assert result.replayed is False
    assert result.status is TransferStatus.REJECTED

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.REJECTED
    assert transfer.decided_at is not None
    assert transfer.decision_reason == "Evidence not required"
    assert transfer.decision_idempotency_key == command.idempotency_key

    assert result.custody_record_id is not None

    custody = await db_session.get(
        CustodyRecord,
        result.custody_record_id,
    )

    assert custody is not None
    assert custody.event_type is CustodyEventType.TRANSFER_REJECTED
    assert custody.previous_record_id == seed.initiated_custody_id
    assert custody.from_user_id == seed.custodian_id
    assert custody.to_user_id == seed.recipient_id

    anchor = await latest_custodian_anchor(
        db_session,
        evidence_id=seed.evidence_id,
    )

    # Rejection does not change the custodian.
    assert anchor.id == seed.acquired_custody_id
    assert anchor.event_type is CustodyEventType.ACQUIRED


@pytest.mark.asyncio
async def test_only_named_recipient_may_decide_transfer(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
        actor_user_id=seed.outsider_id,
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(EvidenceTransferDecisionActorError):
        await service.decide(command=command)

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.PENDING
    assert transfer.decided_at is None
    assert transfer.decision_idempotency_key is None

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    failure_audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_type == "evidence",
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_ACCEPTED.value),
            AuditLog.outcome == AuditOutcome.FAILURE,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert failure_audit is not None


@pytest.mark.asyncio
async def test_identical_decision_replay_returns_existing_result(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
        comment="Accept transfer",
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    first = await service.decide(command=command)

    replay = await service.decide(command=command)

    assert replay.replayed is True
    assert replay.transfer_id == first.transfer_id
    assert replay.status is TransferStatus.ACCEPTED
    assert replay.custody_record_id is None
    assert replay.audit_log_id is None

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )

    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.resource_type == "evidence",
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_ACCEPTED.value),
            AuditLog.outcome == AuditOutcome.SUCCESS,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert int(audit_count or 0) == 1


@pytest.mark.asyncio
async def test_same_key_opposite_decision_is_conflict(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    key = f"decision-{uuid4().hex}"

    accept = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
        idempotency_key=key,
        comment="Accept transfer",
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    await service.decide(command=accept)

    reject = create_decision_command(
        seed,
        status=TransferStatus.REJECTED,
        idempotency_key=key,
        comment="Reject transfer",
    )

    with pytest.raises(EvidenceTransferDecisionIdempotencyConflictError):
        await service.decide(command=reject)

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.ACCEPTED
    assert transfer.decision_idempotency_key == key

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_different_key_after_decision_is_state_conflict(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    first = create_decision_command(
        seed,
        status=TransferStatus.REJECTED,
        comment="Reject transfer",
    )

    await service.decide(command=first)

    second = create_decision_command(
        seed,
        status=TransferStatus.REJECTED,
        comment="Reject transfer",
    )

    with pytest.raises(EvidenceTransferDecisionStateError):
        await service.decide(command=second)

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.REJECTED
    assert transfer.decision_idempotency_key == first.idempotency_key

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_expired_pending_transfer_cannot_be_decided(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
        expired=True,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(EvidenceTransferDecisionStateError):
        await service.decide(command=command)

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.PENDING
    assert transfer.decided_at is None

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    failure_audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_ACCEPTED.value),
            AuditLog.outcome == AuditOutcome.FAILURE,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert failure_audit is not None


@pytest.mark.asyncio
async def test_missing_transfer_is_reference_error(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = EvidenceTransferDecisionCommand(
        evidence_id=seed.evidence_id,
        transfer_id=uuid4(),
        actor_user_id=seed.recipient_id,
        decision_status=TransferStatus.ACCEPTED,
        idempotency_key=(f"decision-{uuid4().hex}"),
        correlation_id=str(uuid4()),
        comment=None,
        source_ip="127.0.0.1",
        user_agent="pytest/transfer-decision",
        device_identifier="pytest",
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(EvidenceTransferDecisionReferenceError):
        await service.decide(command=command)

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    failure_audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_ACCEPTED.value),
            AuditLog.outcome == AuditOutcome.FAILURE,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert failure_audit is not None


@pytest.mark.asyncio
async def test_custody_failure_rolls_back_transfer_decision(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    async def fail_custody(
        **_: object,
    ) -> CustodyRecord:
        raise RuntimeError("forced decision custody failure")

    monkeypatch.setattr(
        service.custody,
        "create",
        fail_custody,
    )

    with pytest.raises(
        RuntimeError,
        match="forced decision custody failure",
    ):
        await service.decide(command=command)

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.PENDING
    assert transfer.decided_at is None
    assert transfer.decision_reason is None
    assert transfer.decision_idempotency_key is None

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_transfer_and_custody(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_decision_fixture(
        db_session,
        signer=signer,
    )

    command = create_decision_command(
        seed,
        status=TransferStatus.ACCEPTED,
    )

    service = EvidenceTransferDecisionService(
        session=db_session,
        signer=signer,
    )

    async def fail_audit(
        **_: object,
    ) -> AuditLog:
        raise RuntimeError("forced decision audit failure")

    monkeypatch.setattr(
        service.audit,
        "create",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match="forced decision audit failure",
    ):
        await service.decide(command=command)

    transfer = await get_transfer(
        db_session,
        transfer_id=seed.transfer_id,
    )

    assert transfer.status is TransferStatus.PENDING
    assert transfer.decided_at is None
    assert transfer.decision_reason is None
    assert transfer.decision_idempotency_key is None

    assert (
        await decision_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    success_audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_ACCEPTED.value),
            AuditLog.outcome == AuditOutcome.SUCCESS,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert int(success_audits or 0) == 0
