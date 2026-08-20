from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_SAFE_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


@dataclass(
    frozen=True,
    slots=True,
)
class StoredEvidenceObject:
    bucket: str
    object_key: str
    version_id: str | None
    etag: str | None
    size_bytes: int
    content_type: str | None

    def __post_init__(self) -> None:
        if not self.bucket.strip():
            raise ValueError("bucket must not be empty")

        if not self.object_key.strip():
            raise ValueError("object_key must not be empty")

        if self.size_bytes <= 0:
            raise ValueError("size_bytes must be greater than zero")


class EvidenceObjectStorage(Protocol):
    async def ensure_ready(
        self,
    ) -> None:
        """Verify the backing storage configuration."""

    async def put_object(
        self,
        *,
        object_key: str,
        payload: bytes,
        content_type: str,
        metadata: Mapping[str, str] | None = None,
    ) -> StoredEvidenceObject:
        """Persist encrypted evidence bytes."""

    async def get_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> bytes:
        """Retrieve encrypted evidence bytes."""

    async def stat_object(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> StoredEvidenceObject:
        """Retrieve object metadata."""

    async def delete_for_compensation(
        self,
        *,
        object_key: str,
        version_id: str | None = None,
    ) -> None:
        """Delete an object only while compensating a failed ingest."""


def build_evidence_object_key(
    *,
    incident_id: UUID,
    evidence_number: str,
    captured_at: datetime,
    encrypted_sha256: str,
) -> str:
    """Build the canonical encrypted-evidence storage key."""

    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    if not _SAFE_SEGMENT_PATTERN.fullmatch(evidence_number):
        raise ValueError("evidence_number contains unsafe storage-key characters")

    if not _SHA256_PATTERN.fullmatch(encrypted_sha256):
        raise ValueError("encrypted_sha256 must be a lowercase SHA-256 digest")

    captured_utc = captured_at.astimezone(UTC)

    date_path = captured_utc.strftime("%Y/%m/%d")

    return f"incidents/{incident_id}/{date_path}/{evidence_number}/{encrypted_sha256}.sspe"
