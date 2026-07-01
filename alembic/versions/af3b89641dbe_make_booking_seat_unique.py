"""make booking seat unique

Revision ID: af3b89641dbe
Revises: 2caf0b8b765f
Create Date: 2026-07-01 19:08:06.163187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af3b89641dbe'
down_revision: Union[str, Sequence[str], None] = '2caf0b8b765f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_bookings_seat_id",
        "bookings",
        ["seat_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_bookings_seat_id",
        "bookings",
        type_="unique",
    )