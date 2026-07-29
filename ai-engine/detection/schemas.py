from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from detection.exceptions import (
    InvalidBoundingBoxError,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        frozen=True,
    )


class DeviceType(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"


class MediaType(StrEnum):
    JPEG = "image/jpeg"
    PNG = "image/png"


class PixelBoundingBox(ApiModel):
    x_min: float = Field(ge=0)
    y_min: float = Field(ge=0)
    x_max: float = Field(gt=0)
    y_max: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_order(
        self,
    ) -> PixelBoundingBox:
        if self.x_max <= self.x_min:
            raise ValueError("x_max must be greater than x_min")

        if self.y_max <= self.y_min:
            raise ValueError("y_max must be greater than y_min")

        return self

    def normalise(
        self,
        *,
        frame_width: int,
        frame_height: int,
    ) -> NormalisedBoundingBox:
        if frame_width <= 0 or frame_height <= 0:
            raise InvalidBoundingBoxError("Frame dimensions must be positive")

        if self.x_max > frame_width or self.y_max > frame_height:
            raise InvalidBoundingBoxError("Bounding box exceeds frame boundaries")

        return NormalisedBoundingBox(
            x_min=self.x_min / frame_width,
            y_min=self.y_min / frame_height,
            x_max=self.x_max / frame_width,
            y_max=self.y_max / frame_height,
        )


class NormalisedBoundingBox(ApiModel):
    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_order(
        self,
    ) -> NormalisedBoundingBox:
        if self.x_max <= self.x_min:
            raise ValueError("x_max must be greater than x_min")

        if self.y_max <= self.y_min:
            raise ValueError("y_max must be greater than y_min")

        return self


class RawDetection(ApiModel):
    class_id: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)
    bounding_box: PixelBoundingBox

    @field_validator("label")
    @classmethod
    def normalise_label(
        cls,
        value: str,
    ) -> str:
        return value.strip()


class Detection(ApiModel):
    class_id: int = Field(ge=0)
    label: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalisedBoundingBox


class ModelIdentity(ApiModel):
    name: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    device: DeviceType
    labels: tuple[str, ...] = ()


class ModelStatus(ApiModel):
    model: ModelIdentity
    is_ready: bool
    is_default: bool


class FrameMetadata(ApiModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    channels: int = Field(gt=0, le=4)
    media_type: MediaType
    byte_size: int = Field(gt=0)


class DetectionRequest(ApiModel):
    model_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    model_version: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
    )
    confidence_threshold: float = Field(
        default=0.5,
        ge=0,
        le=1,
    )


class DetectionResult(ApiModel):
    correlation_id: UUID
    model: ModelIdentity
    frame: FrameMetadata
    detections: tuple[Detection, ...]
    inference_duration_ms: float = Field(ge=0)
    processed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC).replace(microsecond=0)
    )
