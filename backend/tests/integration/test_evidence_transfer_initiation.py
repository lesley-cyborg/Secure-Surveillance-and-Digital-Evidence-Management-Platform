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
from app.modules.evidence.transfer_service import (
    EvidenceTransferIdempotencyConflictError,
    EvidenceTransferInitiationCommand,
    EvidenceTransferInitiationService,
    EvidenceTransferReferenceError,
    EvidenceTransferStateError,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(
    frozen=True,
    slots=True,
)
class TransferSeed:
    evidence_id: UUID
    custodian_id: UUID
    recipient_id: UUID
    second_recipient_id: UUID
    inactive_recipient_id: UUID
    acquired_custody_id: UUID


@pytest.fixture(scope="module")
def signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAPSSSHA256Signer(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference=("test://transfer-signing/v1"),
        key_version=1,
    )


async def seed_user(
    session: AsyncSession,
    *,
    label: str,
    is_active: bool = True,
) -> UUID:
    unique = uuid4().hex[:12]

    repository = UserRepository(session)

    user = await repository.create(
        email=(f"{label}-{unique}@example.test"),
        username=f"{label}_{unique}",
        password_hash="integration-test-hash",
        first_name="Evidence",
        last_name="Investigator",
        is_active=is_active,
    )

    return user.id


async def seed_incident(
    session: AsyncSession,
) -> UUID:
    unique = uuid4().hex[:12]
    detected_at = datetime.now(UTC)

    site = Site(
        name=f"Transfer Site {unique}",
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
        name=f"Transfer Camera {unique}",
        camera_code=f"TRF-CAM-{unique}",
        ip_address="10.55.66.77",
        protocol="RTSP",
        stream_url_encrypted=("encrypted://transfer-test"),
        credentials_secret_ref=(f"secret://camera/{unique}"),
        status=CameraStatus.ONLINE,
        location_description=("Evidence transfer integration camera"),
        is_active=True,
        last_seen_at=detected_at,
    )

    session.add(camera)
    await session.flush()

    incident = Incident(
        incident_number=f"INC-TRF-{unique}",
        primary_camera_id=camera.id,
        created_by_user_id=None,
        source_type=IncidentSourceType.MANUAL,
        incident_type=("EVIDENCE_TRANSFER_TEST"),
        severity=Severity.MEDIUM,
        priority=Priority.NORMAL,
        status=IncidentStatus.NEW,
        title="Evidence transfer test",
        description=("Integration fixture for custody transfer initiation"),
        disposition=None,
        detected_at=detected_at,
        confirmed_at=None,
        closed_at=None,
    )

    session.add(incident)
    await session.flush()

    return incident.id


async def seed_transfer_fixture(
    session: AsyncSession,
    *,
    signer: RSAPSSSHA256Signer,
) -> TransferSeed:
    custodian_id = await seed_user(
        session,
        label="custodian",
    )

    recipient_id = await seed_user(
        session,
        label="recipient",
    )

    second_recipient_id = await seed_user(
        session,
        label="recipient2",
    )

    inactive_recipient_id = await seed_user(
        session,
        label="inactive",
        is_active=False,
    )

    incident_id = await seed_incident(session)

    unique = uuid4().hex
    now = datetime.now(UTC)

    evidence = Evidence(
        evidence_number=(f"EVD-TRF-{unique[:16]}"),
        incident_id=incident_id,
        source_detection_id=None,
        source_artifact_id=None,
        submitted_by_user_id=custodian_id,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=EvidenceType.IMAGE,
        original_filename=("transfer-fixture.jpg"),
        mime_type="image/jpeg",
        file_size_bytes=128,
        storage_bucket="evidence-test",
        storage_object_key=(f"transfer/{unique}/fixture.sspe"),
        storage_version_id="test-version-1",
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        digital_signature=(signer.sign(f"evidence:{unique}".encode()).to_json()),
        status=EvidenceStatus.STORED,
        captured_at=now,
        ingested_at=now,
    )

    session.add(evidence)
    await session.flush()

    metadata: dict[str, object] = {
        "fixture": ("transfer-initiation"),
    }

    integrity = build_custody_integrity(
        evidence_id=evidence.id,
        actor_user_id=custodian_id,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        previous_record_hash=None,
        transfer_id=None,
        event_type=CustodyEventType.ACQUIRED,
        purpose=("Initial secure evidence acquisition"),
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=metadata,
        occurred_at=now,
    )

    signature = signer.sign(integrity.canonical_bytes)

    custody = CustodyRecord(
        evidence_id=evidence.id,
        actor_user_id=custodian_id,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        transfer_id=None,
        event_type=CustodyEventType.ACQUIRED,
        purpose=("Initial secure evidence acquisition"),
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=metadata,
        record_hash=integrity.record_hash,
        digital_signature=signature.to_json(),
        occurred_at=now,
    )

    session.add(custody)
    await session.commit()

    return TransferSeed(
        evidence_id=evidence.id,
        custodian_id=custodian_id,
        recipient_id=recipient_id,
        second_recipient_id=(second_recipient_id),
        inactive_recipient_id=(inactive_recipient_id),
        acquired_custody_id=custody.id,
    )


def create_command(
    seed: TransferSeed,
    *,
    recipient_id: UUID | None = None,
    idempotency_key: str | None = None,
    purpose: str = ("Transfer evidence for forensic review"),
) -> EvidenceTransferInitiationCommand:
    return EvidenceTransferInitiationCommand(
        evidence_id=seed.evidence_id,
        to_user_id=(recipient_id if recipient_id is not None else seed.recipient_id),
        initiated_by_user_id=(seed.custodian_id),
        purpose=purpose,
        expires_at=(datetime.now(UTC) + timedelta(hours=4)),
        idempotency_key=(idempotency_key or f"transfer-{uuid4().hex}"),
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent=("pytest/evidence-transfer"),
        device_identifier="pytest",
    )


async def transfer_count(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(EvidenceTransfer)
        .where(EvidenceTransfer.evidence_id == evidence_id)
    )

    return int(value or 0)


async def transfer_custody_count(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(CustodyRecord)
        .where(
            CustodyRecord.evidence_id == evidence_id,
            CustodyRecord.event_type == (CustodyEventType.TRANSFER_INITIATED),
        )
    )

    return int(value or 0)


@pytest.mark.asyncio
async def test_valid_transfer_is_persisted_atomically(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(seed)

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    result = await service.initiate(command=command)

    assert result.replayed is False
    assert result.evidence_id == seed.evidence_id
    assert result.from_user_id == seed.custodian_id
    assert result.to_user_id == seed.recipient_id
    assert result.status is TransferStatus.PENDING

    transfer = await db_session.get(
        EvidenceTransfer,
        result.transfer_id,
    )

    assert transfer is not None
    assert transfer.idempotency_key == command.idempotency_key
    assert transfer.status is TransferStatus.PENDING

    assert result.custody_record_id is not None

    custody = await db_session.get(
        CustodyRecord,
        result.custody_record_id,
    )

    assert custody is not None

    assert custody.event_type is (CustodyEventType.TRANSFER_INITIATED)

    assert custody.previous_record_id == seed.acquired_custody_id

    assert custody.transfer_id == transfer.id

    assert custody.from_user_id == seed.custodian_id

    assert custody.to_user_id == seed.recipient_id

    previous = await db_session.get(
        CustodyRecord,
        seed.acquired_custody_id,
    )

    assert previous is not None

    integrity = build_custody_integrity(
        evidence_id=custody.evidence_id,
        actor_user_id=(custody.actor_user_id),
        from_user_id=(custody.from_user_id),
        to_user_id=custody.to_user_id,
        previous_record_id=(custody.previous_record_id),
        previous_record_hash=(previous.record_hash),
        transfer_id=custody.transfer_id,
        event_type=custody.event_type,
        purpose=custody.purpose,
        source_ip=(str(custody.source_ip) if custody.source_ip is not None else None),
        device_identifier=(custody.device_identifier),
        event_metadata=(custody.event_metadata),
        occurred_at=custody.occurred_at,
    )

    assert integrity.record_hash == custody.record_hash

    signature = DigitalSignatureEnvelope.from_json(custody.digital_signature)

    assert signer.verify(
        integrity.canonical_bytes,
        signature,
    )

    assert result.audit_log_id is not None

    audit = await db_session.get(
        AuditLog,
        result.audit_log_id,
    )

    assert audit is not None

    assert audit.action == (AuditAction.CUSTODY_TRANSFER_INITIATED.value)

    assert audit.outcome is AuditOutcome.SUCCESS

    assert audit.resource_type == "evidence"

    assert audit.resource_id == seed.evidence_id

    assert audit.details["transfer_id"] == str(transfer.id)


@pytest.mark.asyncio
async def test_identical_idempotent_replay_returns_existing_transfer(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(seed)

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    first = await service.initiate(command=command)

    replay = await service.initiate(command=command)

    assert replay.replayed is True

    assert replay.transfer_id == first.transfer_id

    assert replay.custody_record_id is None

    assert replay.audit_log_id is None

    assert (
        await transfer_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )

    assert (
        await transfer_custody_count(
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
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_INITIATED.value),
            AuditLog.outcome == AuditOutcome.SUCCESS,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert int(audit_count or 0) == 1

    audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_type == "evidence",
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_INITIATED.value),
            AuditLog.outcome == AuditOutcome.SUCCESS,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert audit is not None

    assert audit.details["transfer_id"] == str(first.transfer_id)


@pytest.mark.asyncio
async def test_idempotency_key_reuse_for_different_request_is_rejected(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    key = f"transfer-{uuid4().hex}"

    first = create_command(
        seed,
        idempotency_key=key,
    )

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    await service.initiate(command=first)

    conflicting = EvidenceTransferInitiationCommand(
        evidence_id=first.evidence_id,
        to_user_id=first.to_user_id,
        initiated_by_user_id=(first.initiated_by_user_id),
        purpose=("Different forensic purpose"),
        expires_at=first.expires_at,
        idempotency_key=key,
        correlation_id=str(uuid4()),
        source_ip=first.source_ip,
        user_agent=first.user_agent,
        device_identifier=(first.device_identifier),
    )

    with pytest.raises(EvidenceTransferIdempotencyConflictError):
        await service.initiate(command=conflicting)

    assert (
        await transfer_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )

    assert (
        await transfer_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_current_custodian_cannot_be_transfer_recipient(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(
        seed,
        recipient_id=seed.custodian_id,
    )

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(EvidenceTransferStateError):
        await service.initiate(command=command)

    assert (
        await transfer_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_inactive_recipient_is_rejected(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(
        seed,
        recipient_id=(seed.inactive_recipient_id),
    )

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(EvidenceTransferReferenceError):
        await service.initiate(command=command)

    assert (
        await transfer_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    failure_audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_type == "evidence",
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_INITIATED.value),
            AuditLog.outcome == AuditOutcome.FAILURE,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert failure_audit is not None
    assert failure_audit.resource_type == "evidence"

    assert failure_audit.details["evidence_id"] == str(seed.evidence_id)

    assert failure_audit.details["to_user_id"] == str(seed.inactive_recipient_id)


@pytest.mark.asyncio
async def test_second_pending_transfer_is_rejected(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    first = create_command(seed)

    await service.initiate(command=first)

    second = create_command(
        seed,
        recipient_id=(seed.second_recipient_id),
    )

    with pytest.raises(EvidenceTransferStateError):
        await service.initiate(command=second)

    assert (
        await transfer_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )

    assert (
        await transfer_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_transfer_and_custody(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_transfer_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(seed)

    service = EvidenceTransferInitiationService(
        session=db_session,
        signer=signer,
    )

    async def fail_audit(
        **_: object,
    ) -> AuditLog:
        raise RuntimeError("forced transfer audit failure")

    monkeypatch.setattr(
        service.audit,
        "create",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match=("forced transfer audit failure"),
    ):
        await service.initiate(command=command)

    assert (
        await transfer_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    assert (
        await transfer_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    total_custody = await db_session.scalar(
        select(func.count())
        .select_from(CustodyRecord)
        .where(CustodyRecord.evidence_id == seed.evidence_id)
    )

    # Only the already-committed ACQUIRED
    # record may remain.
    assert int(total_custody or 0) == 1

    transfer_audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.action == (AuditAction.CUSTODY_TRANSFER_INITIATED.value),
            AuditLog.details["evidence_id"].as_string() == str(seed.evidence_id),
        )
    )

    assert int(transfer_audits or 0) == 0
