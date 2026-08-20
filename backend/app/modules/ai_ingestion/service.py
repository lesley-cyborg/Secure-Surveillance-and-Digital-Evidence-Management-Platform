from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.surveillance import (
    AIModel,
    Camera,
)
from app.modules.ai_ingestion.errors import (
    AIIngestionError,
    AIModelAmbiguousError,
    AIModelInactiveError,
    AIModelNotFoundError,
    CameraInactiveError,
    CameraNotFoundError,
    DetectionEventConflictError,
    DetectionEventPersistenceError,
)
from app.modules.ai_ingestion.repository import (
    DetectionEventRepository,
)
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)
from app.modules.incidents.service import (
    DetectionIncidentService,
)

_CONFIDENCE_PRECISION = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class DetectionEventIngestionResult:
    persisted_event_id: UUID
    source_event_id: UUID
    duplicate: bool
    incident_id: UUID | None = None


class DetectionEventIngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = DetectionEventRepository(session)
        self.incidents = DetectionIncidentService(session)

    async def ingest(
        self,
        *,
        event: DetectionEventIngestionRequest,
        idempotency_key: str,
    ) -> DetectionEventIngestionResult:
        normalized_key = idempotency_key.casefold()

        try:
            existing = await self._resolve_existing(
                source_event_id=event.event_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                return existing

            camera = await self._resolve_camera(event.camera_id)

            ai_model = await self._resolve_model(
                name=event.model.name,
                version=event.model.version,
            )

            # BOTH create() (which flushes) AND commit() must live
            # inside the try block. The flush() is what raises
            # IntegrityError on a unique-constraint race, not commit().
            persisted = await self.repository.create(
                source_event_id=event.event_id,
                idempotency_key=normalized_key,
                schema_version=event.schema_version,
                frame_sequence_number=(event.frame.sequence_number),
                camera_id=camera.id,
                ai_model_id=ai_model.id,
                event_type=event.event_type,
                confidence_score=(self._confidence_score(event)),
                bounding_boxes=(self._bounding_boxes(event)),
                contextual_metadata=(self._contextual_metadata(event)),
                detected_at=event.frame.captured_at,
                processed_at=(event.inference.processed_at),
            )

            classification = await self.incidents.classify_and_link(
                event=event,
                detection_event=persisted,
            )

            await self.session.commit()

            return DetectionEventIngestionResult(
                persisted_event_id=persisted.id,
                source_event_id=(persisted.source_event_id),
                duplicate=False,
                incident_id=classification.incident_id,
            )

        except IntegrityError as exception:
            await self.session.rollback()

            existing = await self._resolve_existing(
                source_event_id=event.event_id,
                idempotency_key=normalized_key,
            )
            if existing is not None:
                return existing

            raise DetectionEventPersistenceError() from exception

        except AIIngestionError:
            await self.session.rollback()
            raise

        except Exception:
            await self.session.rollback()
            raise

    async def _resolve_existing(
        self,
        *,
        source_event_id: UUID,
        idempotency_key: str,
    ) -> DetectionEventIngestionResult | None:
        by_source = await self.repository.get_by_source_event_id(source_event_id)
        by_key = await self.repository.get_by_idempotency_key(idempotency_key)

        if by_source is not None and by_source.idempotency_key != idempotency_key:
            raise DetectionEventConflictError(
                reason="source_event_id_reused_with_different_body",
            )

        if by_key is not None and by_key.source_event_id != source_event_id:
            raise DetectionEventConflictError(
                reason="idempotency_key_reused_for_different_event",
            )

        if by_source is not None and by_key is not None and by_source.id != by_key.id:
            raise DetectionEventConflictError(
                reason="event_identity_resolves_to_multiple_records",
            )

        existing = by_source or by_key
        if existing is None:
            return None

        return DetectionEventIngestionResult(
            persisted_event_id=existing.id,
            source_event_id=(existing.source_event_id),
            duplicate=True,
            incident_id=existing.incident_id,
        )

    async def _resolve_camera(self, camera_code: str) -> Camera:
        camera = await self.repository.get_camera_by_code(camera_code)
        if camera is None:
            raise CameraNotFoundError(camera_code)
        if not camera.is_active:
            raise CameraInactiveError(camera_code)
        return camera

    async def _resolve_model(
        self,
        *,
        name: str,
        version: str,
    ) -> AIModel:
        models = await self.repository.list_models_by_identity(
            name=name,
            version=version,
        )
        if not models:
            raise AIModelNotFoundError(name=name, version=version)
        if len(models) > 1:
            raise AIModelAmbiguousError(name=name, version=version)

        model = models[0]
        if not model.is_active:
            raise AIModelInactiveError(name=name, version=version)
        return model

    @staticmethod
    def _confidence_score(
        event: DetectionEventIngestionRequest,
    ) -> Decimal:
        if not event.detections:
            return Decimal("0").quantize(
                _CONFIDENCE_PRECISION,
                rounding=ROUND_HALF_UP,
            )
        maximum = max(d.confidence for d in event.detections)
        return Decimal(str(maximum)).quantize(
            _CONFIDENCE_PRECISION,
            rounding=ROUND_HALF_UP,
        )

    @staticmethod
    def _bounding_boxes(
        event: DetectionEventIngestionRequest,
    ) -> list[dict[str, object]]:
        return [d.model_dump(mode="json") for d in event.detections]

    @staticmethod
    def _contextual_metadata(
        event: DetectionEventIngestionRequest,
    ) -> dict[str, object]:
        return {
            "camera_code": event.camera_id,
            "detection_count": event.detection_count,
            "frame": event.frame.model_dump(mode="json"),
            "model": event.model.model_dump(mode="json"),
            "inference": event.inference.model_dump(mode="json"),
        }
