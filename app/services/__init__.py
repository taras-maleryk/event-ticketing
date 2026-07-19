from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.booking import Booking
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.models.seat import Seat


async def get_or_create_payment_attempt(
    db: AsyncSession,
    *,
    hold_id: int,
    user_id: int,
) -> PaymentAttempt:
    hold = await db.scalar(select(Hold).where(Hold.id == hold_id).with_for_update())

    if hold is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hold not found",
        )

    if hold.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hold is not yours",
        )

    if hold.held_until <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hold has expired",
        )

    booking_id = await db.scalar(
        select(Booking.id).where(Booking.seat_id == hold.seat_id)
    )

    if booking_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seat is already booked",
        )

    existing_attempt = await db.scalar(
        select(PaymentAttempt)
        .where(
            PaymentAttempt.hold_id == hold.id,
            PaymentAttempt.status.in_(
                [
                    PaymentAttemptStatus.CREATING,
                    PaymentAttemptStatus.PENDING,
                ]
            ),
        )
        .order_by(PaymentAttempt.created_at.desc())
        .limit(1)
    )

    if existing_attempt is not None:
        await db.commit()
        return existing_attempt

    seat = await db.get(Seat, hold.seat_id)

    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found",
        )

    payment_attempt = PaymentAttempt(
        hold_id=hold.id,
        user_id=hold.user_id,
        seat_id=hold.seat_id,
        amount=seat.price,
        currency=settings.STRIPE_CURRENCY,
    )

    db.add(payment_attempt)

    await db.commit()
    await db.refresh(payment_attempt)

    return payment_attempt
