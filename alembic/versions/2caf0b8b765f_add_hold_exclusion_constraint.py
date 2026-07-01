"""add hold exclusion constraint

Revision ID: 2caf0b8b765f
Revises: b2932c958541
Create Date: 2026-07-01 16:46:44.400803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2caf0b8b765f'
down_revision: Union[str, Sequence[str], None] = 'b2932c958541'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.drop_column("holds", "payment_started_at")
    op.drop_column("holds", "status")

    op.execute(
        """
        ALTER TABLE holds
        ADD CONSTRAINT excl_holds_seat_time_overlap
        EXCLUDE USING gist (
            seat_id WITH =,
            tstzrange(held_from, held_until, '[)') WITH &&
        )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE holds
        DROP CONSTRAINT IF EXISTS excl_holds_seat_time_overlap
        """
    )

    op.add_column(
        "holds",
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
        ),
    )

    op.add_column(
        "holds",
        sa.Column(
            "payment_started_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )
