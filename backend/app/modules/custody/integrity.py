from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from app.db.models.enums import (
    CustodyEventType,
)

_SCHEMA_VERSION = "1.0"

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _timestamp(
    value: datetime,
) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Custody timestamps must be timezone-aware")

    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(
    frozen=True,
    slots=True,
)
class CustodyIntegrityArtifact:
    canonical_bytes: bytes
    record_hash: str


def build_custody_integrity(
    *,
    evidence_id: UUID,
    actor_user_id: UUID | None,
    from_user_id: UUID | None,
    to_user_id: UUID | None,
    previous_record_id: UUID | None,
    previous_record_hash: str | None,
    transfer_id: UUID | None,
    event_type: CustodyEventType,
    purpose: str | None,
    source_ip: str | None,
    device_identifier: str | None,
    event_metadata: Mapping[str, object],
    occurred_at: datetime,
) -> CustodyIntegrityArtifact:
    if previous_record_hash is not None and not _SHA256_PATTERN.fullmatch(previous_record_hash):
        raise ValueError("previous_record_hash must be a lowercase SHA-256 digest")

    payload = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_id": str(evidence_id),
        "actor_user_id": (str(actor_user_id) if actor_user_id else None),
        "from_user_id": (str(from_user_id) if from_user_id else None),
        "to_user_id": (str(to_user_id) if to_user_id else None),
        "previous_record_id": (str(previous_record_id) if previous_record_id else None),
        "previous_record_hash": (previous_record_hash),
        "transfer_id": (str(transfer_id) if transfer_id else None),
        "event_type": event_type.value,
        "purpose": purpose,
        "source_ip": source_ip,
        "device_identifier": (device_identifier),
        "event_metadata": dict(event_metadata),
        "occurred_at": _timestamp(occurred_at),
    }

    try:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (
        TypeError,
        ValueError,
    ) as exception:
        raise ValueError("Custody metadata must contain JSON-compatible values") from exception

    return CustodyIntegrityArtifact(
        canonical_bytes=canonical,
        record_hash=hashlib.sha256(canonical).hexdigest(),
    )
