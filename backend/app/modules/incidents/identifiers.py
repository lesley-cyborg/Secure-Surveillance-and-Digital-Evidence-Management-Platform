from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4


def generate_incident_number(
    *,
    detected_at: datetime,
) -> str:
    """Generate a human-readable unique incident number."""

    if detected_at.tzinfo is None:
        raise ValueError("detected_at must be timezone-aware")

    timestamp = detected_at.astimezone(UTC).strftime("%Y%m%d-%H%M%S")

    suffix = uuid4().hex[:12].upper()

    return f"INC-{timestamp}-{suffix}"
