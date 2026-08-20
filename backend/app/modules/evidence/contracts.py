from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceStatus,
    EvidenceType,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _require_non_empty(
    *,
    field_name: str,
    value: str,
) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_sha256(
    *,
    field_name: str,
    value: str,
) -> None:
    if not _SHA256_PATTERN.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase 64-character SHA-256 hex digest")


def _require_timezone_aware(
    *,
    field_name: str,
    value: datetime,
) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(
    frozen=True,
    slots=True,
)
class PreparedEvidenceRecord:
    """Forensic artifact ready for database persistence.

    Hashing, encryption, signing and object-storage preparation
    occur before this contract is constructed.
    """

    evidence_number: str

    incident_id: UUID
    source_detection_id: UUID | None
    submitted_by_user_id: UUID | None

    source_type: EvidenceSourceType
    evidence_type: EvidenceType

    original_filename: str
    mime_type: str
    file_size_bytes: int

    storage_bucket: str
    storage_object_key: str
    storage_version_id: str | None

    original_sha256: str
    encrypted_sha256: str
    manifest_sha256: str

    digital_signature: str
    status: EvidenceStatus

    captured_at: datetime
    ingested_at: datetime

    source_artifact_id: UUID | None = None

    def __post_init__(self) -> None:
        _require_non_empty(
            field_name="evidence_number",
            value=self.evidence_number,
        )
        _require_non_empty(
            field_name="original_filename",
            value=self.original_filename,
        )
        _require_non_empty(
            field_name="mime_type",
            value=self.mime_type,
        )
        _require_non_empty(
            field_name="storage_bucket",
            value=self.storage_bucket,
        )
        _require_non_empty(
            field_name="storage_object_key",
            value=self.storage_object_key,
        )
        _require_non_empty(
            field_name="digital_signature",
            value=self.digital_signature,
        )

        if self.file_size_bytes <= 0:
            raise ValueError("file_size_bytes must be greater than zero")

        _require_sha256(
            field_name="original_sha256",
            value=self.original_sha256,
        )
        _require_sha256(
            field_name="encrypted_sha256",
            value=self.encrypted_sha256,
        )
        _require_sha256(
            field_name="manifest_sha256",
            value=self.manifest_sha256,
        )

        _require_timezone_aware(
            field_name="captured_at",
            value=self.captured_at,
        )
        _require_timezone_aware(
            field_name="ingested_at",
            value=self.ingested_at,
        )

        if self.ingested_at < self.captured_at:
            raise ValueError("ingested_at must not be earlier than captured_at")


@dataclass(
    frozen=True,
    slots=True,
)
class PreparedEvidenceKey:
    """Wrapped encryption-key metadata for persisted evidence."""

    algorithm: str
    wrapped_key: str
    key_reference: str
    key_version: int = 1
    is_active: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(
            field_name="algorithm",
            value=self.algorithm,
        )
        _require_non_empty(
            field_name="wrapped_key",
            value=self.wrapped_key,
        )
        _require_non_empty(
            field_name="key_reference",
            value=self.key_reference,
        )

        if self.key_version <= 0:
            raise ValueError("key_version must be greater than zero")
