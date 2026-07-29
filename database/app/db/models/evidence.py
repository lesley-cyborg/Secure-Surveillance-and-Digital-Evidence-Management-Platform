from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, BigInteger, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import (
    CustodyEventType,
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
    TransferStatus,
    VerificationStatus,
)
from app.db.models.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin


class Evidence(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_incident_status", "incident_id", "status"),
        Index("ix_evidence_captured_at", "captured_at"),
        Index("ix_evidence_submitted_by", "submitted_by_user_id"),
    )

    evidence_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    incident_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("incidents.id", ondelete="RESTRICT"), nullable=False)
    source_detection_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("detection_events.id", ondelete="SET NULL"))
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    source_type: Mapped[EvidenceSourceType] = mapped_column(Enum(EvidenceSourceType, name="evidence_source_type"), nullable=False)
    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType, name="evidence_type"), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_object_key: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    storage_version_id: Mapped[str | None] = mapped_column(String(255))
    original_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    digital_signature: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[EvidenceStatus] = mapped_column(Enum(EvidenceStatus, name="evidence_status"), nullable=False, default=EvidenceStatus.PENDING)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    incident: Mapped[object] = relationship("Incident", back_populates="evidence_items")
    keys: Mapped[list[EvidenceKey]] = relationship(back_populates="evidence")
    verifications: Mapped[list[EvidenceVerification]] = relationship(back_populates="evidence")
    custody_records: Mapped[list[CustodyRecord]] = relationship(
        back_populates="evidence",
        foreign_keys="CustodyRecord.evidence_id",
        order_by="CustodyRecord.occurred_at",
    )
    transfers: Mapped[list[EvidenceTransfer]] = relationship(back_populates="evidence")


class EvidenceKey(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_keys"
    __table_args__ = (
        UniqueConstraint("evidence_id", "key_version", name="uq_evidence_keys_evidence_version"),
        Index(
            "uq_evidence_keys_one_active",
            "evidence_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=False)
    algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    wrapped_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    evidence: Mapped[Evidence] = relationship(back_populates="keys")


class EvidenceVerification(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "evidence_verifications"
    __table_args__ = (Index("ix_evidence_verifications_evidence_verified", "evidence_id", "verified_at"),)

    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=False)
    verified_by_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_sha256: Mapped[str | None] = mapped_column(String(64))
    hash_matches: Mapped[bool] = mapped_column(Boolean, nullable=False)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(Enum(VerificationStatus, name="verification_status"), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence: Mapped[Evidence] = relationship(back_populates="verifications")


class EvidenceTransfer(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_transfers"
    __table_args__ = (
        Index("ix_evidence_transfers_evidence_status", "evidence_id", "status"),
        Index("ix_evidence_transfers_recipient_status", "to_user_id", "status"),
    )

    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=False)
    from_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    to_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    initiated_by_user_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TransferStatus] = mapped_column(Enum(TransferStatus, name="transfer_status"), nullable=False, default=TransferStatus.PENDING)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str | None] = mapped_column(Text)

    evidence: Mapped[Evidence] = relationship(back_populates="transfers")


class CustodyRecord(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "chain_of_custody"
    __table_args__ = (
        Index("ix_chain_of_custody_evidence_occurred", "evidence_id", "occurred_at"),
        Index("ix_chain_of_custody_actor_occurred", "actor_user_id", "occurred_at"),
        UniqueConstraint("record_hash", name="uq_chain_of_custody_record_hash"),
    )

    evidence_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence.id", ondelete="RESTRICT"), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    from_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    to_user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    previous_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("chain_of_custody.id", ondelete="RESTRICT"))
    transfer_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), ForeignKey("evidence_transfers.id", ondelete="SET NULL"))
    event_type: Mapped[CustodyEventType] = mapped_column(Enum(CustodyEventType, name="custody_event_type"), nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text)
    source_ip: Mapped[str | None] = mapped_column(INET)
    device_identifier: Mapped[str | None] = mapped_column(String(255))
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    record_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    digital_signature: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence: Mapped[Evidence] = relationship(back_populates="custody_records", foreign_keys=[evidence_id])
    previous_record: Mapped[CustodyRecord | None] = relationship(remote_side="CustodyRecord.id", foreign_keys=[previous_record_id])
