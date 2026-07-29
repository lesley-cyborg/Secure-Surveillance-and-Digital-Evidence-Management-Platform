from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import AuditOutcome, NotificationChannel, NotificationStatus, ReportFormat, ReportStatus, ReportType
from app.db.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_occurred_at", "occurred_at"),
        Index("ix_audit_logs_actor_occurred", "actor_user_id", "occurred_at"),
        Index("ix_audit_logs_resource", "resource_type", "resource_id"),
        Index("ix_audit_logs_correlation", "correlation_id"),
    )

    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(96), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    outcome: Mapped[AuditOutcome] = mapped_column(Enum(AuditOutcome, name="audit_outcome"), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Notification(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_status", "recipient_user_id", "status"),
        Index("ix_notifications_incident", "incident_id"),
        Index("ix_notifications_evidence", "evidence_id"),
    )

    recipient_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    incident_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"))
    evidence_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="SET NULL"))
    channel: Mapped[NotificationChannel] = mapped_column(Enum(NotificationChannel, name="notification_channel"), nullable=False)
    notification_type: Mapped[str] = mapped_column(String(96), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(Enum(NotificationStatus, name="notification_status"), nullable=False, default=NotificationStatus.PENDING)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Report(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_generated_by_status", "generated_by_user_id", "status"),
        Index("ix_reports_generated_at", "generated_at"),
    )

    report_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    generated_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    report_type: Mapped[ReportType] = mapped_column(Enum(ReportType, name="report_type"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    storage_object_key: Mapped[str | None] = mapped_column(String(1024))
    file_format: Mapped[ReportFormat] = mapped_column(Enum(ReportFormat, name="report_format"), nullable=False)
    report_sha256: Mapped[str | None] = mapped_column(String(64))
    digital_signature: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ReportStatus] = mapped_column(Enum(ReportStatus, name="report_status"), nullable=False, default=ReportStatus.QUEUED)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    incident_links: Mapped[list[ReportIncident]] = relationship(back_populates="report", cascade="all, delete-orphan")
    exports: Mapped[list[ReportExport]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportIncident(Base):
    __tablename__ = "report_incidents"

    report_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), primary_key=True)
    incident_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), primary_key=True)

    report: Mapped[Report] = relationship(back_populates="incident_links")


class ReportExport(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "report_exports"
    __table_args__ = (
        Index("ix_report_exports_report_created", "report_id", "created_at"),
        Index("ix_report_exports_expires_at", "expires_at"),
    )

    report_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False)
    exported_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    export_format: Mapped[ReportFormat] = mapped_column(Enum(ReportFormat, name="report_format", create_type=False), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    watermark_reference: Mapped[str | None] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    report: Mapped[Report] = relationship(back_populates="exports")
