from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import (
    AssignmentRole,
    AssignmentStatus,
    IncidentSourceType,
    IncidentStatus,
    Priority,
    Severity,
)
from app.db.models.mixins import CreatedAtMixin, UpdatedAtMixin, UUIDPrimaryKeyMixin


class Incident(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_detected_at", "detected_at"),
        Index("ix_incidents_primary_camera", "primary_camera_id"),
    )

    incident_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    primary_camera_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cameras.id", ondelete="SET NULL")
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    source_type: Mapped[IncidentSourceType] = mapped_column(
        Enum(IncidentSourceType, name="incident_source_type"), nullable=False
    )
    incident_type: Mapped[str] = mapped_column(String(96), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity, name="severity"), nullable=False)
    priority: Mapped[Priority] = mapped_column(
        Enum(Priority, name="priority"), nullable=False, default=Priority.NORMAL
    )
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status"), nullable=False, default=IncidentStatus.NEW
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    disposition: Mapped[str | None] = mapped_column(String(64))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    detection_events: Mapped[list[object]] = relationship(
        "DetectionEvent", back_populates="incident"
    )
    assignments: Mapped[list[IncidentAssignment]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    notes: Mapped[list[IncidentNote]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list[object]] = relationship("Evidence", back_populates="incident")


class IncidentAssignment(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "incident_assignments"
    __table_args__ = (
        Index("ix_incident_assignments_incident_status", "incident_id", "status"),
        Index("ix_incident_assignments_user_status", "assigned_user_id", "status"),
    )

    incident_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    assigned_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    assignment_role: Mapped[AssignmentRole] = mapped_column(
        Enum(AssignmentRole, name="assignment_role"), nullable=False
    )
    status: Mapped[AssignmentStatus] = mapped_column(
        Enum(AssignmentStatus, name="assignment_status"),
        nullable=False,
        default=AssignmentStatus.ACTIVE,
    )
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    incident: Mapped[Incident] = relationship(back_populates="assignments")


class IncidentNote(UUIDPrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "incident_notes"
    __table_args__ = (Index("ix_incident_notes_incident_created", "incident_id", "created_at"),)

    incident_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False
    )
    author_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    incident: Mapped[Incident] = relationship(back_populates="notes")
