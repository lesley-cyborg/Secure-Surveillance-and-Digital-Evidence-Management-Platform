from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from app.db.models.enums import CameraStatus

ALLOWED_PROTOCOLS = frozenset({"RTSP", "ONVIF", "HTTPS"})


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
        extra="forbid",
    )


class CameraCreateRequest(APIModel):
    site_id: UUID
    name: str = Field(min_length=1, max_length=160)
    camera_code: str = Field(min_length=1, max_length=64)
    ip_address: str = Field(min_length=1, max_length=64)
    protocol: str = Field(default="RTSP", min_length=1, max_length=16)
    stream_url: str = Field(min_length=1, max_length=2048)
    credentials_secret_ref: str = Field(
        default="local://unset",
        min_length=1,
        max_length=512,
    )
    location_description: str | None = Field(default=None, max_length=255)
    status: CameraStatus = CameraStatus.OFFLINE
    is_active: bool = True

    @field_validator("camera_code", "name", "stream_url")
    @classmethod
    def strip_required(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be empty")
        return cleaned

    @field_validator("protocol")
    @classmethod
    def protocol_ok(cls, value: str) -> str:
        p = value.strip().upper()
        if p not in ALLOWED_PROTOCOLS:
            raise ValueError(
                f"protocol must be one of {sorted(ALLOWED_PROTOCOLS)}"
            )
        return p

    @field_validator("credentials_secret_ref")
    @classmethod
    def validate_secret_ref(cls, value: str) -> str:
        cleaned = value.strip()
        allowed = ("local://", "env://", "vault://")
        if not cleaned.startswith(allowed):
            raise ValueError(
                "credentials_secret_ref must start with local://, env://, or vault://"
            )
        return cleaned

    @field_validator("location_description")
    @classmethod
    def strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("ip_address")
    @classmethod
    def strip_ip(cls, value: str) -> str:
        return value.strip()


class CameraResponse(APIModel):
    id: UUID
    site_id: UUID
    name: str
    camera_code: str
    ip_address: str
    protocol: str
    status: CameraStatus
    location_description: str | None
    is_active: bool
    last_seen_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("ip_address", mode="before")
    @classmethod
    def ip_to_str(cls, v: object) -> str:
        return str(v)


class CameraListResponse(APIModel):
    items: list[CameraResponse]
    total: int
    
    
class CameraTestResponse(APIModel):
    camera_id: UUID
    reachable: bool
    latency_ms: float | None = None
    message: str
    checked_status: CameraStatus | None = None


class CameraHeartbeatRequest(APIModel):
    status: CameraStatus
    last_seen_at: datetime | None = None
    detail: str | None = Field(default=None, max_length=512)


class CameraHeartbeatResponse(APIModel):
    camera_id: UUID
    status: CameraStatus
    last_seen_at: datetime | None    
    
    
    
    
    
    
    