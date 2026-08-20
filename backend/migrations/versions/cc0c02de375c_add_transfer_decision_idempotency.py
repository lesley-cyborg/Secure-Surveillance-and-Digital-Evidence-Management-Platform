"""add transfer decision idempotency

Revision ID: cc0c02de375c
Revises: d42977a3d0bc
Create Date: 2026-08-16 20:48:35.318437
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cc0c02de375c"
down_revision: str | None = "d42977a3d0bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "evidence_transfers",
        sa.Column(
            "decision_idempotency_key",
            sa.String(length=255),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "evidence_transfers",
        "decision_idempotency_key",
    )
