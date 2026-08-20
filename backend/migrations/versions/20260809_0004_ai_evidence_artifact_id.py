from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "20260809_0004"
down_revision = "20260801_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column(
            "source_artifact_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )

    op.create_index(
        "uq_evidence_source_artifact_id",
        "evidence",
        ["source_artifact_id"],
        unique=True,
        postgresql_where=sa.text(
            "source_artifact_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_evidence_source_artifact_id",
        table_name="evidence",
    )

    op.drop_column(
        "evidence",
        "source_artifact_id",
    )