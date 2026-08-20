from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
)
from app.db.models.evidence import (
    CustodyRecord,
    Evidence,
)
from app.db.models.incidents import Incident
from app.db.models.reporting import AuditLog
from app.db.models.surveillance import (
    Camera,
    Site,
)
from app.modules.audit.actions import AuditAction
from app.modules.auth.repository import UserRepository
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.evidence.quarantine_service import (
    EvidenceQuarantineCommand,
    EvidenceQuarantineIdempotencyConflictError,
    EvidenceQuarantineReferenceError,
    EvidenceQuarantineService,
    EvidenceQuarantineStateError,
)
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    RSAPSSSHA256Signer,
)
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(
    frozen=True,
    slots=True,
)
class QuarantineSeed:
    evidence_id: UUID
    actor_user_id: UUID
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
        key_reference=("test://quarantine-signing/v1"),
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
        email=(f"{label}-{unique}@example.test"),
        username=f"{label}_{unique}",
        password_hash=("integration-test-hash"),
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
        name=f"Quarantine Site {unique}",
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
        name=f"Quarantine Camera {unique}",
        camera_code=(f"QRT-CAM-{unique}"),
        ip_address="10.91.92.93",
        protocol="RTSP",
        stream_url_encrypted=("encrypted://quarantine-test"),
        credentials_secret_ref=(f"secret://camera/{unique}"),
        status=CameraStatus.ONLINE,
        location_description=("Evidence quarantine integration camera"),
        is_active=True,
        last_seen_at=detected_at,
    )

    session.add(camera)
    await session.flush()

    incident = Incident(
        incident_number=(f"INC-QRT-{unique}"),
        primary_camera_id=camera.id,
        created_by_user_id=None,
        source_type=(IncidentSourceType.MANUAL),
        incident_type=("EVIDENCE_QUARANTINE_TEST"),
        severity=Severity.MEDIUM,
        priority=Priority.NORMAL,
        status=IncidentStatus.NEW,
        title="Evidence quarantine test",
        description=("Integration fixture for evidence quarantine"),
        disposition=None,
        detected_at=detected_at,
        confirmed_at=None,
        closed_at=None,
    )

    session.add(incident)
    await session.flush()

    return incident.id


async def seed_quarantine_fixture(
    session: AsyncSession,
    *,
    signer: RSAPSSSHA256Signer,
    status: EvidenceStatus = (EvidenceStatus.STORED),
) -> QuarantineSeed:
    actor_user_id = await seed_user(
        session,
        label="quarantine-actor",
    )

    now = datetime.now(UTC)

    incident_id = await seed_incident(
        session,
        detected_at=now,
    )

    unique = uuid4().hex

    evidence = Evidence(
        evidence_number=(f"EVD-QRT-{unique[:16]}"),
        incident_id=incident_id,
        source_detection_id=None,
        source_artifact_id=None,
        submitted_by_user_id=actor_user_id,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=EvidenceType.IMAGE,
        original_filename=("quarantine-fixture.jpg"),
        mime_type="image/jpeg",
        file_size_bytes=128,
        storage_bucket="evidence-test",
        storage_object_key=(f"quarantine/{unique}/fixture.sspe"),
        storage_version_id=("test-version-1"),
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        digital_signature=(signer.sign(f"evidence:{unique}".encode()).to_json()),
        status=status,
        captured_at=now,
        ingested_at=now,
    )

    session.add(evidence)
    await session.flush()

    metadata: dict[str, object] = {
        "fixture": "quarantine",
        "stage": "acquired",
    }

    integrity = build_custody_integrity(
        evidence_id=evidence.id,
        actor_user_id=actor_user_id,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        previous_record_hash=None,
        transfer_id=None,
        event_type=(CustodyEventType.ACQUIRED),
        purpose=("Initial secure evidence acquisition"),
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=metadata,
        occurred_at=now,
    )

    signature = signer.sign(integrity.canonical_bytes)

    custody = CustodyRecord(
        evidence_id=evidence.id,
        actor_user_id=actor_user_id,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        transfer_id=None,
        event_type=(CustodyEventType.ACQUIRED),
        purpose=("Initial secure evidence acquisition"),
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=metadata,
        record_hash=integrity.record_hash,
        digital_signature=(signature.to_json()),
        occurred_at=now,
        idempotency_scope=None,
        idempotency_key=None,
    )

    session.add(custody)

    await session.commit()

    return QuarantineSeed(
        evidence_id=evidence.id,
        actor_user_id=actor_user_id,
        acquired_custody_id=custody.id,
    )


def create_command(
    seed: QuarantineSeed,
    *,
    reason: str = ("Integrity investigation requires temporary quarantine"),
    idempotency_key: str | None = None,
    correlation_id: str | None = None,
) -> EvidenceQuarantineCommand:
    return EvidenceQuarantineCommand(
        evidence_id=seed.evidence_id,
        actor_user_id=seed.actor_user_id,
        reason=reason,
        idempotency_key=(idempotency_key or f"quarantine-{uuid4().hex}"),
        correlation_id=(correlation_id or str(uuid4())),
        source_ip="127.0.0.1",
        user_agent=("pytest/evidence-quarantine"),
        device_identifier="pytest",
    )


async def get_evidence(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> Evidence:
    evidence = await session.scalar(select(Evidence).where(Evidence.id == evidence_id))

    assert evidence is not None

    return evidence


async def quarantine_custody_count(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> int:
    value = await session.scalar(
        select(func.count())
        .select_from(CustodyRecord)
        .where(
            CustodyRecord.evidence_id == evidence_id,
            CustodyRecord.event_type == CustodyEventType.QUARANTINED,
        )
    )

    return int(value or 0)


@pytest.mark.asyncio
async def test_stored_evidence_can_be_quarantined_atomically(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(
        seed,
        reason=("  Integrity investigation requires quarantine  "),
    )

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    result = await service.quarantine(command=command)

    assert result.replayed is False

    assert result.status is EvidenceStatus.QUARANTINED

    assert result.reason == ("Integrity investigation requires quarantine")

    assert result.custody_record_id is not None
    assert result.audit_log_id is not None

    evidence = await get_evidence(
        db_session,
        evidence_id=seed.evidence_id,
    )

    assert evidence.status is EvidenceStatus.QUARANTINED

    custody = await db_session.get(
        CustodyRecord,
        result.custody_record_id,
    )

    assert custody is not None

    assert custody.event_type is CustodyEventType.QUARANTINED

    assert custody.previous_record_id == seed.acquired_custody_id

    assert custody.actor_user_id == seed.actor_user_id

    assert custody.from_user_id is None
    assert custody.to_user_id is None
    assert custody.transfer_id is None

    assert custody.idempotency_scope == "EVIDENCE_QUARANTINE"

    assert custody.idempotency_key == command.idempotency_key

    assert custody.purpose == result.reason

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

    audit = await db_session.get(
        AuditLog,
        result.audit_log_id,
    )

    assert audit is not None

    assert audit.action == AuditAction.EVIDENCE_QUARANTINED.value

    assert audit.outcome is AuditOutcome.SUCCESS

    assert audit.resource_type == "evidence"

    assert audit.resource_id == seed.evidence_id

    assert audit.details["custody_record_id"] == str(custody.id)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_status",
    [
        EvidenceStatus.VERIFIED,
        EvidenceStatus.COMPROMISED,
    ],
)
async def test_supported_statuses_can_be_quarantined(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    source_status: EvidenceStatus,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
        status=source_status,
    )

    command = create_command(seed)

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    result = await service.quarantine(command=command)

    assert result.status is EvidenceStatus.QUARANTINED

    evidence = await get_evidence(
        db_session,
        evidence_id=seed.evidence_id,
    )

    assert evidence.status is EvidenceStatus.QUARANTINED

    assert (
        await quarantine_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )


@pytest.mark.asyncio
async def test_identical_quarantine_request_is_idempotent_replay(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(seed)

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    first = await service.quarantine(command=command)

    replay = await service.quarantine(command=command)

    assert replay.replayed is True

    assert replay.evidence_id == first.evidence_id

    assert replay.status is EvidenceStatus.QUARANTINED

    assert replay.quarantined_at == first.quarantined_at

    assert replay.custody_record_id is None
    assert replay.audit_log_id is None

    assert (
        await quarantine_custody_count(
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
            AuditLog.action == (AuditAction.EVIDENCE_QUARANTINED.value),
            AuditLog.outcome == AuditOutcome.SUCCESS,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert int(audit_count or 0) == 1


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_reason_is_conflict(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
    )

    key = f"quarantine-{uuid4().hex}"

    first = create_command(
        seed,
        reason=("Integrity investigation requires quarantine"),
        idempotency_key=key,
    )

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    await service.quarantine(command=first)

    conflicting = create_command(
        seed,
        reason=("Different quarantine reason"),
        idempotency_key=key,
    )

    with pytest.raises(EvidenceQuarantineIdempotencyConflictError):
        await service.quarantine(command=conflicting)

    assert (
        await quarantine_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )

    failure_audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_type == "evidence",
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.EVIDENCE_QUARANTINED.value),
            AuditLog.outcome == AuditOutcome.FAILURE,
            AuditLog.correlation_id == conflicting.correlation_id,
        )
    )

    assert failure_audit is not None


@pytest.mark.asyncio
async def test_already_quarantined_with_different_key_is_state_conflict(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
    )

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    first = create_command(seed)

    await service.quarantine(command=first)

    second = create_command(seed)

    with pytest.raises(EvidenceQuarantineStateError):
        await service.quarantine(command=second)

    assert (
        await quarantine_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_status",
    [
        EvidenceStatus.PENDING,
        EvidenceStatus.ARCHIVED,
    ],
)
async def test_invalid_source_status_is_rejected(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    source_status: EvidenceStatus,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
        status=source_status,
    )

    command = create_command(seed)

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(EvidenceQuarantineStateError):
        await service.quarantine(command=command)

    evidence = await get_evidence(
        db_session,
        evidence_id=seed.evidence_id,
    )

    assert evidence.status is source_status

    assert (
        await quarantine_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_missing_evidence_is_reference_error(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
) -> None:
    actor_user_id = await seed_user(
        db_session,
        label="quarantine-missing-evidence-actor",
    )

    # Important: persist the authenticated actor before
    # calling the service. The service rolls back its
    # transaction before recording a failure audit.
    await db_session.commit()

    command = EvidenceQuarantineCommand(
        evidence_id=uuid4(),
        actor_user_id=actor_user_id,
        reason=(
            "Missing evidence quarantine "
            "investigation"
        ),
        idempotency_key=(
            f"quarantine-{uuid4().hex}"
        ),
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent=(
            "pytest/evidence-quarantine"
        ),
        device_identifier="pytest",
    )

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    with pytest.raises(
        EvidenceQuarantineReferenceError
    ):
        await service.quarantine(
            command=command
        )

    failure_audit = await db_session.scalar(
        select(AuditLog).where(
            AuditLog.resource_type
            == "evidence",
            AuditLog.resource_id
            == command.evidence_id,
            AuditLog.actor_user_id
            == actor_user_id,
            AuditLog.action
            == (
                AuditAction
                .EVIDENCE_QUARANTINED
                .value
            ),
            AuditLog.outcome
            == AuditOutcome.FAILURE,
            AuditLog.correlation_id
            == command.correlation_id,
        )
    )

    assert failure_audit is not None

    assert (
        failure_audit.details["evidence_id"]
        == str(command.evidence_id)
    )

    assert (
        failure_audit.details["reason"]
        == "EvidenceQuarantineReferenceError"
    )


@pytest.mark.asyncio
async def test_custody_failure_rolls_back_quarantine(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(seed)

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    async def fail_custody(
        **_: object,
    ) -> CustodyRecord:
        raise RuntimeError("forced quarantine custody failure")

    monkeypatch.setattr(
        service.custody,
        "create",
        fail_custody,
    )

    with pytest.raises(
        RuntimeError,
        match=("forced quarantine custody failure"),
    ):
        await service.quarantine(command=command)

    evidence = await get_evidence(
        db_session,
        evidence_id=seed.evidence_id,
    )

    assert evidence.status is EvidenceStatus.STORED

    assert (
        await quarantine_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )


@pytest.mark.asyncio
async def test_audit_failure_rolls_back_status_and_custody(
    db_session: AsyncSession,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_quarantine_fixture(
        db_session,
        signer=signer,
    )

    command = create_command(seed)

    service = EvidenceQuarantineService(
        session=db_session,
        signer=signer,
    )

    async def fail_audit(
        **_: object,
    ) -> AuditLog:
        raise RuntimeError("forced quarantine audit failure")

    monkeypatch.setattr(
        service.audit,
        "create",
        fail_audit,
    )

    with pytest.raises(
        RuntimeError,
        match=("forced quarantine audit failure"),
    ):
        await service.quarantine(command=command)

    evidence = await get_evidence(
        db_session,
        evidence_id=seed.evidence_id,
    )

    assert evidence.status is EvidenceStatus.STORED

    assert (
        await quarantine_custody_count(
            db_session,
            evidence_id=seed.evidence_id,
        )
        == 0
    )

    success_audits = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(
            AuditLog.resource_type == "evidence",
            AuditLog.resource_id == seed.evidence_id,
            AuditLog.action == (AuditAction.EVIDENCE_QUARANTINED.value),
            AuditLog.outcome == AuditOutcome.SUCCESS,
            AuditLog.correlation_id == command.correlation_id,
        )
    )

    assert int(success_audits or 0) == 0
