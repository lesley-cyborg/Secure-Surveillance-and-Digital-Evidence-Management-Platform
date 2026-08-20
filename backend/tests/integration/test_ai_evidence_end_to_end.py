from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from app.core.config import (
    Settings,
    get_settings,
)
from app.db.models.enums import (
    AuditOutcome,
    CameraStatus,
    CustodyEventType,
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
)
from app.db.models.evidence import (
    CustodyRecord,
    Evidence,
    EvidenceKey,
)
from app.db.models.reporting import AuditLog
from app.db.models.surveillance import (
    AIModel,
    Camera,
    DetectionEvent,
    Site,
)
from app.db.session import get_db_session
from app.main import app
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)
from app.modules.ai_ingestion.service import (
    DetectionEventIngestionService,
)
from app.modules.audit.actions import AuditAction
from app.modules.evidence.ai_bridge import (
    AIDetectionEvidenceBridge,
)
from app.modules.evidence.crypto import (
    SecuredEvidenceArtifact,
    decrypt_evidence,
)
from app.modules.evidence.dependencies import (
    get_forensic_signer,
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
from app.modules.evidence.signing import (
    DigitalSignatureEnvelope,
    RSAPSSSHA256Signer,
    build_evidence_signature_payload,
)
from cryptography.hazmat.primitives import (
    serialization,
)
from cryptography.hazmat.primitives.asymmetric import (
    rsa,
)
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

SERVICE_TOKEN = "integration-ai-evidence-e2e-token"

WRAPPING_PRIVATE_KEY_PATH = Path(".secrets/evidence/wrapping-private.pem")


@dataclass(
    frozen=True,
    slots=True,
)
class AIEvidenceTestReferences:
    site: Site
    camera: Camera
    ai_model: AIModel


async def seed_references(
    session: AsyncSession,
) -> AIEvidenceTestReferences:
    unique = uuid4().hex[:12]
    now = datetime.now(UTC)

    site = Site(
        name=(f"AI Evidence E2E Site {unique}"),
        address=("AI evidence end-to-end integration location"),
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
        name=(f"AI Evidence Camera {unique}"),
        camera_code=(f"AI-EVD-CAM-{unique}"),
        ip_address="10.77.88.99",
        protocol="RTSP",
        stream_url_encrypted=("encrypted://ai-evidence-e2e"),
        credentials_secret_ref=(f"secret://camera/{unique}"),
        status=CameraStatus.ONLINE,
        location_description=("AI evidence end-to-end camera"),
        is_active=True,
        last_seen_at=now,
    )

    ai_model = AIModel(
        name=(f"ai-evidence-model-{unique}"),
        model_type="object_detection",
        version="1.0.0",
        framework="pytest",
        artifact_uri=(f"memory://ai-evidence/{unique}"),
        checksum_sha256="a" * 64,
        confidence_threshold=(Decimal("0.5000")),
        is_active=True,
        deployed_at=now,
    )

    session.add_all(
        [
            camera,
            ai_model,
        ]
    )

    await session.flush()

    return AIEvidenceTestReferences(
        site=site,
        camera=camera,
        ai_model=ai_model,
    )


def create_detection_event(
    references: AIEvidenceTestReferences,
    *,
    captured_at: datetime,
) -> DetectionEventIngestionRequest:
    return DetectionEventIngestionRequest.model_validate(
        {
            "schema_version": "1.0",
            "event_type": ("camera.detection.completed"),
            "event_id": str(uuid4()),
            "camera_id": (references.camera.camera_code),
            "frame": {
                "sequence_number": 99,
                "captured_at": (captured_at),
                "received_at": (captured_at),
            },
            "model": {
                "name": (references.ai_model.name),
                "version": (references.ai_model.version),
                "device": "cpu",
            },
            "detections": [
                {
                    "class_id": 1,
                    "label": "weapon",
                    "confidence": 0.95,
                    "bounding_box": {
                        "x_min": 0.1,
                        "y_min": 0.1,
                        "x_max": 0.8,
                        "y_max": 0.8,
                    },
                }
            ],
            "detection_count": 1,
            "inference": {
                "duration_ms": 8.5,
                "processed_at": (captured_at),
            },
        }
    )


def detection_idempotency_key(
    event: DetectionEventIngestionRequest,
) -> str:
    return hashlib.sha256(event.model_dump_json().encode("utf-8")).hexdigest()


async def seed_detection_with_incident(
    session: AsyncSession,
) -> DetectionEvent:
    references = await seed_references(session)

    event = create_detection_event(
        references,
        captured_at=datetime.now(UTC),
    )

    service = DetectionEventIngestionService(session)

    result = await service.ingest(
        event=event,
        idempotency_key=(detection_idempotency_key(event)),
    )

    assert result.incident_id is not None

    statement = select(DetectionEvent).where(DetectionEvent.source_event_id == event.event_id)

    query_result = await session.execute(statement)

    detection = query_result.scalar_one_or_none()

    assert detection is not None
    assert detection.incident_id is not None

    return detection


def create_settings() -> Settings:
    return get_settings().model_copy(
        update={
            "ai_ingestion_enabled": True,
            "ai_ingestion_service_token": (SecretStr(SERVICE_TOKEN)),
        }
    )


@asynccontextmanager
async def create_real_client(
    *,
    session: AsyncSession,
) -> AsyncIterator[httpx.AsyncClient]:
    settings = create_settings()

    async def override_db_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_settings] = lambda: settings

    app.dependency_overrides[get_db_session] = override_db_session

    try:
        transport = httpx.ASGITransport(app=app)

        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://localhost",
        ) as client:
            yield client

    finally:
        app.dependency_overrides.pop(
            get_settings,
            None,
        )

        app.dependency_overrides.pop(
            get_db_session,
            None,
        )


def evidence_path(
    *,
    source_event_id: UUID,
    artifact_id: UUID,
) -> str:
    return str(
        app.url_path_for(
            "ingest_ai_detection_evidence",
            source_event_id=str(source_event_id),
            artifact_id=str(artifact_id),
            artifact_kind="key-frame",
        )
    )


def evidence_headers(
    *,
    content: bytes,
    correlation_id: UUID,
) -> dict[str, str]:
    return {
        "Authorization": (f"Bearer {SERVICE_TOKEN}"),
        "Content-Type": "image/jpeg",
        "Idempotency-Key": (hashlib.sha256(content).hexdigest()),
        "X-Correlation-ID": str(correlation_id),
    }


async def load_evidence_by_artifact(
    session: AsyncSession,
    *,
    artifact_id: UUID,
) -> Evidence:
    statement = select(Evidence).where(Evidence.source_artifact_id == artifact_id)

    result = await session.execute(statement)

    evidence = result.scalar_one_or_none()

    assert evidence is not None

    return evidence


async def load_active_key(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> EvidenceKey:
    statement = select(EvidenceKey).where(
        EvidenceKey.evidence_id == evidence_id,
        EvidenceKey.is_active.is_(True),
    )

    result = await session.execute(statement)

    evidence_key = result.scalar_one_or_none()

    assert evidence_key is not None

    return evidence_key


async def load_acquired_custody(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> CustodyRecord:
    statement = select(CustodyRecord).where(
        CustodyRecord.evidence_id == evidence_id,
        CustodyRecord.event_type == CustodyEventType.ACQUIRED,
    )

    result = await session.execute(statement)

    custody = result.scalar_one_or_none()

    assert custody is not None

    return custody


async def load_ingestion_audit(
    session: AsyncSession,
    *,
    evidence_id: UUID,
) -> AuditLog:
    statement = select(AuditLog).where(
        AuditLog.resource_id == evidence_id,
        AuditLog.action == AuditAction.EVIDENCE_INGESTED.value,
    )

    result = await session.execute(statement)

    audit = result.scalar_one_or_none()

    assert audit is not None

    return audit


def load_test_wrapping_key() -> RSAOAEPKeyWrapper:
    pem = WRAPPING_PRIVATE_KEY_PATH.resolve().read_bytes()

    loaded = serialization.load_pem_private_key(
        pem,
        password=None,
    )

    if not isinstance(
        loaded,
        rsa.RSAPrivateKey,
    ):
        raise TypeError("Test wrapping private key must be RSA")

    settings = get_settings()

    return RSAOAEPKeyWrapper(
        public_key=loaded.public_key(),
        private_key=loaded,
        key_reference=(settings.evidence_wrapping_key_reference),
        key_version=(settings.evidence_wrapping_key_version),
    )


@pytest.mark.asyncio
async def test_real_ai_key_frame_is_stored_as_forensic_evidence(
    db_session: AsyncSession,
) -> None:
    detection = await seed_detection_with_incident(db_session)

    assert detection.incident_id is not None

    artifact_id = uuid4()
    correlation_id = uuid4()

    content = b"real-ai-key-frame-e2e-payload"

    async with create_real_client(session=db_session) as client:
        response = await client.post(
            evidence_path(
                source_event_id=(detection.source_event_id),
                artifact_id=artifact_id,
            ),
            content=content,
            headers=evidence_headers(
                content=content,
                correlation_id=(correlation_id),
            ),
        )

    assert response.status_code == 201

    body = response.json()

    assert body["duplicate"] is False

    assert body["source_event_id"] == str(detection.source_event_id)

    assert body["artifact_id"] == str(artifact_id)

    assert body["correlation_id"] == str(correlation_id)

    assert response.headers["X-Correlation-ID"] == str(correlation_id)

    evidence = await load_evidence_by_artifact(
        db_session,
        artifact_id=artifact_id,
    )

    assert evidence.id == UUID(body["evidence_id"])

    assert evidence.incident_id == detection.incident_id

    assert evidence.source_detection_id == detection.id

    assert evidence.source_artifact_id == artifact_id

    assert evidence.source_type is EvidenceSourceType.AI_CAPTURE

    assert evidence.evidence_type is EvidenceType.IMAGE

    assert evidence.original_filename == f"ai-{artifact_id}.jpg"

    assert evidence.mime_type == "image/jpeg"

    assert evidence.status is EvidenceStatus.STORED

    assert evidence.original_sha256 == hashlib.sha256(content).hexdigest()

    assert evidence.storage_version_id is not None

    evidence_key = await load_active_key(
        db_session,
        evidence_id=evidence.id,
    )

    assert evidence_key.algorithm == "RSA-OAEP-SHA256"

    assert evidence_key.wrapped_key

    assert evidence_key.key_reference == get_settings().evidence_wrapping_key_reference

    custody = await load_acquired_custody(
        db_session,
        evidence_id=evidence.id,
    )

    assert custody.event_type is CustodyEventType.ACQUIRED

    assert custody.evidence_id == evidence.id

    assert custody.digital_signature
    assert len(custody.record_hash) == 64

    audit = await load_ingestion_audit(
        db_session,
        evidence_id=evidence.id,
    )

    assert audit.outcome is AuditOutcome.SUCCESS

    assert audit.correlation_id == str(correlation_id)

    storage = MinioEvidenceObjectStorage.from_settings(get_settings())

    await storage.ensure_ready()

    try:
        encrypted = await storage.get_object(
            object_key=(evidence.storage_object_key),
            version_id=(evidence.storage_version_id),
        )

        assert encrypted != content

        assert hashlib.sha256(encrypted).hexdigest() == evidence.encrypted_sha256

        manifest = EvidenceForensicManifest(
            evidence_number=(evidence.evidence_number),
            incident_id=(evidence.incident_id),
            source_detection_id=(evidence.source_detection_id),
            source_type=(evidence.source_type),
            evidence_type=(evidence.evidence_type),
            original_filename=(evidence.original_filename),
            mime_type=evidence.mime_type,
            file_size_bytes=(evidence.file_size_bytes),
            original_sha256=(evidence.original_sha256),
            captured_at=(evidence.captured_at),
        )

        manifest_artifact = build_manifest_artifact(manifest)

        assert manifest_artifact.sha256 == evidence.manifest_sha256

        wrapped_key = WrappedEvidenceKey(
            algorithm=(evidence_key.algorithm),
            wrapped_key=(evidence_key.wrapped_key),
            key_reference=(evidence_key.key_reference),
            key_version=(evidence_key.key_version),
        )

        encrypted_artifact = SecuredEvidenceArtifact(
            encrypted_payload=encrypted,
            encrypted_sha256=(evidence.encrypted_sha256),
            wrapped_key=wrapped_key,
        )

        plaintext = decrypt_evidence(
            encrypted_artifact,
            manifest=manifest_artifact,
            key_wrapper=(load_test_wrapping_key()),
        )

        assert plaintext == content

        signer = get_forensic_signer()

        assert isinstance(
            signer,
            RSAPSSSHA256Signer,
        )

        evidence_signature = DigitalSignatureEnvelope.from_json(evidence.digital_signature)

        signature_payload = build_evidence_signature_payload(
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
            signature_payload,
            evidence_signature,
        )

    finally:
        await storage.delete_for_compensation(
            object_key=(evidence.storage_object_key),
            version_id=(evidence.storage_version_id),
        )


@pytest.mark.asyncio
async def test_real_ai_artifact_exact_retry_returns_same_evidence(
    db_session: AsyncSession,
) -> None:
    detection = await seed_detection_with_incident(db_session)

    artifact_id = uuid4()
    correlation_id = uuid4()

    content = b"exact-ai-evidence-retry"

    path = evidence_path(
        source_event_id=(detection.source_event_id),
        artifact_id=artifact_id,
    )

    headers = evidence_headers(
        content=content,
        correlation_id=correlation_id,
    )

    async with create_real_client(session=db_session) as client:
        first = await client.post(
            path,
            content=content,
            headers=headers,
        )

        retry = await client.post(
            path,
            content=content,
            headers=headers,
        )

    assert first.status_code == 201
    assert retry.status_code == 200

    first_body = first.json()
    retry_body = retry.json()

    assert first_body["duplicate"] is False
    assert retry_body["duplicate"] is True

    assert retry_body["evidence_id"] == first_body["evidence_id"]

    count = await db_session.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.source_artifact_id == artifact_id)
    )

    assert int(count or 0) == 1

    evidence = await load_evidence_by_artifact(
        db_session,
        artifact_id=artifact_id,
    )

    storage = MinioEvidenceObjectStorage.from_settings(get_settings())

    try:
        assert evidence.original_sha256 == hashlib.sha256(content).hexdigest()

    finally:
        await storage.delete_for_compensation(
            object_key=(evidence.storage_object_key),
            version_id=(evidence.storage_version_id),
        )


@pytest.mark.asyncio
async def test_real_ai_artifact_id_conflict_returns_409(
    db_session: AsyncSession,
) -> None:
    detection = await seed_detection_with_incident(db_session)

    artifact_id = uuid4()
    correlation_id = uuid4()

    original = b"original-ai-artifact"
    changed = b"changed-ai-artifact"

    path = evidence_path(
        source_event_id=(detection.source_event_id),
        artifact_id=artifact_id,
    )

    async with create_real_client(session=db_session) as client:
        first = await client.post(
            path,
            content=original,
            headers=evidence_headers(
                content=original,
                correlation_id=(correlation_id),
            ),
        )

        conflict = await client.post(
            path,
            content=changed,
            headers=evidence_headers(
                content=changed,
                correlation_id=uuid4(),
            ),
        )

    assert first.status_code == 201

    assert conflict.status_code == 409

    conflict_body = conflict.json()

    assert conflict_body["detail"]["code"] == "AI_EVIDENCE_ARTIFACT_CONFLICT"

    count = await db_session.scalar(
        select(func.count()).select_from(Evidence).where(Evidence.source_artifact_id == artifact_id)
    )

    assert int(count or 0) == 1

    evidence = await load_evidence_by_artifact(
        db_session,
        artifact_id=artifact_id,
    )

    assert evidence.original_sha256 == hashlib.sha256(original).hexdigest()

    storage = MinioEvidenceObjectStorage.from_settings(get_settings())

    await storage.delete_for_compensation(
        object_key=(evidence.storage_object_key),
        version_id=(evidence.storage_version_id),
    )


@pytest.mark.asyncio
async def test_concurrent_ai_artifact_uploads_create_one_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = get_settings()

    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for the concurrency integration test")

    test_engine = create_async_engine(
        str(settings.test_database_url),
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={
            "ssl": False,
            "timeout": 10.0,
        },
    )

    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    artifact_id = uuid4()
    correlation_id = uuid4()

    content = b"concurrent-real-ai-evidence-payload"

    try:
        # This setup uses an independent transaction
        # and commits the DetectionEvent + Incident so
        # both concurrent request sessions can see them.
        async with session_factory() as setup_session:
            detection = await seed_detection_with_incident(setup_session)

        assert detection.incident_id is not None

        path = evidence_path(
            source_event_id=(detection.source_event_id),
            artifact_id=artifact_id,
        )

        headers = evidence_headers(
            content=content,
            correlation_id=correlation_id,
        )

        # Force both bridges to complete their initial
        # "does this artifact already exist?" query
        # before either proceeds to secure ingestion.
        #
        # This makes the test exercise the PostgreSQL
        # partial UNIQUE index race instead of allowing
        # request B to simply observe request A after
        # it has already committed.
        race_barrier = asyncio.Barrier(2)

        original_get_existing = AIDetectionEvidenceBridge._get_existing_artifact

        async def synchronized_get_existing(
            self: AIDetectionEvidenceBridge,
            requested_artifact_id: UUID,
        ) -> Evidence | None:
            existing = await original_get_existing(
                self,
                requested_artifact_id,
            )

            if requested_artifact_id == artifact_id and existing is None:
                await asyncio.wait_for(
                    race_barrier.wait(),
                    timeout=15.0,
                )

            return existing

        monkeypatch.setattr(
            AIDetectionEvidenceBridge,
            "_get_existing_artifact",
            synchronized_get_existing,
        )

        request_session_ids: set[int] = set()

        async def override_db_session() -> AsyncIterator[AsyncSession]:
            async with session_factory() as request_session:
                request_session_ids.add(id(request_session))

                yield request_session

        test_settings = create_settings()

        app.dependency_overrides[get_settings] = lambda: test_settings

        app.dependency_overrides[get_db_session] = override_db_session

        try:
            transport = httpx.ASGITransport(app=app)

            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://localhost",
            ) as client:
                first_response, second_response = await asyncio.gather(
                    client.post(
                        path,
                        content=content,
                        headers=headers,
                    ),
                    client.post(
                        path,
                        content=content,
                        headers=headers,
                    ),
                )

        finally:
            app.dependency_overrides.pop(
                get_settings,
                None,
            )

            app.dependency_overrides.pop(
                get_db_session,
                None,
            )

        # This assertion proves FastAPI supplied
        # two independent AsyncSession instances.
        assert len(request_session_ids) == 2

        responses = [
            first_response,
            second_response,
        ]

        assert sorted(response.status_code for response in responses) == [
            200,
            201,
        ]

        bodies = [response.json() for response in responses]

        assert sorted(body["duplicate"] for body in bodies) == [
            False,
            True,
        ]

        evidence_ids = {body["evidence_id"] for body in bodies}

        # Winner and loser must resolve to the
        # same persistent Evidence record.
        assert len(evidence_ids) == 1

        for body in bodies:
            assert body["source_event_id"] == str(detection.source_event_id)

            assert body["artifact_id"] == str(artifact_id)

        async with session_factory() as verification_session:
            statement = select(Evidence).where(Evidence.source_artifact_id == artifact_id)

            result = await verification_session.execute(statement)

            evidence_rows = list(result.scalars().all())

            # Final PostgreSQL authority:
            # only one row may survive.
            assert len(evidence_rows) == 1

            evidence = evidence_rows[0]

            assert evidence.source_detection_id == detection.id

            assert evidence.incident_id == detection.incident_id

            assert evidence.original_sha256 == hashlib.sha256(content).hexdigest()

            evidence_key_count = await verification_session.scalar(
                select(func.count())
                .select_from(EvidenceKey)
                .where(EvidenceKey.evidence_id == evidence.id)
            )

            custody_count = await verification_session.scalar(
                select(func.count())
                .select_from(CustodyRecord)
                .where(CustodyRecord.evidence_id == evidence.id)
            )

            audit_count = await verification_session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.resource_id == evidence.id,
                    AuditLog.action == (AuditAction.EVIDENCE_INGESTED.value),
                )
            )

            assert int(evidence_key_count or 0) == 1

            assert int(custody_count or 0) == 1

            assert int(audit_count or 0) == 1

            assert evidence.storage_version_id is not None

            storage_object_key = evidence.storage_object_key

            storage_version_id = evidence.storage_version_id

        storage = MinioEvidenceObjectStorage.from_settings(settings)

        await storage.ensure_ready()

        encrypted = await storage.get_object(
            object_key=storage_object_key,
            version_id=storage_version_id,
        )

        assert encrypted != content

        assert hashlib.sha256(encrypted).hexdigest() == evidence.encrypted_sha256

    finally:
        await test_engine.dispose()
