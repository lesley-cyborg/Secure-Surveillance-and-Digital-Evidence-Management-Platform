from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import hexdigits
from typing import Literal

from pydantic import Field, SecretStr, field_validator
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

    backend_incident_sink_enabled: bool = False

    backend_incident_endpoint_url: str | None = None

    backend_service_token: SecretStr | None = Field(
        default=None,
        repr=False,
    )

    backend_incident_connect_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=300,
    )
    backend_incident_read_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=300,
    )
    backend_incident_write_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=300,
    )
    backend_incident_pool_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        le=300,
    )

    backend_incident_maximum_connections: int = Field(
        default=20,
        ge=1,
        le=1_000,
    )
    backend_incident_maximum_keepalive_connections: int = Field(
        default=10,
        ge=0,
        le=1_000,
    )

    backend_incident_verify_tls: bool = True
    backend_incident_allow_insecure_http: bool = False

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
    stream_jpeg_quality: int = Field(
        default=90,
        ge=1,
        le=100,
    )

    stream_reconnect_initial_delay_seconds: float = Field(
        default=1.0,
        gt=0,
        le=60,
    )
    stream_reconnect_multiplier: float = Field(
        default=2.0,
        ge=1,
        le=10,
    )
    stream_reconnect_maximum_delay_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
    )
    stream_reconnect_jitter_ratio: float = Field(
        default=0.2,
        ge=0,
        le=1,
    )
    stream_reconnect_maximum_attempts: int | None = Field(
        default=None,
        ge=0,
    )
    stream_event_queue_capacity: int = Field(
        default=1_000,
        ge=1,
        le=100_000,
    )
    stream_event_delivery_workers: int = Field(
        default=1,
        ge=1,
        le=32,
    )
    stream_event_delivery_timeout_seconds: float = Field(
        default=10.0,
        gt=0,
        le=300,
    )

    stream_event_retry_initial_delay_seconds: float = Field(
        default=0.5,
        gt=0,
        le=60,
    )
    stream_event_retry_multiplier: float = Field(
        default=2.0,
        ge=1,
        le=10,
    )
    stream_event_retry_maximum_delay_seconds: float = Field(
        default=30.0,
        gt=0,
        le=300,
    )
    stream_event_retry_maximum_attempts: int = Field(
        default=5,
        ge=1,
        le=100,
    )

    stream_event_shutdown_timeout_seconds: float = Field(
        default=15.0,
        gt=0,
        le=300,
    )

    stream_event_overflow_policy: Literal[
        "drop_oldest",
        "drop_newest",
    ] = "drop_oldest"

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
