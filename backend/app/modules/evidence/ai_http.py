from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.db.models.enums import EvidenceType


class AIArtifactKind(StrEnum):
    KEY_FRAME = "key-frame"
    EVENT_CLIP = "event-clip"


@dataclass(
    frozen=True,
    slots=True,
)
class AIArtifactContract:
    evidence_type: EvidenceType
    mime_type: str
    extension: str


_ARTIFACT_CONTRACTS = {
    AIArtifactKind.KEY_FRAME: (
        AIArtifactContract(
            evidence_type=EvidenceType.IMAGE,
            mime_type="image/jpeg",
            extension=".jpg",
        )
    ),
    AIArtifactKind.EVENT_CLIP: (
        AIArtifactContract(
            evidence_type=EvidenceType.VIDEO,
            mime_type="video/mp4",
            extension=".mp4",
        )
    ),
}


def get_ai_artifact_contract(
    kind: AIArtifactKind,
) -> AIArtifactContract:
    return _ARTIFACT_CONTRACTS[kind]


def build_ai_artifact_filename(
    *,
    artifact_id: UUID,
    contract: AIArtifactContract,
) -> str:
    return f"ai-{artifact_id}{contract.extension}"


class AIEvidenceIngestionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    evidence_number: str

    source_event_id: UUID
    artifact_id: UUID

    duplicate: bool
    correlation_id: UUID
