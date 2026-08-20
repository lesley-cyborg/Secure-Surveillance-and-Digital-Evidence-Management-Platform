from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0003"
down_revision: str | None = "20260719_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add nullable columns first so existing records
    # can be backfilled before enforcing NOT NULL.
    op.add_column(
        "detection_events",
        sa.Column(
            "source_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.add_column(
        "detection_events",
        sa.Column(
            "idempotency_key",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "detection_events",
        sa.Column(
            "schema_version",
            sa.String(length=16),
            nullable=True,
        ),
    )

    op.add_column(
        "detection_events",
        sa.Column(
            "frame_sequence_number",
            sa.BigInteger(),
            nullable=True,
        ),
    )

    # Existing detection rows predate AI ingestion.
    # Give them deterministic legacy identities.
    legacy_backfill = sa.text(
        """
        UPDATE detection_events
        SET
            source_event_id = id,
            idempotency_key =
                md5(id::text)
                || md5(
                    id::text || :legacy_suffix
                ),
            schema_version = 'legacy',
            frame_sequence_number = 0
        WHERE source_event_id IS NULL
        """
    ).bindparams(
        legacy_suffix="-legacy",
    )

    op.execute(legacy_backfill)

    op.alter_column(
        "detection_events",
        "source_event_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.alter_column(
        "detection_events",
        "idempotency_key",
        existing_type=sa.String(length=64),
        nullable=False,
    )

    op.alter_column(
        "detection_events",
        "schema_version",
        existing_type=sa.String(length=16),
        nullable=False,
    )

    op.alter_column(
        "detection_events",
        "frame_sequence_number",
        existing_type=sa.BigInteger(),
        nullable=False,
    )

    op.create_unique_constraint(
        "uq_detection_events_source_event_id",
        "detection_events",
        ["source_event_id"],
    )

    op.create_unique_constraint(
        "uq_detection_events_idempotency_key",
        "detection_events",
        ["idempotency_key"],
    )

    op.create_check_constraint(
        "ck_detection_events_idempotency_key_length",
        "detection_events",
        "length(idempotency_key) = 64",
    )

    op.create_check_constraint(
        "ck_detection_events_frame_sequence_nonnegative",
        "detection_events",
        "frame_sequence_number >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_detection_events_frame_sequence_nonnegative",
        "detection_events",
        type_="check",
    )

    op.drop_constraint(
        "ck_detection_events_idempotency_key_length",
        "detection_events",
        type_="check",
    )

    op.drop_constraint(
        "uq_detection_events_idempotency_key",
        "detection_events",
        type_="unique",
    )

    op.drop_constraint(
        "uq_detection_events_source_event_id",
        "detection_events",
        type_="unique",
    )

    op.drop_column(
        "detection_events",
        "frame_sequence_number",
    )

    op.drop_column(
        "detection_events",
        "schema_version",
    )

    op.drop_column(
        "detection_events",
        "idempotency_key",
    )

    op.drop_column(
        "detection_events",
        "source_event_id",
    )
