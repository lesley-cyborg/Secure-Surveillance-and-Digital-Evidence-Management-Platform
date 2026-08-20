from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from app.core.config import get_settings
from app.db.models.surveillance import (
    AIModel,
    Camera,
    DetectionEvent,
    Site,
)
from app.modules.ai_ingestion.errors import (
    AIModelAmbiguousError,
    AIModelInactiveError,
    AIModelNotFoundError,
    CameraInactiveError,
    CameraNotFoundError,
    DetectionEventConflictError,
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
class SeededReferences:
    site: Site
    camera: Camera
    ai_model: AIModel


def unique_suffix() -> str:
    return uuid4().hex[:12]


async def seed_references(
    session: AsyncSession,
    *,
    camera_active: bool = True,
    model_active: bool = True,
    create_ambiguous_model: bool = False,
) -> SeededReferences:
    suffix = unique_suffix()

    site = Site(
        name=f"AI ingestion test site {suffix}",
        address="Integration test location",
        timezone="Africa/Gaborone",
        is_active=True,
    )

    session.add(site)
    await session.flush()

    camera = Camera(
        site_id=site.id,
        registered_by=None,
        name=f"Integration camera {suffix}",
        camera_code=f"CAM-{suffix.upper()}",
        ip_address="127.0.0.10",
        protocol="RTSP",
        stream_url_encrypted=("integration-test-encrypted-stream"),
        credentials_secret_ref=(f"test/cameras/{suffix}"),
        location_description=("PostgreSQL integration test"),
        is_active=camera_active,
    )

    model_name = f"surveillance-yolo-{suffix}"
    model_version = "1.0.0"

    ai_model = AIModel(
        name=model_name,
        model_type="detector",
        version=model_version,
        framework="ultralytics",
        artifact_uri=(f"models/{model_name}.pt"),
        checksum_sha256=hashlib.sha256(model_name.encode("utf-8")).hexdigest(),
        confidence_threshold=Decimal("0.3500"),
        is_active=model_active,
        deployed_at=datetime.now(UTC),
    )

    session.add_all(
        [
            camera,
            ai_model,
        ]
    )

    if create_ambiguous_model:
        ambiguous_model = AIModel(
            name=model_name,
            model_type="classifier",
            version=model_version,
            framework="pytorch",
            artifact_uri=(f"models/{model_name}-classifier.pt"),
            checksum_sha256=hashlib.sha256((f"{model_name}-classifier").encode()).hexdigest(),
            confidence_threshold=Decimal("0.5000"),
            is_active=True,
            deployed_at=datetime.now(UTC),
        )

        session.add(ambiguous_model)

    await session.commit()

    return SeededReferences(
        site=site,
        camera=camera,
        ai_model=ai_model,
    )


def create_event(
    references: SeededReferences,
    *,
    event_id: UUID | None = None,
    camera_code: str | None = None,
    model_name: str | None = None,
    model_version: str | None = None,
    include_detection: bool = True,
) -> DetectionEventIngestionRequest:
    captured_at = datetime(
        2026,
        8,
        3,
        20,
        30,
        0,
        tzinfo=UTC,
    )

    detections: list[dict[str, object]]

    if include_detection:
        detections = [
            {
                "class_id": 0,
                "label": "person",
                "confidence": 0.94,
                "bounding_box": {
                    "x_min": 0.1,
                    "y_min": 0.2,
                    "x_max": 0.8,
                    "y_max": 0.9,
                },
            }
        ]
    else:
        detections = []

    return DetectionEventIngestionRequest.model_validate(
        {
            "schema_version": "1.0",
            "event_type": ("camera.detection.completed"),
            "event_id": str(event_id or uuid4()),
            "camera_id": (camera_code or references.camera.camera_code),
            "frame": {
                "sequence_number": 42,
                "captured_at": captured_at,
                "received_at": captured_at,
            },
            "model": {
                "name": (model_name or references.ai_model.name),
                "version": (model_version or references.ai_model.version),
                "device": "cpu",
            },
            "detections": detections,
            "detection_count": len(detections),
            "inference": {
                "duration_ms": 8.5,
                "processed_at": captured_at,
            },
        }
    )


def create_idempotency_key(
    event_id: UUID,
    *,
    discriminator: str = "original",
) -> str:
    value = (f"{event_id}:{discriminator}").encode()

    return hashlib.sha256(value).hexdigest()


async def count_events(
    session: AsyncSession,
    *,
    source_event_id: UUID,
) -> int:
    count = await session.scalar(
        select(func.count(DetectionEvent.id)).where(
            DetectionEvent.source_event_id == source_event_id
        )
    )

    return int(count or 0)


async def load_event(
    session: AsyncSession,
    *,
    source_event_id: UUID,
) -> DetectionEvent:
    result = await session.scalar(
        select(DetectionEvent).where(DetectionEvent.source_event_id == source_event_id)
    )

    assert result is not None

    return result


async def test_new_event_is_persisted(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)
    event = create_event(references)
    key = create_idempotency_key(event.event_id)

    service = DetectionEventIngestionService(db_session)

    result = await service.ingest(
        event=event,
        idempotency_key=key,
    )

    persisted = await load_event(
        db_session,
        source_event_id=event.event_id,
    )

    assert result.duplicate is False
    assert result.persisted_event_id == persisted.id
    assert persisted.source_event_id == event.event_id
    assert persisted.idempotency_key == key
    assert persisted.schema_version == "1.0"
    assert persisted.frame_sequence_number == 42

    assert persisted.camera_id == references.camera.id
    assert persisted.ai_model_id == references.ai_model.id

    assert persisted.confidence_score == Decimal("0.9400")
    assert persisted.event_type == ("camera.detection.completed")

    assert persisted.bounding_boxes == [
        {
            "class_id": 0,
            "label": "person",
            "confidence": 0.94,
            "bounding_box": {
                "x_min": 0.1,
                "y_min": 0.2,
                "x_max": 0.8,
                "y_max": 0.9,
            },
        }
    ]

    metadata = persisted.contextual_metadata

    model_metadata = cast(
        dict[str, object],
        metadata["model"],
    )
    frame_metadata = cast(
        dict[str, object],
        metadata["frame"],
    )
    inference_metadata = cast(
        dict[str, object],
        metadata["inference"],
    )

    assert metadata["camera_code"] == references.camera.camera_code
    assert metadata["detection_count"] == 1
    assert model_metadata["name"] == references.ai_model.name
    assert frame_metadata["sequence_number"] == 42
    assert inference_metadata["duration_ms"] == 8.5


async def test_exact_retry_returns_duplicate(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)
    event = create_event(references)
    key = create_idempotency_key(event.event_id)

    service = DetectionEventIngestionService(db_session)

    first = await service.ingest(
        event=event,
        idempotency_key=key,
    )

    second = await service.ingest(
        event=event,
        idempotency_key=key,
    )

    assert first.duplicate is False
    assert second.duplicate is True
    assert first.persisted_event_id == second.persisted_event_id

    assert (
        await count_events(
            db_session,
            source_event_id=event.event_id,
        )
        == 1
    )


async def test_source_event_id_reuse_conflicts(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)
    event = create_event(references)

    service = DetectionEventIngestionService(db_session)

    original_key = create_idempotency_key(event.event_id)

    await service.ingest(
        event=event,
        idempotency_key=original_key,
    )

    conflicting_key = create_idempotency_key(
        event.event_id,
        discriminator="different-body",
    )

    with pytest.raises(DetectionEventConflictError) as captured:
        await service.ingest(
            event=event,
            idempotency_key=conflicting_key,
        )

    assert captured.value.status_code == 409
    assert captured.value.details["reason"] == ("source_event_id_reused_with_different_body")

    assert (
        await count_events(
            db_session,
            source_event_id=event.event_id,
        )
        == 1
    )


async def test_idempotency_key_reuse_conflicts(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    first_event = create_event(references)
    second_event = create_event(references)

    shared_key = create_idempotency_key(first_event.event_id)

    service = DetectionEventIngestionService(db_session)

    await service.ingest(
        event=first_event,
        idempotency_key=shared_key,
    )

    with pytest.raises(DetectionEventConflictError) as captured:
        await service.ingest(
            event=second_event,
            idempotency_key=shared_key,
        )

    assert captured.value.status_code == 409
    assert captured.value.details["reason"] == ("idempotency_key_reused_for_different_event")


async def test_unknown_camera_is_rejected(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    event = create_event(
        references,
        camera_code=(f"MISSING-{unique_suffix()}"),
    )

    service = DetectionEventIngestionService(db_session)

    with pytest.raises(CameraNotFoundError):
        await service.ingest(
            event=event,
            idempotency_key=(create_idempotency_key(event.event_id)),
        )


async def test_inactive_camera_is_rejected(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(
        db_session,
        camera_active=False,
    )
    event = create_event(references)

    service = DetectionEventIngestionService(db_session)

    with pytest.raises(CameraInactiveError):
        await service.ingest(
            event=event,
            idempotency_key=(create_idempotency_key(event.event_id)),
        )


async def test_unknown_model_is_rejected(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    event = create_event(
        references,
        model_name=(f"missing-model-{unique_suffix()}"),
    )

    service = DetectionEventIngestionService(db_session)

    with pytest.raises(AIModelNotFoundError):
        await service.ingest(
            event=event,
            idempotency_key=(create_idempotency_key(event.event_id)),
        )


async def test_inactive_model_is_rejected(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(
        db_session,
        model_active=False,
    )
    event = create_event(references)

    service = DetectionEventIngestionService(db_session)

    with pytest.raises(AIModelInactiveError):
        await service.ingest(
            event=event,
            idempotency_key=(create_idempotency_key(event.event_id)),
        )


async def test_ambiguous_model_is_rejected(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(
        db_session,
        create_ambiguous_model=True,
    )
    event = create_event(references)

    service = DetectionEventIngestionService(db_session)

    with pytest.raises(AIModelAmbiguousError):
        await service.ingest(
            event=event,
            idempotency_key=(create_idempotency_key(event.event_id)),
        )


async def test_zero_detection_event_stores_zero_confidence(
    db_session: AsyncSession,
) -> None:
    references = await seed_references(db_session)

    event = create_event(
        references,
        include_detection=False,
    )

    service = DetectionEventIngestionService(db_session)

    result = await service.ingest(
        event=event,
        idempotency_key=(create_idempotency_key(event.event_id)),
    )

    persisted = await load_event(
        db_session,
        source_event_id=event.event_id,
    )

    assert result.duplicate is False
    assert persisted.confidence_score == Decimal("0.0000")
    assert persisted.bounding_boxes == []
    assert persisted.contextual_metadata["detection_count"] == 0


async def cleanup_concurrent_test(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    source_event_id: UUID,
    camera_id: UUID,
    ai_model_id: UUID,
    site_id: UUID,
) -> None:
    async with session_factory() as session:
        await session.execute(
            delete(DetectionEvent).where(DetectionEvent.source_event_id == source_event_id)
        )

        await session.execute(delete(Camera).where(Camera.id == camera_id))

        await session.execute(delete(AIModel).where(AIModel.id == ai_model_id))

        await session.execute(delete(Site).where(Site.id == site_id))

        await session.commit()


async def test_concurrent_retries_create_one_row() -> None:
    settings = get_settings()

    if settings.test_database_url is None:
        pytest.skip("TEST_DATABASE_URL is required for integration tests")

    test_engine = create_async_engine(
        settings.test_database_url,
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

    async with session_factory() as setup_session:
        references = await seed_references(setup_session)

    event = create_event(references)
    key = create_idempotency_key(event.event_id)

    async def ingest_once() -> DetectionEventIngestionResult:
        async with session_factory() as session:
            service = DetectionEventIngestionService(session)

            return await service.ingest(
                event=event,
                idempotency_key=key,
            )

    try:
        results = await asyncio.gather(
            ingest_once(),
            ingest_once(),
        )

        duplicate_values = sorted(result.duplicate for result in results)

        assert duplicate_values == [
            False,
            True,
        ]

        assert results[0].persisted_event_id == results[1].persisted_event_id

        async with session_factory() as verification:
            assert (
                await count_events(
                    verification,
                    source_event_id=event.event_id,
                )
                == 1
            )

    finally:
        await cleanup_concurrent_test(
            session_factory,
            source_event_id=event.event_id,
            camera_id=references.camera.id,
            ai_model_id=references.ai_model.id,
            site_id=references.site.id,
        )

        await test_engine.dispose()
