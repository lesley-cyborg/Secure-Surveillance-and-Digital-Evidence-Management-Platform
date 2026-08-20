from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.core.config import get_settings
from app.core.security import hash_password
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
    VerificationStatus,
)
from app.db.models.evidence import (
    CustodyRecord,
    Evidence,
    EvidenceKey,
    EvidenceVerification,
)
from app.db.models.incidents import Incident
from app.db.models.reporting import AuditLog
from app.db.models.surveillance import (
    Camera,
    Site,
)
from app.modules.audit.actions import AuditAction
from app.modules.auth.repository import (
    UserRepository,
)
from app.modules.custody.integrity import (
    build_custody_integrity,
)
from app.modules.evidence.content_access import (
    EvidenceContentAccessCommand,
    EvidenceContentAccessService,
)
from app.modules.evidence.contracts import (
    PreparedEvidenceKey,
    PreparedEvidenceRecord,
)
from app.modules.evidence.crypto import (
    SecuredEvidenceArtifact,
    decrypt_evidence,
)
from app.modules.evidence.errors import (
    EvidenceIngestionCompensationError,
    EvidenceObjectNotFoundError,
    EvidenceReferenceError,
    EvidenceRetrievalUnavailableError,
    EvidenceStorageUnavailableError,
)
from app.modules.evidence.forensics import (
    EvidenceForensicManifest,
    build_manifest_artifact,
)
from app.modules.evidence.key_wrapping import (
    RSAOAEPKeyWrapper,
    WrappedEvidenceKey,
)
from app.modules.evidence.minio_storage import (
    MinioEvidenceObjectStorage,
)
from app.modules.evidence.service import (
    EvidenceIngestionCommand,
    SecureEvidenceIngestionService,
)
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    RSAPSSSHA256Signer,
    build_evidence_signature_payload,
)
from app.modules.evidence.storage import (
    StoredEvidenceObject,
)
from app.modules.evidence.verification_orchestrator import (
    EvidenceVerificationOrchestrator,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)
from sqlalchemy import func, select, update
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
)
from sqlalchemy.ext.asyncio import AsyncSession

_CONTENT = b"secure-surveillance-platform-phase-6.2f-evidence"


class RecordingStorage:
    """Thin probe around the real MinIO adapter.

    This does not mock object storage. Every operation still goes to
    MinIO; the wrapper only records uploads so compensation can be
    asserted precisely.
    """

    def __init__(
        self,
        delegate: MinioEvidenceObjectStorage,
    ) -> None:
        self.delegate = delegate
        self.put_count = 0
        self.last_stored: StoredEvidenceObject | None = None

    async def ensure_ready(self) -> None:
        await self.delegate.ensure_ready()

    async def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        metadata: (Mapping[str, str] | None) = None,
    ) -> StoredEvidenceObject:
        self.put_count += 1

        stored = await self.delegate.put_object(
            object_key=object_key,
            payload=payload,
            content_type=content_type,
            metadata=metadata,
        )

        self.last_stored = stored

        return stored

    async def get_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        return await self.delegate.get_object(
            object_key=object_key,
            version_id=version_id,
        )

    async def stat_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> StoredEvidenceObject:
        return await self.delegate.stat_object(
            object_key=object_key,
            version_id=version_id,
        )

    async def delete_for_compensation(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> None:
        await self.delegate.delete_for_compensation(
            object_key=object_key,
            version_id=version_id,
        )


class FailingPutStorage:
    """Fail deterministically before any object is uploaded."""

    def __init__(
        self,
        delegate: MinioEvidenceObjectStorage,
    ) -> None:
        self.delegate = delegate
        self.put_count = 0

    async def ensure_ready(self) -> None:
        await self.delegate.ensure_ready()

    async def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> StoredEvidenceObject:
        del (
            object_key,
            payload,
            content_type,
            metadata,
        )

        self.put_count += 1

        raise EvidenceStorageUnavailableError("Forced evidence storage failure")

    async def get_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        return await self.delegate.get_object(
            object_key=object_key,
            version_id=version_id,
        )

    async def stat_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> StoredEvidenceObject:
        return await self.delegate.stat_object(
            object_key=object_key,
            version_id=version_id,
        )

    async def delete_for_compensation(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> None:
        await self.delegate.delete_for_compensation(
            object_key=object_key,
            version_id=version_id,
        )


class FailingCompensationStorage:
    """Upload normally but fail compensating deletion."""

    def __init__(
        self,
        delegate: MinioEvidenceObjectStorage,
    ) -> None:
        self.delegate = delegate

        self.put_count = 0
        self.delete_count = 0

        self.last_stored: StoredEvidenceObject | None = None

    async def ensure_ready(self) -> None:
        await self.delegate.ensure_ready()

    async def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> StoredEvidenceObject:
        self.put_count += 1

        stored = await self.delegate.put_object(
            object_key=object_key,
            payload=payload,
            content_type=content_type,
            metadata=metadata,
        )

        self.last_stored = stored

        return stored

    async def get_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        return await self.delegate.get_object(
            object_key=object_key,
            version_id=version_id,
        )

    async def stat_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> StoredEvidenceObject:
        return await self.delegate.stat_object(
            object_key=object_key,
            version_id=version_id,
        )

    async def delete_for_compensation(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> None:
        del (
            object_key,
            version_id,
        )

        self.delete_count += 1

        raise EvidenceStorageUnavailableError("Forced compensation failure")


@pytest.fixture(scope="module")
def key_wrapper() -> RSAOAEPKeyWrapper:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAOAEPKeyWrapper(
        public_key=(private_key.public_key()),
        private_key=private_key,
        key_reference=("test://evidence-wrap/v1"),
        key_version=1,
    )


@pytest.fixture(scope="module")
def signer() -> RSAPSSSHA256Signer:
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096,
    )

    return RSAPSSSHA256Signer(
        public_key=(private_key.public_key()),
        private_key=private_key,
        key_reference=("test://evidence-signing/v1"),
        key_version=1,
    )


@pytest.fixture
async def real_storage() -> MinioEvidenceObjectStorage:
    storage = MinioEvidenceObjectStorage.from_settings(get_settings())

    await storage.ensure_ready()

    return storage


async def seed_incident(
    session: AsyncSession,
) -> UUID:
    unique = uuid4().hex[:12]
    detected_at = datetime.now(UTC)

    site = Site(
        name=(f"Evidence Integration Site {unique}"),
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
        name=(f"Evidence Camera {unique}"),
        camera_code=(f"EVD-CAM-{unique}"),
        ip_address="10.44.55.66",
        protocol="RTSP",
        stream_url_encrypted=("encrypted://evidence-test"),
        credentials_secret_ref=(f"secret://camera/{unique}"),
        status=CameraStatus.ONLINE,
        location_description=("Evidence orchestration integration camera"),
        is_active=True,
        last_seen_at=detected_at,
    )

    session.add(camera)

    await session.flush()

    incident = Incident(
        incident_number=(f"INC-EVD-{unique}"),
        primary_camera_id=camera.id,
        created_by_user_id=None,
        source_type=(IncidentSourceType.MANUAL),
        incident_type=("FORENSIC_EVIDENCE_TEST"),
        severity=Severity.MEDIUM,
        priority=Priority.NORMAL,
        status=IncidentStatus.NEW,
        title=("Evidence ingestion integration incident"),
        description=("Integration fixture for secure evidence ingestion"),
        disposition=None,
        detected_at=detected_at,
        confirmed_at=None,
        closed_at=None,
    )

    session.add(incident)

    await session.flush()

    incident_id = incident.id

    await session.commit()

    return incident_id


async def seed_evidence_actor(
    session: AsyncSession,
) -> UUID:
    unique = uuid4().hex[:12]

    repository = UserRepository(session)

    user = await repository.create(
        email=(f"evidence-e2e-{unique}@example.test"),
        username=(f"evidence_e2e_{unique}"),
        password_hash=hash_password("Evidence-E2E-Test-Password-123!"),
        first_name="Evidence",
        last_name="Investigator",
    )

    actor_id = user.id

    await session.commit()

    return actor_id


def create_command(
    *,
    incident_id: UUID,
) -> EvidenceIngestionCommand:
    return EvidenceIngestionCommand(
        incident_id=incident_id,
        source_detection_id=None,
        submitted_by_user_id=None,
        source_type=(EvidenceSourceType.EXTERNAL_IMPORT),
        evidence_type=EvidenceType.IMAGE,
        original_filename=("integration-frame.jpg"),
        mime_type="image/jpeg",
        captured_at=datetime.now(UTC),
        content=_CONTENT,
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent=("pytest/secure-evidence"),
        device_identifier=("pytest-integration"),
    )


async def load_active_evidence_key(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> EvidenceKey:
    statement = select(EvidenceKey).where(
        EvidenceKey.evidence_id == evidence_id,
        EvidenceKey.is_active.is_(True),
    )

    result = await session.execute(statement)

    key = result.scalar_one_or_none()

    assert key is not None

    return key


@pytest.mark.asyncio
async def test_secure_evidence_ingestion_is_persisted_end_to_end(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
) -> None:
    incident_id = await seed_incident(db_session)

    command = create_command(incident_id=incident_id)

    service = SecureEvidenceIngestionService(
        session=db_session,
        storage=real_storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    result = await service.ingest(command=command)

    assert result.storage_version_id is not None

    evidence = await db_session.get(
        Evidence,
        result.evidence_id,
    )

    assert evidence is not None

    assert evidence.evidence_number == result.evidence_number

    assert evidence.incident_id == incident_id

    assert evidence.source_detection_id is None

    assert evidence.source_type is EvidenceSourceType.EXTERNAL_IMPORT

    assert evidence.evidence_type is EvidenceType.IMAGE

    assert evidence.status is EvidenceStatus.STORED

    assert evidence.original_sha256 == hashlib.sha256(_CONTENT).hexdigest()

    assert evidence.original_sha256 == result.original_sha256

    assert evidence.encrypted_sha256 == result.encrypted_sha256

    assert evidence.manifest_sha256 == result.manifest_sha256

    assert evidence.storage_bucket == result.storage_bucket

    assert evidence.storage_object_key == result.storage_object_key

    assert evidence.storage_version_id == result.storage_version_id

    evidence_key = await load_active_evidence_key(
        db_session,
        evidence_id=evidence.id,
    )

    assert evidence_key.algorithm == "RSA-OAEP-SHA256"

    assert evidence_key.key_version == 1
    assert evidence_key.is_active is True
    assert evidence_key.wrapped_key
    assert evidence_key.key_reference

    custody = await db_session.get(
        CustodyRecord,
        result.custody_record_id,
    )

    assert custody is not None

    assert custody.evidence_id == evidence.id

    assert custody.event_type is CustodyEventType.ACQUIRED

    assert custody.previous_record_id is None
    assert custody.transfer_id is None

    assert len(custody.record_hash) == 64

    audit = await db_session.get(
        AuditLog,
        result.audit_log_id,
    )

    assert audit is not None

    assert audit.action == AuditAction.EVIDENCE_INGESTED.value

    assert audit.resource_type == "evidence"

    assert audit.resource_id == evidence.id

    assert audit.outcome is AuditOutcome.SUCCESS

    assert audit.correlation_id == command.correlation_id

    audit_details = audit.details

    assert audit_details["custody_record_id"] == str(custody.id)

    downloaded = await real_storage.get_object(
        object_key=(evidence.storage_object_key),
        version_id=(evidence.storage_version_id),
    )

    assert hashlib.sha256(downloaded).hexdigest() == evidence.encrypted_sha256

    manifest = EvidenceForensicManifest(
        evidence_number=(evidence.evidence_number),
        incident_id=evidence.incident_id,
        source_detection_id=(evidence.source_detection_id),
        source_type=evidence.source_type,
        evidence_type=evidence.evidence_type,
        original_filename=(evidence.original_filename),
        mime_type=evidence.mime_type,
        file_size_bytes=(evidence.file_size_bytes),
        original_sha256=(evidence.original_sha256),
        captured_at=evidence.captured_at,
    )

    manifest_artifact = build_manifest_artifact(manifest)

    assert manifest_artifact.sha256 == evidence.manifest_sha256

    wrapped_key = WrappedEvidenceKey(
        algorithm=evidence_key.algorithm,
        wrapped_key=(evidence_key.wrapped_key),
        key_reference=(evidence_key.key_reference),
        key_version=(evidence_key.key_version),
    )

    encrypted_artifact = SecuredEvidenceArtifact(
        encrypted_payload=downloaded,
        encrypted_sha256=(evidence.encrypted_sha256),
        wrapped_key=wrapped_key,
    )

    plaintext = decrypt_evidence(
        encrypted_artifact,
        manifest=manifest_artifact,
        key_wrapper=key_wrapper,
    )

    assert plaintext == _CONTENT

    evidence_signature = DigitalSignatureEnvelope.from_json(evidence.digital_signature)

    evidence_signature_payload = build_evidence_signature_payload(
        evidence_number=(evidence.evidence_number),
        incident_id=(evidence.incident_id),
        source_detection_id=(evidence.source_detection_id),
        storage_bucket=(evidence.storage_bucket),
        storage_object_key=(evidence.storage_object_key),
        storage_version_id=(evidence.storage_version_id),
        original_sha256=(evidence.original_sha256),
        encrypted_sha256=(evidence.encrypted_sha256),
        manifest_sha256=(evidence.manifest_sha256),
        captured_at=(evidence.captured_at),
        ingested_at=(evidence.ingested_at),
    )

    assert signer.verify(
        evidence_signature_payload,
        evidence_signature,
    )

    custody_metadata = custody.event_metadata

    custody_integrity = build_custody_integrity(
        evidence_id=custody.evidence_id,
        actor_user_id=(custody.actor_user_id),
        from_user_id=(custody.from_user_id),
        to_user_id=(custody.to_user_id),
        previous_record_id=(custody.previous_record_id),
        previous_record_hash=None,
        transfer_id=(custody.transfer_id),
        event_type=(custody.event_type),
        purpose=custody.purpose,
        source_ip=(str(custody.source_ip) if custody.source_ip is not None else None),
        device_identifier=(custody.device_identifier),
        event_metadata=(custody_metadata),
        occurred_at=(custody.occurred_at),
    )

    assert custody_integrity.record_hash == custody.record_hash

    custody_signature = DigitalSignatureEnvelope.from_json(custody.digital_signature)

    assert signer.verify(
        custody_integrity.canonical_bytes,
        custody_signature,
    )

    audit_id = audit.id
    custody_id = custody.id

    # PostgreSQL independently protects
    # both forensic tables from mutation.
    with pytest.raises(DBAPIError):
        await db_session.execute(
            update(AuditLog).where(AuditLog.id == audit_id).values(action="TAMPERED")
        )

    await db_session.rollback()

    with pytest.raises(DBAPIError):
        await db_session.execute(
            update(CustodyRecord).where(CustodyRecord.id == custody_id).values(purpose="tampered")
        )

    await db_session.rollback()


@pytest.mark.asyncio
async def test_database_failure_rolls_back_and_compensates_minio(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = await seed_incident(db_session)

    command = create_command(incident_id=incident_id)

    storage = RecordingStorage(real_storage)

    service = SecureEvidenceIngestionService(
        session=db_session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    original_create_key = service.evidence.create_key

    async def create_duplicate_key(
        *,
        evidence_id: UUID,
        key: PreparedEvidenceKey,
    ) -> EvidenceKey:
        first = await original_create_key(
            evidence_id=evidence_id,
            key=key,
        )

        # The first INSERT is real.
        # The second INSERT intentionally violates
        # the PostgreSQL evidence/version uniqueness
        # rule and forces the DB-stage rollback.
        await original_create_key(
            evidence_id=evidence_id,
            key=key,
        )

        return first

    monkeypatch.setattr(
        service.evidence,
        "create_key",
        create_duplicate_key,
    )

    with pytest.raises(IntegrityError):
        await service.ingest(command=command)

    assert storage.put_count == 1

    stored = storage.last_stored

    assert stored is not None
    assert stored.version_id is not None

    evidence_count = await db_session.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.incident_id == incident_id)
    )

    assert int(evidence_count or 0) == 0

    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.correlation_id == command.correlation_id)
    )

    assert int(audit_count or 0) == 0

    # The exact MinIO version uploaded before
    # PostgreSQL failed must have been removed.
    with pytest.raises(EvidenceObjectNotFoundError):
        await real_storage.stat_object(
            object_key=stored.object_key,
            version_id=stored.version_id,
        )


@pytest.mark.asyncio
async def test_invalid_incident_reference_never_uploads_to_minio(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
) -> None:
    storage = RecordingStorage(real_storage)

    service = SecureEvidenceIngestionService(
        session=db_session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    command = create_command(incident_id=uuid4())

    with pytest.raises(EvidenceReferenceError):
        await service.ingest(command=command)

    assert storage.put_count == 0
    assert storage.last_stored is None


@pytest.mark.asyncio
async def test_storage_failure_creates_no_database_evidence(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
) -> None:
    incident_id = await seed_incident(db_session)

    command = create_command(incident_id=incident_id)

    storage = FailingPutStorage(real_storage)

    service = SecureEvidenceIngestionService(
        session=db_session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    with pytest.raises(EvidenceStorageUnavailableError):
        await service.ingest(command=command)

    assert storage.put_count == 1

    # The service's preflight query must not
    # leave an open transaction after the
    # storage operation fails.
    assert not db_session.in_transaction()

    evidence_count = await db_session.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.incident_id == incident_id)
    )

    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.correlation_id == command.correlation_id)
    )

    assert int(evidence_count or 0) == 0
    assert int(audit_count or 0) == 0


@pytest.mark.asyncio
async def test_compensation_failure_is_not_silenced(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = await seed_incident(db_session)

    command = create_command(incident_id=incident_id)

    storage = FailingCompensationStorage(real_storage)

    service = SecureEvidenceIngestionService(
        session=db_session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    async def fail_evidence_create(
        *,
        record: PreparedEvidenceRecord,
    ) -> Evidence:
        del record

        raise RuntimeError("Forced PostgreSQL-stage failure")

    monkeypatch.setattr(
        service.evidence,
        "create",
        fail_evidence_create,
    )

    try:
        with pytest.raises(
            EvidenceIngestionCompensationError,
            match=("PostgreSQL evidence transaction failed and MinIO compensation also failed"),
        ) as exception_info:
            await service.ingest(command=command)

        assert storage.put_count == 1
        assert storage.delete_count == 1

        assert isinstance(
            exception_info.value.__cause__,
            EvidenceStorageUnavailableError,
        )

        stored = storage.last_stored

        assert stored is not None
        assert stored.version_id is not None

        # PostgreSQL must still have rolled back
        # even though MinIO cleanup subsequently
        # failed.
        evidence_count = await db_session.scalar(
            select(func.count()).select_from(Evidence).where(Evidence.incident_id == incident_id)
        )

        audit_count = await db_session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.correlation_id == command.correlation_id)
        )

        assert int(evidence_count or 0) == 0
        assert int(audit_count or 0) == 0

        # Because compensation deliberately
        # failed, the exact uploaded version
        # should still exist.
        persisted_object = await real_storage.stat_object(
            object_key=(stored.object_key),
            version_id=(stored.version_id),
        )

        assert persisted_object.object_key == stored.object_key

        assert persisted_object.version_id == stored.version_id

    finally:
        stored = storage.last_stored

        # Test cleanup must use the real delegate,
        # not the deliberately failing wrapper.
        if stored is not None:
            await real_storage.delete_for_compensation(
                object_key=(stored.object_key),
                version_id=(stored.version_id),
            )


@pytest.mark.asyncio
async def test_cancellation_after_upload_rolls_back_and_compensates(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    incident_id = await seed_incident(db_session)

    command = create_command(incident_id=incident_id)

    storage = RecordingStorage(real_storage)

    service = SecureEvidenceIngestionService(
        session=db_session,
        storage=storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    original_validate_references = service._validate_references

    async def cancel_after_upload(
        command_to_validate: (EvidenceIngestionCommand),
        *,
        lock: bool,
    ) -> None:
        if lock:
            raise asyncio.CancelledError

        await original_validate_references(
            command_to_validate,
            lock=lock,
        )

    monkeypatch.setattr(
        service,
        "_validate_references",
        cancel_after_upload,
    )

    with pytest.raises(asyncio.CancelledError):
        await service.ingest(command=command)

    assert storage.put_count == 1

    stored = storage.last_stored

    assert stored is not None
    assert stored.version_id is not None

    # Cancellation is explicitly handled by
    # SecureEvidenceIngestionService.
    assert not db_session.in_transaction()

    evidence_count = await db_session.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.incident_id == incident_id)
    )

    audit_count = await db_session.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.correlation_id == command.correlation_id)
    )

    assert int(evidence_count or 0) == 0
    assert int(audit_count or 0) == 0

    # The exact MinIO version uploaded before
    # cancellation must have been compensated.
    with pytest.raises(EvidenceObjectNotFoundError):
        await real_storage.stat_object(
            object_key=stored.object_key,
            version_id=stored.version_id,
        )


@pytest.mark.asyncio
async def test_real_verification_and_content_retrieval_end_to_end(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
) -> None:
    incident_id = await seed_incident(db_session)

    actor_user_id = await seed_evidence_actor(db_session)

    ingestion_command = create_command(incident_id=incident_id)

    ingestion_service = SecureEvidenceIngestionService(
        session=db_session,
        storage=real_storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    ingested = await ingestion_service.ingest(command=ingestion_command)

    assert ingested.storage_version_id is not None

    orchestrator = EvidenceVerificationOrchestrator(
        session=db_session,
        storage=real_storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    content_service = EvidenceContentAccessService(
        session=db_session,
        orchestrator=orchestrator,
        signer=signer,
    )

    retrieval_command = EvidenceContentAccessCommand(
        evidence_id=ingested.evidence_id,
        actor_user_id=actor_user_id,
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent=("pytest/evidence-retrieval-e2e"),
        device_identifier=("pytest-integration"),
    )

    try:
        retrieved = await content_service.retrieve(command=retrieval_command)

        assert retrieved.evidence_id == (ingested.evidence_id)

        assert retrieved.content == _CONTENT

        assert retrieved.original_filename == ingestion_command.original_filename

        assert retrieved.original_sha256 == hashlib.sha256(_CONTENT).hexdigest()

        evidence = await db_session.get(
            Evidence,
            ingested.evidence_id,
        )

        assert evidence is not None

        await db_session.refresh(evidence)

        assert evidence.status is EvidenceStatus.VERIFIED

        verification_result = await db_session.scalars(
            select(EvidenceVerification)
            .where(EvidenceVerification.evidence_id == evidence.id)
            .order_by(
                EvidenceVerification.verified_at,
                EvidenceVerification.id,
            )
        )

        verifications = list(verification_result.all())

        assert len(verifications) == 1

        verification = verifications[0]

        assert verification.verification_status is VerificationStatus.VERIFIED

        assert verification.hash_matches is True
        assert verification.signature_valid is True

        assert verification.verified_by_user_id == actor_user_id

        custody_result = await db_session.scalars(
            select(CustodyRecord)
            .where(CustodyRecord.evidence_id == evidence.id)
            .order_by(
                CustodyRecord.occurred_at,
                CustodyRecord.created_at,
                CustodyRecord.id,
            )
        )

        custody_records = list(custody_result.all())

        assert [record.event_type for record in custody_records] == [
            CustodyEventType.ACQUIRED,
            CustodyEventType.VERIFIED,
            CustodyEventType.VIEWED,
        ]

        assert custody_records[0].actor_user_id is None

        assert custody_records[1].actor_user_id == actor_user_id

        assert custody_records[2].actor_user_id == actor_user_id

        previous_id: UUID | None = None
        previous_hash: str | None = None

        for custody in custody_records:
            assert custody.previous_record_id == previous_id

            integrity = build_custody_integrity(
                evidence_id=(custody.evidence_id),
                actor_user_id=(custody.actor_user_id),
                from_user_id=(custody.from_user_id),
                to_user_id=(custody.to_user_id),
                previous_record_id=(custody.previous_record_id),
                previous_record_hash=(previous_hash),
                transfer_id=(custody.transfer_id),
                event_type=(custody.event_type),
                purpose=custody.purpose,
                source_ip=(str(custody.source_ip) if custody.source_ip is not None else None),
                device_identifier=(custody.device_identifier),
                event_metadata=(custody.event_metadata),
                occurred_at=(custody.occurred_at),
            )

            assert integrity.record_hash == custody.record_hash

            custody_signature = DigitalSignatureEnvelope.from_json(custody.digital_signature)

            assert signer.verify(
                integrity.canonical_bytes,
                custody_signature,
            )

            previous_id = custody.id
            previous_hash = custody.record_hash

        audit_result = await db_session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_id == evidence.id)
            .order_by(
                AuditLog.occurred_at,
                AuditLog.id,
            )
        )

        audits = list(audit_result.all())

        assert [audit.action for audit in audits] == [
            AuditAction.EVIDENCE_INGESTED.value,
            AuditAction.EVIDENCE_VERIFIED.value,
            (AuditAction.EVIDENCE_CONTENT_VIEWED.value),
        ]

        assert [audit.outcome for audit in audits] == [
            AuditOutcome.SUCCESS,
            AuditOutcome.SUCCESS,
            AuditOutcome.SUCCESS,
        ]

        downloaded = await real_storage.get_object(
            object_key=(ingested.storage_object_key),
            version_id=(ingested.storage_version_id),
        )

        assert hashlib.sha256(downloaded).hexdigest() == ingested.encrypted_sha256

    finally:
        await real_storage.delete_for_compensation(
            object_key=(ingested.storage_object_key),
            version_id=(ingested.storage_version_id),
        )


@pytest.mark.asyncio
async def test_real_missing_minio_version_blocks_content_end_to_end(
    db_session: AsyncSession,
    real_storage: MinioEvidenceObjectStorage,
    key_wrapper: RSAOAEPKeyWrapper,
    signer: RSAPSSSHA256Signer,
) -> None:
    incident_id = await seed_incident(db_session)

    actor_user_id = await seed_evidence_actor(db_session)

    ingestion_service = SecureEvidenceIngestionService(
        session=db_session,
        storage=real_storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    ingested = await ingestion_service.ingest(command=create_command(incident_id=incident_id))

    assert ingested.storage_version_id is not None

    # Remove exactly the immutable version recorded
    # by PostgreSQL. Verification must never fall
    # back to some newer/latest object version.
    await real_storage.delete_for_compensation(
        object_key=(ingested.storage_object_key),
        version_id=(ingested.storage_version_id),
    )

    with pytest.raises(EvidenceObjectNotFoundError):
        await real_storage.stat_object(
            object_key=(ingested.storage_object_key),
            version_id=(ingested.storage_version_id),
        )

    orchestrator = EvidenceVerificationOrchestrator(
        session=db_session,
        storage=real_storage,
        key_wrapper=key_wrapper,
        signer=signer,
    )

    content_service = EvidenceContentAccessService(
        session=db_session,
        orchestrator=orchestrator,
        signer=signer,
    )

    command = EvidenceContentAccessCommand(
        evidence_id=ingested.evidence_id,
        actor_user_id=actor_user_id,
        correlation_id=str(uuid4()),
        source_ip="127.0.0.1",
        user_agent=("pytest/evidence-missing-object-e2e"),
        device_identifier="pytest-integration",
    )

    with pytest.raises(EvidenceRetrievalUnavailableError):
        await content_service.retrieve(command=command)

    evidence = await db_session.get(
        Evidence,
        ingested.evidence_id,
    )

    assert evidence is not None

    await db_session.refresh(evidence)

    # UNAVAILABLE does not falsely classify the
    # evidence itself as compromised.
    assert evidence.status is EvidenceStatus.STORED

    verification_result = await db_session.scalars(
        select(EvidenceVerification).where(EvidenceVerification.evidence_id == evidence.id)
    )

    verifications = list(verification_result.all())

    assert len(verifications) == 1

    assert verifications[0].verification_status is VerificationStatus.UNAVAILABLE

    assert verifications[0].hash_matches is False

    custody_result = await db_session.scalars(
        select(CustodyRecord)
        .where(CustodyRecord.evidence_id == evidence.id)
        .order_by(
            CustodyRecord.occurred_at,
            CustodyRecord.created_at,
            CustodyRecord.id,
        )
    )

    custody_records = list(custody_result.all())

    # No VERIFIED and absolutely no VIEWED record.
    assert [record.event_type for record in custody_records] == [
        CustodyEventType.ACQUIRED,
    ]

    audit_result = await db_session.scalars(
        select(AuditLog)
        .where(AuditLog.resource_id == evidence.id)
        .order_by(
            AuditLog.occurred_at,
            AuditLog.id,
        )
    )

    audits = list(audit_result.all())

    assert [audit.action for audit in audits] == [
        AuditAction.EVIDENCE_INGESTED.value,
        AuditAction.EVIDENCE_VERIFIED.value,
        (AuditAction.EVIDENCE_CONTENT_VIEWED.value),
    ]

    assert [audit.outcome for audit in audits] == [
        AuditOutcome.SUCCESS,
        AuditOutcome.FAILURE,
        AuditOutcome.FAILURE,
    ]
