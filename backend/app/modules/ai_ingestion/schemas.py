from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class BoundingBoxPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    x_min: float = Field(ge=0, le=1)
    y_min: float = Field(ge=0, le=1)
    x_max: float = Field(ge=0, le=1)
    y_max: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_coordinates(
        self,
    ) -> BoundingBoxPayload:
        if self.x_max <= self.x_min:
            raise ValueError("x_max must be greater than x_min")

        if self.y_max <= self.y_min:
            raise ValueError("y_max must be greater than y_min")

        return self


class DetectionPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    class_id: int = Field(ge=0)
    label: str = Field(
        min_length=1,
        max_length=128,
    )
    confidence: float = Field(ge=0, le=1)

    bounding_box: BoundingBoxPayload


class FramePayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    sequence_number: int = Field(ge=0)

    captured_at: AwareDatetime
    received_at: AwareDatetime


class ModelPayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    name: str = Field(
        min_length=1,
        max_length=128,
    )
    version: str = Field(
        min_length=1,
        max_length=128,
    )
    device: str = Field(
        min_length=1,
        max_length=64,
    )


class InferencePayload(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    duration_ms: float = Field(ge=0)
    processed_at: AwareDatetime


class DetectionEventIngestionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    schema_version: Literal["1.0"]

    event_type: Literal["camera.detection.completed"]

    event_id: UUID

    camera_id: str = Field(
        min_length=1,
        max_length=128,
    )

    frame: FramePayload
    model: ModelPayload

    detections: tuple[
        DetectionPayload,
        ...,
    ] = ()

    detection_count: int = Field(ge=0)

    inference: InferencePayload

    @model_validator(mode="after")
    def validate_detection_count(
        self,
    ) -> DetectionEventIngestionRequest:
        if self.detection_count != len(self.detections):
            raise ValueError("detection_count does not match the detections collection")

        return self


class DetectionEventAcceptedResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
    )

    accepted: Literal[True] = True

    duplicate: bool = False

    event_id: UUID
    correlation_id: UUID
