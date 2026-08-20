from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.db.models.enums import (
    CustodyEventType,
)
from app.modules.custody.integrity import (
    CustodyIntegrityArtifact,
    build_custody_integrity,
)

_EVIDENCE_ID = UUID("33333333-3333-3333-3333-333333333333")


def build(
    *,
    metadata: dict[str, object] | None = None,
    occurred_at: datetime | None = None,
) -> CustodyIntegrityArtifact:
    return build_custody_integrity(
        evidence_id=_EVIDENCE_ID,
        actor_user_id=None,
        from_user_id=None,
        to_user_id=None,
        previous_record_id=None,
        previous_record_hash=None,
        transfer_id=None,
        event_type=(CustodyEventType.ACQUIRED),
        purpose=("Initial secure evidence acquisition"),
        source_ip="127.0.0.1",
        device_identifier="pytest",
        event_metadata=(metadata or {"source": "integration"}),
        occurred_at=(
            occurred_at
            or datetime(
                2026,
                8,
                9,
                10,
                0,
                tzinfo=UTC,
            )
        ),
    )


def test_custody_hash_is_deterministic() -> None:
    first = build()
    second = build()

    assert first.canonical_bytes == second.canonical_bytes
    assert first.record_hash == second.record_hash


def test_metadata_change_changes_hash() -> None:
    first = build(metadata={"value": 1})

    second = build(metadata={"value": 2})

    assert first.record_hash != second.record_hash


def test_custody_hash_is_sha256() -> None:
    artifact = build()

    assert len(artifact.record_hash) == 64

    int(
        artifact.record_hash,
        16,
    )


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        build(
            occurred_at=datetime(
                2026,
                8,
                9,
                10,
                0,
            )
        )
