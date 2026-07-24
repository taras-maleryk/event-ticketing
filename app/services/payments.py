from datetime import UTC, datetime, timedelta

import structlog
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from stripe.checkout import Session
from stripe.params.checkout import SessionCreateParams

from app.core.config import settings
from app.core.stripe_client import stripe_client
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.booking import Booking
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.models.seat import Seat

logger = structlog.get_logger(__name__)


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

    now = datetime.now(UTC)

    if hold.held_until <= now:
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

    attempts_result = await db.scalars(
        select(PaymentAttempt).where(
            PaymentAttempt.hold_id == hold.id,
            PaymentAttempt.status.in_(
                [
                    PaymentAttemptStatus.CREATING,
                    PaymentAttemptStatus.PENDING,
                ]
            ),
        )
    )

    existing_attempt = attempts_result.one_or_none()

    if existing_attempt is not None:
        return existing_attempt

    seat = await db.get(Seat, hold.seat_id)

    if seat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seat not found",
        )

    checkout_expires_at = now + timedelta(
        minutes=settings.STRIPE_CHECKOUT_EXPIRE_MINUTES
    )

    payment_attempt = PaymentAttempt(
        hold_id=hold.id,
        user_id=hold.user_id,
        seat_id=hold.seat_id,
        amount=seat.price,
        currency=settings.STRIPE_CURRENCY,
        checkout_expires_at=checkout_expires_at,
    )

    hold.held_until = checkout_expires_at

    db.add(payment_attempt)
    await db.flush()
    await db.refresh(payment_attempt)

    return payment_attempt


async def create_stripe_checkout_session(
    payment_attempt: PaymentAttempt,
) -> Session:
    if payment_attempt.hold_id is None:
        raise RuntimeError("Payment attempt has no hold")

    if payment_attempt.checkout_expires_at is None:
        raise RuntimeError("Payment attempt has no checkout expiration")

    metadata = {
        "payment_attempt_id": str(payment_attempt.id),
        "hold_id": str(payment_attempt.hold_id),
        "user_id": str(payment_attempt.user_id),
        "seat_id": str(payment_attempt.seat_id),
    }

    correlation_id = structlog.contextvars.get_contextvars().get("correlation_id")

    if isinstance(correlation_id, str) and correlation_id:
        metadata["correlation_id"] = correlation_id

    params: SessionCreateParams = {
        "mode": "payment",
        "payment_method_types": ["card"],
        "line_items": [
            {
                "price_data": {
                    "currency": payment_attempt.currency,
                    "unit_amount": payment_attempt.amount,
                    "product_data": {
                        "name": "Event Ticket",
                    },
                },
                "quantity": 1,
            }
        ],
        "success_url": settings.STRIPE_SUCCESS_URL,
        "cancel_url": settings.STRIPE_CANCEL_URL,
        "expires_at": int(payment_attempt.checkout_expires_at.timestamp()),
        "client_reference_id": str(payment_attempt.id),
        "metadata": metadata,
    }

    checkout_session = await stripe_client.v1.checkout.sessions.create_async(
        params=params,
        options={
            "idempotency_key": (f"payment-attempt:{payment_attempt.id}"),
        },
    )

    logger.info(
        "stripe_checkout_session_created",
        payment_attempt_id=payment_attempt.id,
        stripe_checkout_session_id=checkout_session.id,
        hold_id=payment_attempt.hold_id,
    )

    return checkout_session


async def mark_payment_attempt_pending(
    db: AsyncSession,
    *,
    payment_attempt_id: int,
    stripe_checkout_session_id: str,
) -> PaymentAttempt:
    payment_attempt = await db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == payment_attempt_id)
        .with_for_update()
    )

    if payment_attempt is None:
        raise RuntimeError("Payment attempt not found")

    existing_session_id = payment_attempt.stripe_checkout_session_id

    if (
        existing_session_id is not None
        and existing_session_id != stripe_checkout_session_id
    ):
        raise RuntimeError("Payment attempt belongs to another Stripe session")

    payment_attempt.stripe_checkout_session_id = stripe_checkout_session_id
    payment_attempt.status = PaymentAttemptStatus.PENDING

    await db.flush()

    return payment_attempt


async def get_payment_attempt_for_user(
    db: AsyncSession,
    *,
    payment_attempt_id: int,
    user_id: int,
) -> PaymentAttempt:
    payment_attempt = await db.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.id == payment_attempt_id,
            PaymentAttempt.user_id == user_id,
        )
    )

    if payment_attempt is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment attempt not found",
        )

    return payment_attempt
