from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2a69569bb323"
down_revision: str | None = "20260809_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_verifications",
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        ("uq_evidence_verifications_evidence_idempotency_key"),
        "evidence_verifications",
        [
            "evidence_id",
            "idempotency_key",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        ("uq_evidence_verifications_evidence_idempotency_key"),
        "evidence_verifications",
        type_="unique",
    )

    op.drop_column(
        "evidence_verifications",
        "idempotency_key",
    )
