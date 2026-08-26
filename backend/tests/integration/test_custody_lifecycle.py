from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.core.security import hash_password
from app.db.models.enums import (
    AuditOutcome,
    CustodyEventType,
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
)
from app.db.models.evidence import CustodyRecord, Evidence
from app.db.models.incidents import Incident
from app.db.models.reporting import AuditLog
from app.db.models.surveillance import Camera, Site
from app.modules.auth.repository import UserRepository
from app.modules.custody.errors import (
    CustodyEvidenceNotFoundError,
    CustodyIdempotencyConflictError,
)
from app.modules.custody.service import (
    AppendCustodyEventCommand,
    CustodyService,
    ListCustodyEventsCommand,
)
from app.modules.custody.integrity import build_custody_integrity
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
)
from app.modules.evidence.signing import RSAPSSSHA256Signer
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
async def signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096) <--THIS GUY WA NYOBOKA EISH
    return RSAPSSSHA256Signer(
        public_key=private_key.public_key(),
        private_key=private_key,
        key_reference="test://custody-signing/v1",
        key_version=1,
    )


@pytest.fixture
async def custody_service(db_session: AsyncSession, signer: RSAPSSSHA256Signer) -> CustodyService:
    return CustodyService(session=db_session, signer=signer)


@pytest.fixture
async def test_user(db_session: AsyncSession):
    repo = UserRepository(db_session)
    user = await repo.create(
        email=f"test-{uuid4()}@example.com",
        username=f"testuser-{uuid4().hex[:8]}",
        password_hash=hash_password("SecurePassword123!"),
        first_name="Test",
        last_name="User",
    )
    return user


@pytest.fixture
async def test_evidence(db_session: AsyncSession, test_user):
    site = Site(name="Test Site", timezone="UTC")
    db_session.add(site)
    await db_session.flush()

    camera = Camera(
        site_id=site.id,
        name="Test Camera",
        camera_code=f"CAM-{uuid4().hex[:8]}",
        ip_address="127.0.0.1",
        protocol="RTSP",
        stream_url_encrypted="encrypted-url",
        credentials_secret_ref="ref",
        status="ONLINE",
    )
    db_session.add(camera)
    await db_session.flush()

    incident = Incident(
        incident_number=f"INC-{uuid4().hex[:8]}",
        source_type=IncidentSourceType.MANUAL,
        incident_type="TEST",
        severity=Severity.LOW,
        priority=Priority.LOW,
        status=IncidentStatus.NEW,
        title="Test Incident",
        detected_at=datetime.now(UTC),
    )
    db_session.add(incident)
    await db_session.flush()

    evidence = Evidence(
        evidence_number=f"EV-{uuid4().hex[:8]}",
        incident_id=incident.id,
        submitted_by_user_id=test_user.id,
        source_type=EvidenceSourceType.MANUAL_UPLOAD,
        evidence_type=EvidenceType.IMAGE,
        original_filename="test.jpg",
        mime_type="image/jpeg",
        file_size_bytes=1024,
        storage_bucket="test-bucket",
        storage_object_key=f"test/{uuid4()}",
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        digital_signature="test-signature",
        status=EvidenceStatus.STORED,
        captured_at=datetime.now(UTC),
        ingested_at=datetime.now(UTC),
    )
    db_session.add(evidence)
    await db_session.flush()

    return evidence


@pytest.mark.asyncio
async def test_append_custody_event_success(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    command = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence for investigation",
        idempotency_key=f"idemp-{uuid4().hex}",
        correlation_id=str(uuid4()),
    )

    result = await custody_service.append_event(command=command)

    assert result.replayed is False
    assert result.custody_record.event_type == CustodyEventType.VIEWED
    assert result.custody_record.purpose == "Reviewed evidence for investigation"
    assert result.custody_record.record_hash is not None
    assert result.custody_record.digital_signature is not None
    assert result.custody_record.previous_record_id is None  # First record

    # Verify audit log
    audit_stmt = select(AuditLog).where(
        AuditLog.action == "CUSTODY_EVENT_CREATED",
        AuditLog.resource_id == test_evidence.id,
    )
    audit_result = await db_session.execute(audit_stmt)
    audit_log = audit_result.scalar_one_or_none()
    assert audit_log is not None
    assert audit_log.outcome == AuditOutcome.SUCCESS


@pytest.mark.asyncio
async def test_append_custody_event_idempotency(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    idempotency_key = f"idemp-{uuid4().hex}"
    command = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence for investigation",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
    )

    result1 = await custody_service.append_event(command=command)
    assert result1.replayed is False

    result2 = await custody_service.append_event(command=command)
    assert result2.replayed is True
    assert result2.custody_record.id == result1.custody_record.id


@pytest.mark.asyncio
async def test_append_custody_event_idempotency_conflict(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    idempotency_key = f"idemp-{uuid4().hex}"
    command1 = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="First purpose",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
    )

    await custody_service.append_event(command=command1)

    command2 = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.EXPORTED,
        purpose="Different purpose",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
    )

    with pytest.raises(CustodyIdempotencyConflictError):
        await custody_service.append_event(command=command2)


@pytest.mark.asyncio
async def test_append_custody_event_evidence_not_found(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_user,
):
    command = AppendCustodyEventCommand(
        evidence_id=uuid4(),
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence",
        idempotency_key=f"idemp-{uuid4().hex}",
        correlation_id=str(uuid4()),
    )

    with pytest.raises(CustodyEvidenceNotFoundError):
        await custody_service.append_event(command=command)


@pytest.mark.asyncio
async def test_append_custody_event_invalid_event_type(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    command = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.ACQUIRED,  # Not API-appendable
        purpose="Attempted internal event",
        idempotency_key=f"idemp-{uuid4().hex}",
        correlation_id=str(uuid4()),
    )

    with pytest.raises(ValueError):
        await custody_service.append_event(command=command)


@pytest.mark.asyncio
async def test_list_custody_events(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    # Create two events
    for i, event_type in enumerate([CustodyEventType.VIEWED, CustodyEventType.EXPORTED]):
        command = AppendCustodyEventCommand(
            evidence_id=test_evidence.id,
            actor_user_id=test_user.id,
            event_type=event_type,
            purpose=f"Purpose {i}",
            idempotency_key=f"idemp-{uuid4().hex}",
            correlation_id=str(uuid4()),
        )
        await custody_service.append_event(command=command)

    list_command = ListCustodyEventsCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        correlation_id=str(uuid4()),
        page=1,
        page_size=25,
    )

    result = await custody_service.list_events(command=list_command)

    assert result.total == 2
    assert len(result.items) == 2
    assert result.items[0].event_type == CustodyEventType.VIEWED
    assert result.items[1].event_type == CustodyEventType.EXPORTED
    assert result.items[1].previous_record_id == result.items[0].id  # Chain integrity


@pytest.mark.asyncio
async def test_list_custody_events_evidence_not_found(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_user,
):
    command = ListCustodyEventsCommand(
        evidence_id=uuid4(),
        actor_user_id=test_user.id,
        correlation_id=str(uuid4()),
    )

    with pytest.raises(CustodyEvidenceNotFoundError):
        await custody_service.list_events(command=command)


@pytest.mark.asyncio
async def test_custody_chain_integrity(
    db_session: AsyncSession,
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    # Create three events and verify chain linking
    records = []
    for i, event_type in enumerate([CustodyEventType.VIEWED, CustodyEventType.EXPORTED, CustodyEventType.VERIFIED]):
        command = AppendCustodyEventCommand(
            evidence_id=test_evidence.id,
            actor_user_id=test_user.id,
            event_type=event_type,
            purpose=f"Purpose {i}",
            idempotency_key=f"idemp-{uuid4().hex}",
            correlation_id=str(uuid4()),
        )
        result = await custody_service.append_event(command=command)
        records.append(result.custody_record)

    # First record has no previous
    assert records[0].previous_record_id is None

    # Subsequent records link to previous
    assert records[1].previous_record_id == records[0].id
    assert records[2].previous_record_id == records[1].id

    # Verify hashes are different
    assert records[0].record_hash != records[1].record_hash
    assert records[1].record_hash != records[2].record_hash
    
    
@pytest.mark.asyncio
async def test_idempotency_conflict_when_metadata_changes(
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    idempotency_key = f"idemp-{uuid4().hex}"

    command1 = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
        event_metadata={
            "case_reference": "CASE-001",
        },
    )

    await custody_service.append_event(command=command1)

    command2 = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
        event_metadata={
            "case_reference": "CASE-999",
        },
    )

    with pytest.raises(CustodyIdempotencyConflictError):
        await custody_service.append_event(command=command2)
        
           
@pytest.mark.asyncio
async def test_append_custody_event_idempotency_conflict_when_metadata_changes(
    custody_service: CustodyService,
    test_evidence: Evidence,
    test_user,
):
    idempotency_key = f"idemp-{uuid4().hex}"

    command1 = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
        event_metadata={
            "case_reference": "CASE-001",
        },
    )

    result1 = await custody_service.append_event(
        command=command1,
    )

    assert result1.replayed is False

    command2 = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Reviewed evidence",
        idempotency_key=idempotency_key,
        correlation_id=str(uuid4()),
        event_metadata={
            "case_reference": "CASE-999",
        },
    )

    with pytest.raises(CustodyIdempotencyConflictError):
        await custody_service.append_event(
            command=command2,
        )

         
@pytest.mark.asyncio
async def test_persisted_custody_record_is_cryptographically_verifiable(
    db_session: AsyncSession,
    custody_service: CustodyService,
    signer: RSAPSSSHA256Signer,
    test_evidence: Evidence,
    test_user,
):
    command = AppendCustodyEventCommand(
        evidence_id=test_evidence.id,
        actor_user_id=test_user.id,
        event_type=CustodyEventType.VIEWED,
        purpose="Independent cryptographic verification",
        idempotency_key=f"idemp-{uuid4().hex}",
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata={
            "case_reference": "CASE-CRYPTO-001",
        },
    )

    result = await custody_service.append_event(
        command=command,
    )

    custody = result.custody_record

    integrity = build_custody_integrity(
        evidence_id=custody.evidence_id,
        actor_user_id=custody.actor_user_id,
        from_user_id=custody.from_user_id,
        to_user_id=custody.to_user_id,
        previous_record_id=custody.previous_record_id,
        previous_record_hash=custody.previous_record_hash,
        transfer_id=custody.transfer_id,
        event_type=custody.event_type,
        purpose=custody.purpose,
        source_ip=custody.source_ip,
        device_identifier=custody.device_identifier,
        event_metadata=dict(custody.event_metadata or {}),
        occurred_at=custody.occurred_at,
    )

    assert integrity.record_hash == custody.record_hash

    envelope = DigitalSignatureEnvelope.from_json(
        custody.digital_signature,
    )

    assert signer.verify(
        integrity.canonical_bytes,
        envelope,
    )

         