from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO
from uuid import UUID

from app.db.models.enums import (
    EvidenceSourceType,
    EvidenceType,
)

_DEFAULT_HASH_CHUNK_SIZE = 1024 * 1024
_SHA256_HEX_LENGTH = 64
_MANIFEST_SCHEMA_VERSION = "1.0"


def _validate_sha256(
    value: str,
    *,
    field_name: str,
) -> None:
    if len(value) != _SHA256_HEX_LENGTH:
        raise ValueError(f"{field_name} must contain 64 hexadecimal characters")

    try:
        bytes.fromhex(value)
    except ValueError as exception:
        raise ValueError(f"{field_name} must be a valid SHA-256 hexadecimal digest") from exception

    if value != value.lower():
        raise ValueError(f"{field_name} must use lowercase hexadecimal characters")


def _canonical_timestamp(
    value: datetime,
) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Manifest timestamps must be timezone-aware")

    normalized = value.astimezone(UTC)

    return normalized.isoformat(timespec="microseconds").replace(
        "+00:00",
        "Z",
    )


@dataclass(
    frozen=True,
    slots=True,
)
class OriginalEvidenceDigest:
    """Integrity information calculated from raw evidence."""

    sha256: str
    file_size_bytes: int

    def __post_init__(self) -> None:
        _validate_sha256(
            self.sha256,
            field_name="sha256",
        )

        if self.file_size_bytes <= 0:
            raise ValueError("file_size_bytes must be greater than zero")


@dataclass(
    frozen=True,
    slots=True,
)
class EvidenceForensicManifest:
    """Canonical metadata describing an acquired evidence object."""

    evidence_number: str

    incident_id: UUID
    source_detection_id: UUID | None

    source_type: EvidenceSourceType
    evidence_type: EvidenceType

    original_filename: str
    mime_type: str

    file_size_bytes: int
    original_sha256: str

    captured_at: datetime

    schema_version: str = _MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.evidence_number.strip():
            raise ValueError("evidence_number must not be empty")

        if not self.original_filename.strip():
            raise ValueError("original_filename must not be empty")

        if not self.mime_type.strip():
            raise ValueError("mime_type must not be empty")

        if self.file_size_bytes <= 0:
            raise ValueError("file_size_bytes must be greater than zero")

        _validate_sha256(
            self.original_sha256,
            field_name="original_sha256",
        )

        # Validate timezone-awareness eagerly.
        _canonical_timestamp(self.captured_at)

        if self.schema_version != _MANIFEST_SCHEMA_VERSION:
            raise ValueError("Unsupported evidence manifest schema version")

    def to_canonical_dict(
        self,
    ) -> dict[str, object]:
        return {
            "schema_version": (self.schema_version),
            "evidence_number": (self.evidence_number),
            "incident_id": str(self.incident_id),
            "source_detection_id": (
                str(self.source_detection_id) if self.source_detection_id is not None else None
            ),
            "source_type": (self.source_type.value),
            "evidence_type": (self.evidence_type.value),
            "original_filename": (self.original_filename),
            "mime_type": self.mime_type,
            "file_size_bytes": (self.file_size_bytes),
            "original_sha256": (self.original_sha256),
            "captured_at": (_canonical_timestamp(self.captured_at)),
        }

    def canonical_bytes(self) -> bytes:
        """Return deterministic UTF-8 JSON bytes."""

        payload = json.dumps(
            self.to_canonical_dict(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

        return payload.encode("utf-8")


@dataclass(
    frozen=True,
    slots=True,
)
class ForensicManifestArtifact:
    manifest: EvidenceForensicManifest
    canonical_bytes: bytes
    sha256: str

    def __post_init__(self) -> None:
        if not self.canonical_bytes:
            raise ValueError("canonical_bytes must not be empty")

        _validate_sha256(
            self.sha256,
            field_name="sha256",
        )


def sha256_bytes(
    content: bytes,
) -> str:
    if not content:
        raise ValueError("Evidence content must not be empty")

    return hashlib.sha256(content).hexdigest()


def sha256_stream(
    stream: BinaryIO,
    *,
    chunk_size: int = (_DEFAULT_HASH_CHUNK_SIZE),
) -> OriginalEvidenceDigest:
    """Hash binary content without loading it all into memory.

    Seekable streams are restored to their original position after
    hashing. Non-seekable streams are consumed.
    """

    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")

    original_position: int | None = None

    if stream.seekable():
        original_position = stream.tell()

    digest = hashlib.sha256()
    file_size_bytes = 0

    try:
        while True:
            chunk = stream.read(chunk_size)

            if not chunk:
                break

            digest.update(chunk)
            file_size_bytes += len(chunk)

    finally:
        if original_position is not None:
            stream.seek(original_position)

    if file_size_bytes == 0:
        raise ValueError("Evidence content must not be empty")

    return OriginalEvidenceDigest(
        sha256=digest.hexdigest(),
        file_size_bytes=file_size_bytes,
    )


def analyze_evidence_bytes(
    content: bytes,
) -> OriginalEvidenceDigest:
    """Calculate forensic digest and length for an in-memory object."""

    return sha256_stream(BytesIO(content))


def build_manifest_artifact(
    manifest: EvidenceForensicManifest,
) -> ForensicManifestArtifact:
    canonical_bytes = manifest.canonical_bytes()

    digest = hashlib.sha256(canonical_bytes).hexdigest()

    return ForensicManifestArtifact(
        manifest=manifest,
        canonical_bytes=canonical_bytes,
        sha256=digest,
    )
