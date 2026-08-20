from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
)
from app.db.models.incidents import Incident
from app.db.models.surveillance import DetectionEvent


class IncidentRepository:
    """Persistence operations for AI-generated incidents.

    The repository may flush, but it never commits. Transaction
    boundaries belong to the calling service.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session

    async def acquire_classification_lock(
        self,
        *,
        camera_id: UUID,
        incident_type: str,
    ) -> None:
        """Serialize classification for one camera/type combination.

        PostgreSQL transaction-level advisory locking prevents two
        simultaneous qualifying detections from both observing that
        no reusable incident exists and creating duplicate incidents.
        """

        lock_key = f"incident-classification:{camera_id}:{incident_type}"

        await self.session.execute(
            text(
                """
                SELECT pg_advisory_xact_lock(
                    hashtextextended(:lock_key, 0)
                )
                """
            ),
            {
                "lock_key": lock_key,
            },
        )

    async def find_reusable_ai_incident(
        self,
        *,
        camera_id: UUID,
        incident_type: str,
        detected_after: datetime,
        reusable_statuses: frozenset[IncidentStatus],
    ) -> Incident | None:
        if not reusable_statuses:
            return None

        statement = (
            select(Incident)
            .where(
                Incident.primary_camera_id == camera_id,
                Incident.source_type == IncidentSourceType.AI,
                Incident.incident_type == incident_type,
                Incident.status.in_(tuple(reusable_statuses)),
                Incident.detected_at >= detected_after,
            )
            .order_by(
                Incident.detected_at.desc(),
                Incident.created_at.desc(),
                Incident.id.desc(),
            )
            .limit(1)
            .with_for_update()
        )

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def create_ai_incident(
        self,
        *,
        incident_number: str,
        camera_id: UUID,
        incident_type: str,
        severity: Severity,
        priority: Priority,
        title: str,
        description: str | None,
        detected_at: datetime,
    ) -> Incident:
        incident = Incident(
            incident_number=incident_number,
            primary_camera_id=camera_id,
            created_by_user_id=None,
            source_type=IncidentSourceType.AI,
            incident_type=incident_type,
            severity=severity,
            priority=priority,
            status=IncidentStatus.NEW,
            title=title,
            description=description,
            disposition=None,
            detected_at=detected_at,
            confirmed_at=None,
            closed_at=None,
        )

        self.session.add(incident)

        await self.session.flush()

        return incident

    async def link_detection_event(
        self,
        *,
        detection_event: DetectionEvent,
        incident: Incident,
    ) -> None:
        detection_event.incident_id = incident.id

        await self.session.flush()
