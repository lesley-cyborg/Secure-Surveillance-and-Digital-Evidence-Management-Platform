from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
    VerificationStatus,
)
from app.db.models.evidence import (
    EvidenceVerification,
)
from app.db.models.incidents import Incident
from app.modules.evidence.contracts import (
    PreparedEvidenceKey,
    PreparedEvidenceRecord,
)
from app.modules.evidence.identifiers import (
    generate_evidence_number,
)
from app.modules.evidence.repository import (
    EvidenceRepository,
)
from app.modules.evidence.verification import (
    evidence_status_after_verification,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def create_incident(
    session: AsyncSession,
) -> Incident:
    now = datetime.now(UTC)
    unique = uuid4().hex[:12]

    incident = Incident(
        incident_number=(f"INC-EVIDENCE-{unique}"),
        primary_camera_id=None,
        created_by_user_id=None,
        source_type=IncidentSourceType.AI,
        incident_type="EVIDENCE_TEST",
        severity=Severity.HIGH,
        priority=Priority.HIGH,
        status=IncidentStatus.NEW,
        title="Evidence persistence test",
        description=None,
        disposition=None,
        detected_at=now,
        confirmed_at=None,
        closed_at=None,
    )

    session.add(incident)
    await session.flush()

    return incident


def create_prepared_record(
    *,
    incident_id: object,
    source_artifact_id: UUID | None = None,
) -> PreparedEvidenceRecord:

    if not isinstance(incident_id, UUID):
        raise TypeError("incident_id must be UUID")

    captured_at = datetime.now(UTC)

    evidence_number = generate_evidence_number(captured_at=captured_at)

    return PreparedEvidenceRecord(
        evidence_number=evidence_number,
        incident_id=incident_id,
        source_detection_id=None,
        submitted_by_user_id=None,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=EvidenceType.IMAGE,
        original_filename=("integration-frame.jpg"),
        mime_type="image/jpeg",
        file_size_bytes=8192,
        storage_bucket="evidence",
        storage_object_key=(f"integration/{evidence_number}/payload.enc"),
        storage_version_id=None,
        original_sha256="a" * 64,
        encrypted_sha256="b" * 64,
        manifest_sha256="c" * 64,
        digital_signature=("integration-test-signature"),
        status=EvidenceStatus.STORED,
        captured_at=captured_at,
        ingested_at=(captured_at + timedelta(seconds=1)),
        source_artifact_id=(source_artifact_id),
    )


@pytest.mark.asyncio
async def test_evidence_metadata_and_key_are_persisted(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    record = create_prepared_record(incident_id=incident.id)

    evidence = await repository.create(record=record)

    key = await repository.create_key(
        evidence_id=evidence.id,
        key=PreparedEvidenceKey(
            algorithm="AES-256-GCM",
            wrapped_key=("integration-wrapped-key"),
            key_reference=("test://master-key/v1"),
            key_version=1,
        ),
    )

    await db_session.commit()

    persisted = await repository.get_by_id(evidence.id)

    assert persisted is not None

    assert persisted.evidence_number == record.evidence_number
    assert persisted.incident_id == incident.id
    assert persisted.source_type is EvidenceSourceType.EXTERNAL_IMPORT
    assert persisted.evidence_type is EvidenceType.IMAGE
    assert persisted.status is EvidenceStatus.STORED

    assert persisted.original_sha256 == "a" * 64
    assert persisted.encrypted_sha256 == "b" * 64
    assert persisted.manifest_sha256 == "c" * 64

    active_key = await repository.get_active_key(evidence.id)

    assert active_key is not None
    assert active_key.id == key.id
    assert active_key.algorithm == "AES-256-GCM"
    assert active_key.key_version == 1
    assert active_key.is_active is True


@pytest.mark.asyncio
async def test_evidence_can_be_resolved_by_number(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    record = create_prepared_record(incident_id=incident.id)

    created = await repository.create(record=record)

    await db_session.commit()

    persisted = await repository.get_by_evidence_number(record.evidence_number)

    assert persisted is not None
    assert persisted.id == created.id


@pytest.mark.asyncio
async def test_evidence_can_be_resolved_by_storage_key(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    record = create_prepared_record(incident_id=incident.id)

    created = await repository.create(record=record)

    await db_session.commit()

    persisted = await repository.get_by_storage_object_key(record.storage_object_key)

    assert persisted is not None
    assert persisted.id == created.id

    # Non-AI/external evidence does not
    # require an AI artifact identity.
    assert persisted.source_artifact_id is None


@pytest.mark.asyncio
async def test_evidence_can_be_resolved_by_source_artifact_id(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    artifact_id = uuid4()

    record = create_prepared_record(
        incident_id=incident.id,
        source_artifact_id=artifact_id,
    )

    created = await repository.create(record=record)

    await db_session.commit()

    persisted = await repository.get_by_source_artifact_id(artifact_id)

    assert persisted is not None
    assert persisted.id == created.id

    assert persisted.source_artifact_id == artifact_id


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_unknown_evidence(
    db_session: AsyncSession,
) -> None:
    repository = EvidenceRepository(db_session)

    persisted = await repository.get_by_id(uuid4())

    assert persisted is None


@pytest.mark.asyncio
async def test_get_active_key_ignores_inactive_key(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    record = create_prepared_record(incident_id=incident.id)

    evidence = await repository.create(record=record)

    key = await repository.create_key(
        evidence_id=evidence.id,
        key=PreparedEvidenceKey(
            algorithm="AES-256-GCM",
            wrapped_key=("integration-inactive-wrapped-key"),
            key_reference=("test://master-key/inactive/v1"),
            key_version=1,
        ),
    )

    # Simulate a rotated/deactivated key.
    key.is_active = False

    await db_session.commit()

    active_key = await repository.get_active_key(evidence.id)

    assert active_key is None


@pytest.mark.asyncio
async def test_verified_outcome_is_persisted(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    evidence = await repository.create(record=create_prepared_record(incident_id=incident.id))

    await db_session.commit()

    locked = await repository.get_by_id_for_update(evidence.id)

    assert locked is not None

    verified_at = datetime.now(UTC)

    verification = await repository.create_verification(
        evidence_id=locked.id,
        verified_by_user_id=None,
        expected_sha256=(locked.encrypted_sha256),
        calculated_sha256=(locked.encrypted_sha256),
        hash_matches=True,
        signature_valid=True,
        verification_status=(VerificationStatus.VERIFIED),
        failure_reason=None,
        verified_at=verified_at,
    )

    target_status = evidence_status_after_verification(
        current_status=locked.status,
        verification_status=(verification.verification_status),
    )

    await repository.set_status(
        evidence=locked,
        status=target_status,
    )

    await db_session.commit()

    persisted = await repository.get_by_id(evidence.id)

    assert persisted is not None
    assert persisted.status is EvidenceStatus.VERIFIED

    result = await db_session.execute(
        select(EvidenceVerification).where(EvidenceVerification.id == verification.id)
    )

    persisted_verification = result.scalar_one()

    assert persisted_verification.verification_status is VerificationStatus.VERIFIED
    assert persisted_verification.hash_matches is True
    assert persisted_verification.signature_valid is True
    assert persisted_verification.failure_reason is None


@pytest.mark.asyncio
async def test_hash_mismatch_marks_evidence_compromised(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    evidence = await repository.create(record=create_prepared_record(incident_id=incident.id))

    await db_session.commit()

    locked = await repository.get_by_id_for_update(evidence.id)

    assert locked is not None

    calculated_sha256 = "d" * 64

    verification = await repository.create_verification(
        evidence_id=locked.id,
        verified_by_user_id=None,
        expected_sha256=(locked.encrypted_sha256),
        calculated_sha256=(calculated_sha256),
        hash_matches=False,
        signature_valid=False,
        verification_status=(VerificationStatus.HASH_MISMATCH),
        failure_reason=("Evidence integrity verification failed."),
        verified_at=datetime.now(UTC),
    )

    await repository.set_status(
        evidence=locked,
        status=(
            evidence_status_after_verification(
                current_status=locked.status,
                verification_status=(verification.verification_status),
            )
        ),
    )

    await db_session.commit()

    persisted = await repository.get_by_id(evidence.id)

    assert persisted is not None
    assert persisted.status is EvidenceStatus.COMPROMISED


@pytest.mark.asyncio
async def test_invalid_signature_marks_evidence_compromised(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    evidence = await repository.create(record=create_prepared_record(incident_id=incident.id))

    await db_session.commit()

    locked = await repository.get_by_id_for_update(evidence.id)

    assert locked is not None

    verification = await repository.create_verification(
        evidence_id=locked.id,
        verified_by_user_id=None,
        expected_sha256=(locked.encrypted_sha256),
        calculated_sha256=(locked.encrypted_sha256),
        hash_matches=True,
        signature_valid=False,
        verification_status=(VerificationStatus.SIGNATURE_INVALID),
        failure_reason=("Stored digital signature verification failed."),
        verified_at=datetime.now(UTC),
    )

    await repository.set_status(
        evidence=locked,
        status=(
            evidence_status_after_verification(
                current_status=locked.status,
                verification_status=(verification.verification_status),
            )
        ),
    )

    await db_session.commit()

    persisted = await repository.get_by_id(evidence.id)

    assert persisted is not None
    assert persisted.status is EvidenceStatus.COMPROMISED


@pytest.mark.asyncio
async def test_unavailable_verification_preserves_stored_status(
    db_session: AsyncSession,
) -> None:
    incident = await create_incident(db_session)

    repository = EvidenceRepository(db_session)

    evidence = await repository.create(record=create_prepared_record(incident_id=incident.id))

    await db_session.commit()

    locked = await repository.get_by_id_for_update(evidence.id)

    assert locked is not None
    assert locked.status is EvidenceStatus.STORED

    verification = await repository.create_verification(
        evidence_id=locked.id,
        verified_by_user_id=None,
        expected_sha256=(locked.encrypted_sha256),
        calculated_sha256=None,
        hash_matches=False,
        signature_valid=False,
        verification_status=(VerificationStatus.UNAVAILABLE),
        failure_reason=("Evidence object unavailable."),
        verified_at=datetime.now(UTC),
    )

    await repository.set_status(
        evidence=locked,
        status=(
            evidence_status_after_verification(
                current_status=locked.status,
                verification_status=(verification.verification_status),
            )
        ),
    )

    await db_session.commit()

    persisted = await repository.get_by_id(evidence.id)

    assert persisted is not None
    assert persisted.status is EvidenceStatus.STORED
