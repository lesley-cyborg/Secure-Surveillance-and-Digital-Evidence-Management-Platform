"""add custody lifecycle idempotency

Revision ID: bf2b79caa708
Revises: cc0c02de375c
Create Date: 2026-08-18 14:42:52.494753
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "bf2b79caa708"
down_revision: str | None = "cc0c02de375c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "chain_of_custody",
        sa.Column(
            "idempotency_scope",
            sa.String(length=64),
            nullable=True,
        ),
    )

    op.add_column(
        "chain_of_custody",
        sa.Column(
            "idempotency_key",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.create_unique_constraint(
        "uq_chain_of_custody_lifecycle_idempotency",
        "chain_of_custody",
        [
            "evidence_id",
            "idempotency_scope",
            "idempotency_key",
        ],
    )

    op.create_check_constraint(
        "ck_chain_of_custody_idempotency_pair",
        "chain_of_custody",
        (
            "("
            "idempotency_scope IS NULL "
            "AND idempotency_key IS NULL"
            ") OR ("
            "idempotency_scope IS NOT NULL "
            "AND idempotency_key IS NOT NULL"
            ")"
        ),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_chain_of_custody_idempotency_pair",
        "chain_of_custody",
        type_="check",
    )

    op.drop_constraint(
        "uq_chain_of_custody_lifecycle_idempotency",
        "chain_of_custody",
        type_="unique",
    )

    op.drop_column(
        "chain_of_custody",
        "idempotency_key",
    )

    op.drop_column(
        "chain_of_custody",
        "idempotency_scope",
    )
