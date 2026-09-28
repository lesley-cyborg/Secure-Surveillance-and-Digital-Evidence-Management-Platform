from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from addons.schemas import PlateObservation, PoseObservation, ThreatSignal
from detection.schemas import NormalisedBoundingBox

__all__ = [
    "OCRText",
    "PlateObservation",
    "PoseObservation",
    "ThreatSignal",
    "VisionAnalysisResult",
    "VisionModel",
]

class VisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)


class OCRText(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=4096)
    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalisedBoundingBox | None = None


class FaceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalisedBoundingBox


class VisionAnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ocr: tuple[OCRText, ...] = ()
    faces: tuple[FaceObservation, ...] = ()
    threat_signals: tuple[ThreatSignal, ...] = ()
    ocr_model: VisionModel | None = None
    face_model: VisionModel | None = None
    plates: tuple[PlateObservation, ...] = ()
    poses: tuple[PoseObservation, ...] = ()
    weapon_count: int = Field(default=0, ge=0)
    degraded_capabilities: tuple[str, ...] = ()
