from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
)
from app.db.models.evidence import Evidence


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    evidence_number: str = Field(alias="evidenceNumber")
    incident_id: UUID = Field(alias="incidentId")
    source_detection_id: UUID | None = Field(
        default=None,
        alias="sourceDetectionId",
    )
    submitted_by_user_id: UUID | None = Field(
        default=None,
        alias="submittedByUserId",
    )
    source_type: EvidenceSourceType = Field(alias="sourceType")
    evidence_type: EvidenceType = Field(alias="evidenceType")
    original_filename: str = Field(alias="originalFilename")
    mime_type: str = Field(alias="mimeType")
    file_size_bytes: int = Field(alias="fileSizeBytes")
    original_sha256: str = Field(alias="originalSha256")
    encrypted_sha256: str = Field(alias="encryptedSha256")
    status: EvidenceStatus
    captured_at: datetime = Field(alias="capturedAt")
    ingested_at: datetime = Field(alias="ingestedAt")
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_model(cls, row: Evidence) -> EvidenceResponse:
        return cls.model_validate(row)


class EvidenceListResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    items: list[EvidenceResponse]
    total: int