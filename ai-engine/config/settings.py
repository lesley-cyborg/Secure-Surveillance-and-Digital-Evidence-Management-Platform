from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import hexdigits
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
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

    addon_enabled: bool =  True
    addon_event_v11_enabled: bool = True
    addon_threat_model_enabled: bool = True
    addon_threat_model_path: Path = Path("models/weapons.pt")
    addon_threat_model_sha256: str | None = None
    addon_plate_model_enabled: bool = True
    addon_plate_model_path: Path = Path("models/license-plate.pt")
    addon_plate_model_sha256: str | None = None
    addon_pose_model_enabled: bool = True
    addon_pose_model_path: Path = Path("models/pose.pt")
    addon_pose_model_sha256: str | None = None
    addon_plate_ocr_enabled: bool = True
    addon_pose_confirmation_frames: int = Field(default=3, ge=1, le=60)
    addon_pose_confirmation_expiry_seconds: float = Field(default=5.0, gt=0, le=300)
    addon_pose_confidence_threshold: float = Field(default=0.75, ge=0, le=1)
    addon_pose_minimum_iou: float = Field(default=0.3, ge=0, le=1)

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

    @field_validator(
        "model_sha256",
        "addon_threat_model_sha256",
        "addon_plate_model_sha256",
        "addon_pose_model_sha256",
    )
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

    @model_validator(mode="after")
    def require_checksum_for_production_model(self) -> Self:
        if self.production_model_enabled and self.model_sha256 is None:
            raise ValueError(
                "AI_MODEL_SHA256 is required when AI_PRODUCTION_MODEL_ENABLED is true"
            )

        if (
            self.addon_event_v11_enabled
            or self.addon_threat_model_enabled
            or self.addon_plate_model_enabled
            or self.addon_pose_model_enabled
        ) and not self.addon_enabled:
            raise ValueError(
                "AI_ADDON_ENABLED must be true when add-on models or "
                "v1.1 events are enabled"
            )

        enabled_models = (
            ("threat", self.addon_threat_model_enabled, self.addon_threat_model_sha256),
            ("plate", self.addon_plate_model_enabled, self.addon_plate_model_sha256),
            ("pose", self.addon_pose_model_enabled, self.addon_pose_model_sha256),
        )
        if any(enabled and digest is None for _, enabled, digest in enabled_models):
            missing = [
                capability
                for capability, enabled, digest in enabled_models
                if enabled and digest is None
            ]
            raise ValueError(
                "SHA-256 digests are required for enabled add-on models: "
                + ", ".join(missing)
            )

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
