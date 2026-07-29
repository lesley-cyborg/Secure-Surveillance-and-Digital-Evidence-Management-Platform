from __future__ import annotations

from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
)

from streaming.domain import (
    CameraStreamConfig,
    StreamState,
    StreamTransport,
)


class CameraStreamRegistrationRequest(BaseModel):
    """Secure request for registering one RTSP stream."""

    model_config = ConfigDict(
        extra="forbid",
    )

    camera_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$",
    )
    name: str = Field(
        min_length=1,
        max_length=200,
    )

    source_uri: SecretStr

    enabled: bool = True
    transport: StreamTransport = StreamTransport.TCP

    target_fps: float = Field(
        default=5.0,
        gt=0,
        le=60,
    )
    confidence_threshold: float = Field(
        default=0.35,
        ge=0,
        le=1,
    )
    queue_capacity: int = Field(
        default=1,
        ge=1,
        le=32,
    )
    maximum_consecutive_read_failures: int = Field(
        default=3,
        ge=1,
        le=100,
    )

    @field_validator("source_uri")
    @classmethod
    def validate_source_uri(
        cls,
        value: SecretStr,
    ) -> SecretStr:
        raw_uri = value.get_secret_value()
        parsed = urlsplit(raw_uri)

        if parsed.scheme.lower() not in {"rtsp", "rtsps"} or not parsed.hostname:
            raise ValueError("source_uri must be a valid RTSP URI")

        return value

    def to_domain(
        self,
    ) -> CameraStreamConfig:
        return CameraStreamConfig(
            camera_id=self.camera_id,
            name=self.name,
            source_uri=(self.source_uri.get_secret_value()),
            enabled=self.enabled,
            transport=self.transport,
            target_fps=self.target_fps,
            confidence_threshold=(self.confidence_threshold),
            queue_capacity=self.queue_capacity,
            maximum_consecutive_read_failures=(self.maximum_consecutive_read_failures),
        )


class CameraStreamStatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    camera_id: str
    state: StreamState
    running: bool
    disposed: bool


class StreamManagerStatusResponse(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    closed: bool

    total_workers: int
    running_workers: int
    failed_workers: int
    disposed_workers: int

    workers: tuple[
        CameraStreamStatusResponse,
        ...,
    ]
