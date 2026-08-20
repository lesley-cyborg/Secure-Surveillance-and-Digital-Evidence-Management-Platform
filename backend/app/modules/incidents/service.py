from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    Priority,
    Severity,
)
from app.db.models.incidents import Incident
from app.db.models.surveillance import DetectionEvent
from app.modules.ai_ingestion.schemas import (
    DetectionEventIngestionRequest,
)
from app.modules.incidents.classification import (
    IncidentClassificationDecision,
    IncidentClassificationPolicy,
)
from app.modules.incidents.identifiers import (
    generate_incident_number,
)
from app.modules.incidents.repository import (
    IncidentRepository,
)


@dataclass(
    frozen=True,
    slots=True,
)
class DetectionIncidentResult:
    incident_id: UUID | None
    incident_created: bool
    incident_reused: bool
    decision: IncidentClassificationDecision


class DetectionIncidentService:
    """Classify a persisted AI event and attach an incident when needed."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        policy: IncidentClassificationPolicy | None = None,
    ) -> None:
        self.session = session
        self.repository = IncidentRepository(session)
        self.policy = policy or IncidentClassificationPolicy()

    async def classify_and_link(
        self,
        *,
        event: DetectionEventIngestionRequest,
        detection_event: DetectionEvent,
    ) -> DetectionIncidentResult:
        decision = self.policy.classify(event)

        if not decision.should_create_incident:
            return DetectionIncidentResult(
                incident_id=None,
                incident_created=False,
                incident_reused=False,
                decision=decision,
            )

        (
            incident_type,
            severity,
            priority,
            title,
        ) = self._require_incident_fields(decision)

        await self.repository.acquire_classification_lock(
            camera_id=detection_event.camera_id,
            incident_type=incident_type,
        )

        detected_after = detection_event.detected_at - decision.deduplication_window

        incident = await self.repository.find_reusable_ai_incident(
            camera_id=(detection_event.camera_id),
            incident_type=incident_type,
            detected_after=detected_after,
            reusable_statuses=(decision.reusable_statuses),
        )

        created = False

        if incident is None:
            incident = await self._create_incident(
                detection_event=(detection_event),
                decision=decision,
                incident_type=incident_type,
                severity=severity,
                priority=priority,
                title=title,
            )

            created = True

        await self.repository.link_detection_event(
            detection_event=detection_event,
            incident=incident,
        )

        return DetectionIncidentResult(
            incident_id=incident.id,
            incident_created=created,
            incident_reused=not created,
            decision=decision,
        )

    async def _create_incident(
        self,
        *,
        detection_event: DetectionEvent,
        decision: IncidentClassificationDecision,
        incident_type: str,
        severity: Severity,
        priority: Priority,
        title: str,
    ) -> Incident:
        return await self.repository.create_ai_incident(
            incident_number=(generate_incident_number(detected_at=(detection_event.detected_at))),
            camera_id=(detection_event.camera_id),
            incident_type=incident_type,
            severity=severity,
            priority=priority,
            title=title,
            description=(decision.description),
            detected_at=(detection_event.detected_at),
        )

    @staticmethod
    def _require_incident_fields(
        decision: IncidentClassificationDecision,
    ) -> tuple[
        str,
        Severity,
        Priority,
        str,
    ]:
        if (
            decision.incident_type is None
            or decision.severity is None
            or decision.priority is None
            or decision.title is None
        ):
            raise RuntimeError("Incident classification decision is incomplete")

        return (
            decision.incident_type,
            decision.severity,
            decision.priority,
            decision.title,
        )
