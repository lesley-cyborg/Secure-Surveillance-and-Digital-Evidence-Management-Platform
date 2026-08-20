from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def generate_evidence_number(
    *,
    captured_at: datetime,
) -> str:
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")

    timestamp = captured_at.astimezone(UTC).strftime("%Y%m%d-%H%M%S")

    suffix = uuid4().hex[:12].upper()

    return f"EVD-{timestamp}-{suffix}"
