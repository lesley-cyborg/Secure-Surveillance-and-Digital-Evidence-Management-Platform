from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field, model_validator
class AddonModel(BaseModel):
    model_config=ConfigDict(extra="forbid", frozen=True)
class BoundingBox(AddonModel):
    x_min: float=Field(ge=0,le=1); y_min: float=Field(ge=0,le=1); x_max: float=Field(ge=0,le=1); y_max: float=Field(ge=0,le=1)
    @model_validator(mode="after")
    def ordered(self)->"BoundingBox":
        if self.x_max<=self.x_min or self.y_max<=self.y_min: raise ValueError("bounding box maximums must exceed minimums")
        return self
class ThreatSignal(AddonModel):
    signal: str=Field(min_length=1,max_length=128); confidence: float=Field(ge=0,le=1); source: str=Field(min_length=1,max_length=128); bounding_box: BoundingBox|None=None
class PlateObservation(AddonModel):
    text: str=Field(min_length=1,max_length=32); confidence: float=Field(ge=0,le=1); bounding_box: BoundingBox
class PoseKeypoint(AddonModel):
    name: str=Field(min_length=1,max_length=64); x: float=Field(ge=0,le=1); y: float=Field(ge=0,le=1); confidence: float=Field(ge=0,le=1)
class PoseObservation(AddonModel):
    posture: str=Field(min_length=1,max_length=64); confidence: float=Field(ge=0,le=1); bounding_box: BoundingBox; keypoints: tuple[PoseKeypoint,...]=(); confirmed: bool=False
class AnalysisOutput(AddonModel):
    threat_signals: tuple[ThreatSignal,...]=(); weapon_count: int=Field(default=0,ge=0); plates: tuple[PlateObservation,...]=(); poses: tuple[PoseObservation,...]=(); degraded_capabilities: tuple[str,...]=()
