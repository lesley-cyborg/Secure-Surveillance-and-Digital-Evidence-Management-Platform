from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import CameraStatus
from app.db.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin, UpdatedAtMixin


class Site(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "sites"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Africa/Gaborone")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    cameras: Mapped[list[Camera]] = relationship(back_populates="site")


class Camera(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "cameras"
    __table_args__ = (
        Index("ix_cameras_site_status", "site_id", "status"),
        Index("ix_cameras_active_last_seen", "is_active", "last_seen_at"),
    )

    site_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("sites.id", ondelete="RESTRICT"), nullable=False)
    registered_by: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    camera_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    stream_url_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    credentials_secret_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[CameraStatus] = mapped_column(Enum(CameraStatus, name="camera_status"), nullable=False, default=CameraStatus.OFFLINE)
    location_description: Mapped[str | None] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    site: Mapped[Site] = relationship(back_populates="cameras")
    ai_configurations: Mapped[list[CameraAIConfig]] = relationship(back_populates="camera", cascade="all, delete-orphan")
    detections: Mapped[list[DetectionEvent]] = relationship(back_populates="camera")


class AIModel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_models"
    __table_args__ = (UniqueConstraint("name", "model_type", "version", name="uq_ai_models_identity"),)

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    model_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    framework: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera_configurations: Mapped[list[CameraAIConfig]] = relationship(back_populates="ai_model")
    detections: Mapped[list[DetectionEvent]] = relationship(back_populates="ai_model")


class CameraAIConfig(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "camera_ai_configs"
    __table_args__ = (UniqueConstraint("camera_id", "ai_model_id", name="uq_camera_ai_configs_camera_model"),)

    camera_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False)
    ai_model_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    confidence_threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    camera: Mapped[Camera] = relationship(back_populates="ai_configurations")
    ai_model: Mapped[AIModel] = relationship(back_populates="camera_configurations")


class DetectionEvent(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "detection_events"
    __table_args__ = (
        Index("ix_detection_events_camera_detected", "camera_id", "detected_at"),
        Index("ix_detection_events_incident", "incident_id"),
        Index("ix_detection_events_type_detected", "event_type", "detected_at"),
    )

    camera_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("cameras.id", ondelete="RESTRICT"), nullable=False)
    ai_model_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("ai_models.id", ondelete="RESTRICT"), nullable=False)
    incident_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"))
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    confidence_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    bounding_boxes: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")
    recognition_results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    ocr_results: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    contextual_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    camera: Mapped[Camera] = relationship(back_populates="detections")
    ai_model: Mapped[AIModel] = relationship(back_populates="detections")
    incident: Mapped[object | None] = relationship("Incident", back_populates="detection_events")
