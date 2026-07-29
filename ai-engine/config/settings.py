from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import hexdigits

from pydantic import Field, field_validator
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
)

from detection.schemas import DeviceType


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AI_",
        case_sensitive=False,
        extra="ignore",
    )

    service_name: str = "secure-surveillance-ai-engine"
    service_version: str = "0.1.0"
    environment: str = "development"

    maximum_upload_bytes: int = Field(
        default=10 * 1024 * 1024,
        gt=0,
    )
    maximum_image_width: int = Field(
        default=7680,
        gt=0,
    )
    maximum_image_height: int = Field(
        default=4320,
        gt=0,
    )
    maximum_image_pixels: int = Field(
        default=33_177_600,
        gt=0,
    )
    upload_chunk_size: int = Field(
        default=64 * 1024,
        gt=0,
    )
    maximum_concurrent_inferences: int = Field(
        default=1,
        ge=1,
        le=16,
    )

    inference_queue_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        le=120,
    )

    production_model_enabled: bool = False

    model_path: Path = Path("models/yolo26n.pt")
    model_name: str = Field(
        default="surveillance-yolo",
        min_length=1,
        max_length=128,
    )
    model_version: str = Field(
        default="yolo26n-coco",
        min_length=1,
        max_length=64,
    )

    model_device: DeviceType = DeviceType.AUTO
    model_cuda_device_index: int = Field(
        default=0,
        ge=0,
    )

    model_image_size: int = Field(
        default=640,
        ge=32,
        le=4096,
    )
    model_backend_confidence_floor: float = Field(
        default=0.001,
        ge=0,
        le=1,
    )
    model_iou_threshold: float = Field(
        default=0.7,
        ge=0,
        le=1,
    )
    model_warmup_runs: int = Field(
        default=1,
        ge=0,
        le=10,
    )

    model_allowed_labels: tuple[str, ...] = (
        "person",
        "bicycle",
        "car",
        "motorcycle",
        "bus",
        "truck",
    )

    model_sha256: str | None = None

    @field_validator("model_sha256")
    @classmethod
    def validate_model_sha256(
        cls,
        value: str | None,
    ) -> str | None:
        if value is None:
            return None

        normalised = value.strip().casefold()

        if not normalised:
            return None

        if len(normalised) != 64 or any(
            character not in hexdigits for character in normalised
        ):
            raise ValueError("model_sha256 must be a 64-character hexadecimal digest")

        return normalised


@lru_cache
def get_settings() -> Settings:
    return Settings()
