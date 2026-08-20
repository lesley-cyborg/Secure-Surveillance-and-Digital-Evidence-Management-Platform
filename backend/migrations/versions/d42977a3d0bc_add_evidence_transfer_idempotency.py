from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d42977a3d0bc"
down_revision: str | None = "2a69569bb323"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_transfers",
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_evidence_transfers_evidence_idempotency_key",
        "evidence_transfers",
        [
            "evidence_id",
            "idempotency_key",
        ],
    )

    op.create_index(
        "uq_evidence_transfers_one_pending",
        "evidence_transfers",
        ["evidence_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'PENDING'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_evidence_transfers_one_pending",
        table_name="evidence_transfers",
    )

    op.drop_constraint(
        "uq_evidence_transfers_evidence_idempotency_key",
        "evidence_transfers",
        type_="unique",
    )

    op.drop_column(
        "evidence_transfers",
        "idempotency_key",
    )