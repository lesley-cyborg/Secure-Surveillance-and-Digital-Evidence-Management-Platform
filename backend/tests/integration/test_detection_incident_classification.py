from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.core.config import get_settings
from app.db.models.enums import (
    CameraStatus,
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
)
from app.db.models.incidents import Incident
from app.db.models.surveillance import (
    AIModel,
    Camera,
    DetectionEvent,
    Site,
)
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)
from app.modules.ai_ingestion.service import (
    DetectionEventIngestionResult,
    DetectionEventIngestionService,
)
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


@dataclass(frozen=True, slots=True)
class IncidentTestReferences:
    site: Site
    camera: Camera
    ai_model: AIModel


async def seed_references(
    session: AsyncSession,
) -> IncidentTestReferences:
    unique = uuid4().hex[:12]

    site = Site(
        name=f"Incident Test Site {unique}",
        address="Integration test site",
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
        name=f"Incident Camera {unique}",
        camera_code=f"INC-CAM-{unique}",
        ip_address="10.20.30.40",
        protocol="RTSP",
        stream_url_encrypted=("encrypted://integration-test"),
        credentials_secret_ref=(f"secret://camera/{unique}"),
        status=CameraStatus.ONLINE,
        location_description=("Incident integration test location"),
        is_active=True,
        last_seen_at=datetime.now(UTC),
    )

    ai_model = AIModel(
        name=f"incident-test-model-{unique}",
        model_type="object_detection",
        version="1.0.0",
        framework="pytest",
        artifact_uri=(f"memory://incident-model/{unique}"),
        checksum_sha256="a" * 64,
        confidence_threshold=Decimal("0.5000"),
        is_active=True,
        deployed_at=datetime.now(UTC),
    )

    session.add_all(
        [
            camera,
            ai_model,
        ]
    )

    await session.flush()

    return IncidentTestReferences(
        site=site,
        camera=camera,
        ai_model=ai_model,
    )


async def create_second_camera(
    session: AsyncSession,
    *,
    site_id: UUID,
) -> Camera:
    unique = uuid4().hex[:12]

    camera = Camera(
        site_id=site_id,
        registered_by=None,
        name=f"Second Incident Camera {unique}",
        camera_code=f"INC-CAM-SECOND-{unique}",
        ip_address="10.20.30.41",
        protocol="RTSP",
        stream_url_encrypted=("encrypted://integration-test-second"),
        credentials_secret_ref=(f"secret://camera/{unique}"),
        status=CameraStatus.ONLINE,
        location_description=("Second incident integration camera"),
        is_active=True,
        last_seen_at=datetime.now(UTC),
    )

    session.add(camera)
    await session.flush()

    return camera


def create_event(
    references: IncidentTestReferences,
    *,
    label: str,
    confidence: float,
    captured_at: datetime,
    camera_code: str | None = None,
    sequence_number: int = 42,
) -> DetectionEventIngestionRequest:
    return DetectionEventIngestionRequest.model_validate(
        {
            "schema_version": "1.0",
            "event_type": ("camera.detection.completed"),
            "event_id": str(uuid4()),
            "camera_id": (camera_code or references.camera.camera_code),
            "frame": {
                "sequence_number": sequence_number,
                "captured_at": captured_at,
                "received_at": captured_at,
            },
            "model": {
                "name": references.ai_model.name,
                "version": (references.ai_model.version),
                "device": "cpu",
            },
            "detections": [
                {
                    "class_id": 1,
                    "label": label,
                    "confidence": confidence,
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
                "processed_at": captured_at,
            },
        }
    )


def create_zero_detection_event(
    references: IncidentTestReferences,
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
                "sequence_number": 43,
                "captured_at": captured_at,
                "received_at": captured_at,
            },
            "model": {
                "name": references.ai_model.name,
                "version": (references.ai_model.version),
                "device": "cpu",
            },
            "detections": [],
            "detection_count": 0,
            "inference": {
                "duration_ms": 4.0,
                "processed_at": captured_at,
            },
        }
    )


def idempotency_key(
    event: DetectionEventIngestionRequest,
) -> str:
    payload = event.model_dump_json().encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


async def load_detection(
    session: AsyncSession,
    *,
    source_event_id: UUID,
) -> DetectionEvent:
    statement = select(DetectionEvent).where(DetectionEvent.source_event_id == source_event_id)

    result = await session.execute(statement)

    detection = result.scalar_one_or_none()

    assert detection is not None

    return detection


async def load_incident(
    session: AsyncSession,
    *,
    incident_id: UUID,
) -> Incident:
    incident = await session.get(
        Incident,
        incident_id,
    )

    assert incident is not None

    return incident


async def count_incidents_for_camera(
    session: AsyncSession,
    *,
    camera_id: UUID,
) -> int:
    statement = (
        select(func.count()).select_from(Incident).where(Incident.primary_camera_id == camera_id)
    )

    result = await session.scalar(statement)

    return int(result or 0)


@pytest.mark.asyncio
async def test_qualifying_detection_creates_and_links_incident(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    captured_at = datetime.now(UTC)

    event = create_event(
        references,
        label="weapon",
        confidence=0.92,
        captured_at=captured_at,
    )

    service = DetectionEventIngestionService(db_session)

    result = await service.ingest(
        event=event,
        idempotency_key=idempotency_key(event),
    )

    assert result.duplicate is False
    assert result.incident_id is not None

    detection = await load_detection(
        db_session,
        source_event_id=event.event_id,
    )

    incident = await load_incident(
        db_session,
        incident_id=result.incident_id,
    )

    assert detection.incident_id == incident.id

    assert incident.primary_camera_id == references.camera.id
    assert incident.source_type is IncidentSourceType.AI
    assert incident.incident_type == "WEAPON_DETECTED"
    assert incident.severity is Severity.CRITICAL
    assert incident.priority is Priority.URGENT
    assert incident.status is IncidentStatus.NEW
    assert incident.created_by_user_id is None
    assert incident.detected_at == captured_at
    assert incident.incident_number.startswith("INC-")


@pytest.mark.asyncio
async def test_nonqualifying_detection_creates_no_incident(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    event = create_event(
        references,
        label="person",
        confidence=0.99,
        captured_at=datetime.now(UTC),
    )

    service = DetectionEventIngestionService(db_session)

    result = await service.ingest(
        event=event,
        idempotency_key=idempotency_key(event),
    )

    assert result.incident_id is None

    persisted = await load_detection(
        db_session,
        source_event_id=event.event_id,
    )

    assert persisted.incident_id is None

    count = await count_incidents_for_camera(
        db_session,
        camera_id=references.camera.id,
    )

    assert count == 0


@pytest.mark.asyncio
async def test_zero_detection_event_creates_no_incident(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    event = create_zero_detection_event(
        references,
        captured_at=datetime.now(UTC),
    )

    service = DetectionEventIngestionService(db_session)

    result = await service.ingest(
        event=event,
        idempotency_key=idempotency_key(event),
    )

    assert result.incident_id is None

    persisted = await load_detection(
        db_session,
        source_event_id=event.event_id,
    )

    assert persisted.incident_id is None


@pytest.mark.asyncio
async def test_recent_matching_incident_is_reused(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    first_time = datetime.now(UTC)

    first_event = create_event(
        references,
        label="fire",
        confidence=0.90,
        captured_at=first_time,
    )

    second_event = create_event(
        references,
        label="fire",
        confidence=0.95,
        captured_at=(first_time + timedelta(minutes=4)),
    )

    service = DetectionEventIngestionService(db_session)

    first = await service.ingest(
        event=first_event,
        idempotency_key=idempotency_key(first_event),
    )

    second = await service.ingest(
        event=second_event,
        idempotency_key=idempotency_key(second_event),
    )

    assert first.incident_id is not None
    assert second.incident_id is not None

    assert second.incident_id == first.incident_id

    count = await count_incidents_for_camera(
        db_session,
        camera_id=references.camera.id,
    )

    assert count == 1

    second_detection = await load_detection(
        db_session,
        source_event_id=second_event.event_id,
    )

    assert second_detection.incident_id == first.incident_id


@pytest.mark.asyncio
async def test_different_incident_type_is_not_reused(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    first_time = datetime.now(UTC)

    fire_event = create_event(
        references,
        label="fire",
        confidence=0.95,
        captured_at=first_time,
    )

    weapon_event = create_event(
        references,
        label="weapon",
        confidence=0.95,
        captured_at=(first_time + timedelta(minutes=1)),
    )

    service = DetectionEventIngestionService(db_session)

    fire_result = await service.ingest(
        event=fire_event,
        idempotency_key=idempotency_key(fire_event),
    )

    weapon_result = await service.ingest(
        event=weapon_event,
        idempotency_key=idempotency_key(weapon_event),
    )

    assert fire_result.incident_id is not None
    assert weapon_result.incident_id is not None

    assert fire_result.incident_id != weapon_result.incident_id

    count = await count_incidents_for_camera(
        db_session,
        camera_id=references.camera.id,
    )

    assert count == 2


@pytest.mark.asyncio
async def test_different_camera_is_not_reused(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    second_camera = await create_second_camera(
        db_session,
        site_id=references.site.id,
    )

    first_time = datetime.now(UTC)

    first_event = create_event(
        references,
        label="fire",
        confidence=0.95,
        captured_at=first_time,
    )

    second_event = create_event(
        references,
        label="fire",
        confidence=0.95,
        captured_at=(first_time + timedelta(minutes=1)),
        camera_code=(second_camera.camera_code),
    )

    service = DetectionEventIngestionService(db_session)

    first_result = await service.ingest(
        event=first_event,
        idempotency_key=idempotency_key(first_event),
    )

    second_result = await service.ingest(
        event=second_event,
        idempotency_key=idempotency_key(second_event),
    )

    assert first_result.incident_id is not None
    assert second_result.incident_id is not None

    assert first_result.incident_id != second_result.incident_id


@pytest.mark.asyncio
async def test_terminal_incident_is_not_reused(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    first_time = datetime.now(UTC)

    first_event = create_event(
        references,
        label="smoke",
        confidence=0.95,
        captured_at=first_time,
    )

    service = DetectionEventIngestionService(db_session)

    first_result = await service.ingest(
        event=first_event,
        idempotency_key=idempotency_key(first_event),
    )

    assert first_result.incident_id is not None

    original_incident = await load_incident(
        db_session,
        incident_id=(first_result.incident_id),
    )

    original_incident.status = IncidentStatus.CLOSED
    original_incident.closed_at = first_time + timedelta(seconds=30)

    await db_session.commit()

    second_event = create_event(
        references,
        label="smoke",
        confidence=0.96,
        captured_at=(first_time + timedelta(minutes=1)),
    )

    second_result = await service.ingest(
        event=second_event,
        idempotency_key=idempotency_key(second_event),
    )

    assert second_result.incident_id is not None

    assert second_result.incident_id != first_result.incident_id


@pytest.mark.asyncio
async def test_expired_deduplication_window_creates_new_incident(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    first_time = datetime.now(UTC)

    first_event = create_event(
        references,
        label="fire",
        confidence=0.91,
        captured_at=first_time,
    )

    second_event = create_event(
        references,
        label="fire",
        confidence=0.92,
        captured_at=(
            first_time
            + timedelta(
                minutes=5,
                seconds=1,
            )
        ),
    )

    service = DetectionEventIngestionService(db_session)

    first_result = await service.ingest(
        event=first_event,
        idempotency_key=idempotency_key(first_event),
    )

    second_result = await service.ingest(
        event=second_event,
        idempotency_key=idempotency_key(second_event),
    )

    assert first_result.incident_id is not None
    assert second_result.incident_id is not None

    assert first_result.incident_id != second_result.incident_id

    count = await count_incidents_for_camera(
        db_session,
        camera_id=references.camera.id,
    )

    assert count == 2


@pytest.mark.asyncio
async def test_exact_retry_preserves_incident_identity(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    event = create_event(
        references,
        label="weapon",
        confidence=0.93,
        captured_at=datetime.now(UTC),
    )

    key = idempotency_key(event)

    service = DetectionEventIngestionService(db_session)

    first = await service.ingest(
        event=event,
        idempotency_key=key,
    )

    retry = await service.ingest(
        event=event,
        idempotency_key=key,
    )

    assert first.duplicate is False
    assert retry.duplicate is True

    assert first.incident_id is not None

    assert retry.incident_id == first.incident_id

    assert retry.persisted_event_id == first.persisted_event_id

    count = await count_incidents_for_camera(
        db_session,
        camera_id=references.camera.id,
    )

    assert count == 1


@pytest.mark.asyncio
async def test_concurrent_same_camera_same_threat_creates_one_incident() -> None:
    settings = get_settings()

    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")

    engine = create_async_engine(
        settings.test_database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={
            "ssl": False,
            "timeout": 10.0,
        },
    )

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    worker_count = 5

    site_id: UUID | None = None
    camera_id: UUID | None = None
    ai_model_id: UUID | None = None

    events: list[DetectionEventIngestionRequest] = []

    try:
        # -------------------------------------------------
        # Seed committed reference data.
        #
        # This must be committed because the concurrent
        # workers below use independent connections.
        # -------------------------------------------------
        async with session_factory() as setup_session:
            references = await seed_references(setup_session)

            await setup_session.commit()

            site_id = references.site.id
            camera_id = references.camera.id
            ai_model_id = references.ai_model.id

        captured_at = datetime.now(UTC)

        events = [
            create_event(
                references,
                label="fire",
                confidence=0.95,
                captured_at=captured_at,
                sequence_number=1000 + index,
            )
            for index in range(worker_count)
        ]

        # -------------------------------------------------
        # Concurrency gate.
        #
        # Every worker establishes its own PostgreSQL
        # connection before any ingestion begins.
        # -------------------------------------------------
        start_event = asyncio.Event()
        all_ready = asyncio.Event()
        ready_lock = asyncio.Lock()

        ready_count = 0

        async def ingest_event(
            event: DetectionEventIngestionRequest,
        ) -> DetectionEventIngestionResult:
            nonlocal ready_count

            async with session_factory() as session:
                # Force this worker to acquire its own
                # physical PostgreSQL connection before
                # reaching the start barrier.
                await session.connection()

                async with ready_lock:
                    ready_count += 1

                    if ready_count == worker_count:
                        all_ready.set()

                await start_event.wait()

                service = DetectionEventIngestionService(session)

                return await service.ingest(
                    event=event,
                    idempotency_key=(idempotency_key(event)),
                )

        tasks = [
            asyncio.create_task(
                ingest_event(event),
                name=(f"incident-concurrency-{index}"),
            )
            for index, event in enumerate(
                events,
                start=1,
            )
        ]

        try:
            # Do not release any worker until all five
            # PostgreSQL connections are established.
            await asyncio.wait_for(
                all_ready.wait(),
                timeout=15.0,
            )

            start_event.set()

            results = await asyncio.wait_for(
                asyncio.gather(*tasks),
                timeout=45.0,
            )

        finally:
            # Prevent workers from remaining blocked when
            # setup or execution fails.
            start_event.set()

            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        # -------------------------------------------------
        # Every request was a distinct event.
        # None should have taken the idempotency duplicate
        # path.
        # -------------------------------------------------
        assert len(results) == worker_count

        assert all(result.duplicate is False for result in results)

        assert all(result.incident_id is not None for result in results)

        event_ids = [event.event_id for event in events]

        # -------------------------------------------------
        # Verify committed PostgreSQL state from another
        # independent connection.
        # -------------------------------------------------
        async with session_factory() as verification:
            persisted_events_result = await verification.scalars(
                select(DetectionEvent).where(DetectionEvent.source_event_id.in_(event_ids))
            )

            persisted_events = list(persisted_events_result.all())

            assert len(persisted_events) == worker_count

            # All five detection rows must be linked.
            assert all(event.incident_id is not None for event in persisted_events)

            linked_incident_ids = {
                event.incident_id for event in persisted_events if event.incident_id is not None
            }

            # This is the primary advisory-lock
            # correctness assertion.
            assert len(linked_incident_ids) == 1

            shared_incident_id = next(iter(linked_incident_ids))

            # Every service response must agree with the
            # persisted relationship.
            assert all(result.incident_id == shared_incident_id for result in results)

            incident_count = await verification.scalar(
                select(func.count(Incident.id)).where(
                    Incident.primary_camera_id == camera_id,
                    Incident.incident_type == "FIRE_DETECTED",
                    Incident.source_type == IncidentSourceType.AI,
                )
            )

            assert int(incident_count or 0) == 1

            incident = await verification.get(
                Incident,
                shared_incident_id,
            )

            assert incident is not None

            assert incident.primary_camera_id == camera_id
            assert incident.incident_type == "FIRE_DETECTED"
            assert incident.source_type is IncidentSourceType.AI
            assert incident.status is IncidentStatus.NEW
            assert incident.severity is Severity.CRITICAL
            assert incident.priority is Priority.URGENT

    finally:
        # -------------------------------------------------
        # Manual cleanup is necessary because this test
        # deliberately bypasses db_session and commits
        # several independent transactions.
        # -------------------------------------------------
        if site_id is not None and camera_id is not None and ai_model_id is not None:
            async with session_factory() as cleanup:
                source_event_ids = [event.event_id for event in events]

                if source_event_ids:
                    await cleanup.execute(
                        delete(DetectionEvent).where(
                            DetectionEvent.source_event_id.in_(source_event_ids)
                        )
                    )

                await cleanup.execute(
                    delete(Incident).where(Incident.primary_camera_id == camera_id)
                )

                await cleanup.execute(delete(AIModel).where(AIModel.id == ai_model_id))

                await cleanup.execute(delete(Camera).where(Camera.id == camera_id))

                await cleanup.execute(delete(Site).where(Site.id == site_id))

                await cleanup.commit()

        await engine.dispose()
