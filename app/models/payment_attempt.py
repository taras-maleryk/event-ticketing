from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.async_session import Base
from app.enums.payment_attempt_status import PaymentAttemptStatus


class PaymentAttempt(Base):
    __tablename__ = "payment_attempts"

    __table_args__ = (
        CheckConstraint(
            "amount >= 0",
            name="ck_payment_attempts_amount_non_negative",
        ),
        CheckConstraint(
            "char_length(currency) = 3",
            name="ck_payment_attempts_currency_length",
        ),
        CheckConstraint(
            "currency = lower(currency)",
            name="ck_payment_attempts_currency_lowercase",
        ),
        UniqueConstraint(
            "booking_id",
            name="uq_payment_attempts_booking_id",
        ),
        UniqueConstraint(
            "stripe_checkout_session_id",
            name="uq_payment_attempts_checkout_session_id",
        ),
        UniqueConstraint(
            "stripe_payment_intent_id",
            name="uq_payment_attempts_payment_intent_id",
        ),
        UniqueConstraint(
            "stripe_refund_id",
            name="uq_payment_attempts_refund_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    hold_id: Mapped[int | None] = mapped_column(
        ForeignKey("holds.id", ondelete="SET NULL"),
        nullable=True,
    )

    booking_id: Mapped[int | None] = mapped_column(
        ForeignKey("bookings.id", ondelete="SET NULL"),
        nullable=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id"),
        nullable=False,
    )

    amount: Mapped[int] = mapped_column(nullable=False)

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
    )

    status: Mapped[PaymentAttemptStatus] = mapped_column(
        SqlEnum(
            PaymentAttemptStatus,
            name="payment_attempt_status",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=PaymentAttemptStatus.CREATING,
        server_default=PaymentAttemptStatus.CREATING.value,
        nullable=False,
    )

    stripe_checkout_session_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    stripe_payment_intent_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    stripe_refund_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    checkout_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
