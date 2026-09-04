"""track payment refunds

Revision ID: 5e6f7a8b9c10
Revises: 7c1e5a9b2d40
Create Date: 2026-09-04 10:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5e6f7a8b9c10"
down_revision: str | Sequence[str] | None = "7c1e5a9b2d40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = (
    "creating",
    "pending",
    "succeeded",
    "failed",
    "expired",
    "requires_refund",
)
NEW_STATUSES = (*OLD_STATUSES, "refunded")


def payment_status_constraint(statuses: tuple[str, ...]) -> str:
    values = ", ".join(f"'{status}'" for status in statuses)
    return f"status IN ({values})"


def upgrade() -> None:
    op.add_column(
        "payment_attempts",
        sa.Column("stripe_refund_id", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_payment_attempts_refund_id",
        "payment_attempts",
        ["stripe_refund_id"],
    )
    op.drop_constraint(
        "payment_attempt_status",
        "payment_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "payment_attempt_status",
        "payment_attempts",
        payment_status_constraint(NEW_STATUSES),
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE payment_attempts "
            "SET status = 'requires_refund' "
            "WHERE status = 'refunded'"
        )
    )
    op.drop_constraint(
        "payment_attempt_status",
        "payment_attempts",
        type_="check",
    )
    op.create_check_constraint(
        "payment_attempt_status",
        "payment_attempts",
        payment_status_constraint(OLD_STATUSES),
    )
    op.drop_constraint(
        "uq_payment_attempts_refund_id",
        "payment_attempts",
        type_="unique",
    )
    op.drop_column("payment_attempts", "stripe_refund_id")
