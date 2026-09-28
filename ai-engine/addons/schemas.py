from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AddonModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BoundingBox(AddonModel):
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_coordinates(self) -> BoundingBox:
        if self.x_max <= self.x_min or self.y_max <= self.y_min:
            raise ValueError("bounding box maxima must exceed minima")
        return self


class ThreatSignal(AddonModel):
    signal: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)
    source: str = Field(min_length=1, max_length=128)
    bounding_box: BoundingBox | None = None


class PlateCandidate(AddonModel):
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox


class PlateObservation(AddonModel):
    text: str = Field(min_length=1, max_length=32)
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox

    @field_validator("text")
    @classmethod
    def reject_placeholder_text(cls, value: str) -> str:
        text = value.strip()
        if not text or text.casefold() in {"pending", "unreadable"}:
            raise ValueError("plate text must be successfully recognized")
        return text


class PoseObservation(AddonModel):
    posture: str = Field(min_length=1, max_length=64)
    confidence: float = Field(ge=0, le=1)
    bounding_box: BoundingBox
    confirmed: bool = False


class AddonAnalysisResult(AddonModel):
    threat_signals: tuple[ThreatSignal, ...] = ()
    weapon_count: int = Field(default=0, ge=0)
    plates: tuple[PlateObservation, ...] = ()
    poses: tuple[PoseObservation, ...] = ()
    degraded_capabilities: tuple[str, ...] = ()
