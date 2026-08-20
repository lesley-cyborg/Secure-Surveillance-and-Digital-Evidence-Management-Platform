from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
)
from app.db.models.evidence import Evidence
from app.db.models.surveillance import (
    DetectionEvent,
)
from app.modules.evidence.service import (
    EvidenceIngestionCommand,
    SecureEvidenceIngestionService,
)


class AIEvidenceBridgeError(Exception):
    """Base exception for AI-to-evidence integration."""


class AIDetectionEventNotFoundError(AIEvidenceBridgeError):
    """Referenced AI detection event was not found."""


class AIDetectionIncidentMissingError(AIEvidenceBridgeError):
    """Referenced detection is not linked to an incident."""


class AIEvidenceArtifactConflictError(AIEvidenceBridgeError):
    """Artifact ID was reused for different evidence."""


@dataclass(
    frozen=True,
    slots=True,
)
class AIEvidenceArtifactCommand:
    source_event_id: UUID
    artifact_id: UUID

    evidence_type: EvidenceType

    original_filename: str
    mime_type: str

    content: bytes = field(repr=False)

    correlation_id: str

    source_ip: str | None = None
    user_agent: str | None = None
    device_identifier: str | None = None

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("AI evidence content must not be empty")

        if not self.original_filename.strip():
            raise ValueError("original_filename must not be empty")

        if not self.mime_type.strip():
            raise ValueError("mime_type must not be empty")

        if not self.correlation_id.strip():
            raise ValueError("correlation_id must not be empty")


@dataclass(
    frozen=True,
    slots=True,
)
class AIEvidenceArtifactResult:
    evidence_id: UUID
    evidence_number: str

    source_event_id: UUID
    artifact_id: UUID

    duplicate: bool


@dataclass(
    frozen=True,
    slots=True,
)
class ResolvedDetectionReference:
    """
    Primitive snapshot of a DetectionEvent.

    Keeping this separate from the ORM instance prevents
    post-rollback attribute access from triggering async
    lazy-loading.
    """

    detection_id: UUID
    incident_id: UUID
    detected_at: datetime


class AIDetectionEvidenceBridge:
    """Bridge an AI detection artifact into forensic evidence."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        ingestion: SecureEvidenceIngestionService,
    ) -> None:
        self.session = session
        self.ingestion = ingestion

    async def ingest(
        self,
        *,
        command: AIEvidenceArtifactCommand,
    ) -> AIEvidenceArtifactResult:
        detection = await self._get_detection(command.source_event_id)

        if detection is None:
            raise AIDetectionEventNotFoundError("Referenced AI detection event does not exist")

        if detection.incident_id is None:
            raise AIDetectionIncidentMissingError("Referenced AI detection has no linked incident")

        # Snapshot all DetectionEvent values that will
        # be needed after secure ingestion starts.
        #
        # Secure ingestion may roll the session back
        # when a concurrent request loses the artifact
        # uniqueness race. SQLAlchemy expires ORM
        # instances on rollback, so the recovery path
        # must not read attributes from `detection`.
        detection_reference = ResolvedDetectionReference(
            detection_id=detection.id,
            incident_id=detection.incident_id,
            detected_at=detection.detected_at,
        )

        content_sha256 = hashlib.sha256(command.content).hexdigest()

        existing = await self._get_existing_artifact(command.artifact_id)

        if existing is not None:
            self._validate_existing(
                existing=existing,
                detection=(detection_reference),
                command=command,
                content_sha256=content_sha256,
            )

            return self._duplicate_result(
                existing=existing,
                command=command,
            )

        ingestion_command = EvidenceIngestionCommand(
            incident_id=(detection_reference.incident_id),
            source_detection_id=(detection_reference.detection_id),
            submitted_by_user_id=None,
            source_type=(EvidenceSourceType.AI_CAPTURE),
            evidence_type=(command.evidence_type),
            original_filename=(command.original_filename),
            mime_type=command.mime_type,
            captured_at=(detection_reference.detected_at),
            content=command.content,
            correlation_id=(command.correlation_id),
            source_artifact_id=(command.artifact_id),
            source_ip=command.source_ip,
            user_agent=(command.user_agent),
            device_identifier=(command.device_identifier),
        )

        try:
            result = await self.ingestion.ingest(command=ingestion_command)

        except IntegrityError:
            # SecureEvidenceIngestionService has
            # rolled back its failed transaction.
            #
            # Do not access the original DetectionEvent
            # ORM object here. It may now be expired.
            existing = await self._get_existing_artifact(command.artifact_id)

            if existing is None:
                raise

            self._validate_existing(
                existing=existing,
                detection=(detection_reference),
                command=command,
                content_sha256=content_sha256,
            )

            return self._duplicate_result(
                existing=existing,
                command=command,
            )

        return AIEvidenceArtifactResult(
            evidence_id=result.evidence_id,
            evidence_number=(result.evidence_number),
            source_event_id=(command.source_event_id),
            artifact_id=command.artifact_id,
            duplicate=False,
        )

    async def _get_detection(
        self,
        source_event_id: UUID,
    ) -> DetectionEvent | None:
        statement = select(DetectionEvent).where(DetectionEvent.source_event_id == source_event_id)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def _get_existing_artifact(
        self,
        artifact_id: UUID,
    ) -> Evidence | None:
        statement = select(Evidence).where(Evidence.source_artifact_id == artifact_id)

        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    @staticmethod
    def _duplicate_result(
        *,
        existing: Evidence,
        command: AIEvidenceArtifactCommand,
    ) -> AIEvidenceArtifactResult:
        return AIEvidenceArtifactResult(
            evidence_id=existing.id,
            evidence_number=(existing.evidence_number),
            source_event_id=(command.source_event_id),
            artifact_id=(command.artifact_id),
            duplicate=True,
        )

    @staticmethod
    def _validate_existing(
        *,
        existing: Evidence,
        detection: ResolvedDetectionReference,
        command: AIEvidenceArtifactCommand,
        content_sha256: str,
    ) -> None:
        matches = (
            existing.source_artifact_id == command.artifact_id
            and existing.source_detection_id == detection.detection_id
            and existing.incident_id == detection.incident_id
            and existing.source_type is EvidenceSourceType.AI_CAPTURE
            and existing.evidence_type is command.evidence_type
            and existing.original_filename == command.original_filename
            and existing.mime_type == command.mime_type
            and hmac.compare_digest(
                existing.original_sha256,
                content_sha256,
            )
        )

        if not matches:
            raise AIEvidenceArtifactConflictError(
                "AI artifact ID was already used for different evidence"
            )
