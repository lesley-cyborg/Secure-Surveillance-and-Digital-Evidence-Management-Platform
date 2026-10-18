from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.surveillance import (
    AIModel,
    Camera,
    DetectionEvent,
)


class DetectionEventRepository:
    """
    Database operations for AI detection ingestion.

    Flushes changes but never commits. Transaction boundaries
    belong to the service.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
    
    async def get_camera_by_id(self, camera_id: UUID) -> Camera | None:
        statement = select(Camera).where(Camera.id == camera_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_camera_by_code(
        self,
        camera_code: str,
    ) -> Camera | None:
        statement = select(Camera).where(
            Camera.camera_code == camera_code,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_models_by_identity(
        self,
        *,
        name: str,
        version: str,
    ) -> list[AIModel]:
        statement = (
            select(AIModel)
            .where(
                AIModel.name == name,
                AIModel.version == version,
            )
            .order_by(AIModel.id)
        )
        result = await self.session.scalars(statement)
        return list(result.all())

    async def get_by_source_event_id(
        self,
        source_event_id: UUID,
    ) -> DetectionEvent | None:
        statement = select(DetectionEvent).where(
            DetectionEvent.source_event_id == source_event_id,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> DetectionEvent | None:
        statement = select(DetectionEvent).where(
            DetectionEvent.idempotency_key == idempotency_key,
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        source_event_id: UUID,
        idempotency_key: str,
        schema_version: str,
        frame_sequence_number: int,
        camera_id: UUID,
        ai_model_id: UUID,
        event_type: str,
        confidence_score: Decimal,
        bounding_boxes: list[dict[str, object]],
        contextual_metadata: dict[str, object],
        detected_at: datetime,
        processed_at: datetime,
    ) -> DetectionEvent:
        detection_event = DetectionEvent(
            source_event_id=source_event_id,
            idempotency_key=idempotency_key,
            schema_version=schema_version,
            frame_sequence_number=frame_sequence_number,
            camera_id=camera_id,
            ai_model_id=ai_model_id,
            incident_id=None,  # Phase 6.1C will link events to incidents
            event_type=event_type,
            confidence_score=confidence_score,
            bounding_boxes=bounding_boxes,
            recognition_results={},
            ocr_results={},
            contextual_metadata=contextual_metadata,
            detected_at=detected_at,
            processed_at=processed_at,
        )
        self.session.add(detection_event)
        await self.session.flush()
        return detection_event
