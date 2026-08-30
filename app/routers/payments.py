import structlog
from fastapi import APIRouter, HTTPException, status
from stripe import StripeError

from app.core.deps import CurrentUser, db_dep
from app.schemas.payment import (
    CheckoutSessionResponse,
    PaymentStatusResponse,
)
from app.services import payments as payments_service

router = APIRouter(
    tags=["payments"],
)

logger = structlog.get_logger(__name__)


@router.post(
    "/holds/{hold_id}/checkout-session",
    status_code=status.HTTP_201_CREATED,
    response_model=CheckoutSessionResponse,
)
async def start_checkout(
    db: db_dep,
    current_user: CurrentUser,
    hold_id: int,
) -> CheckoutSessionResponse:
    payment_attempt = await payments_service.get_or_create_payment_attempt(
        db,
        hold_id=hold_id,
        user_id=current_user.id,
    )

    await db.commit()

    logger.info(
        "payment_attempt_ready",
        payment_attempt_id=payment_attempt.id,
        hold_id=payment_attempt.hold_id,
        user_id=payment_attempt.user_id,
        seat_id=payment_attempt.seat_id,
        status=payment_attempt.status.value,
        amount=payment_attempt.amount,
        currency=payment_attempt.currency,
    )

    try:
        stripe_session = await payments_service.create_stripe_checkout_session(
            payment_attempt
        )
    except StripeError as exc:
        logger.exception(
            "stripe_checkout_session_failed",
            payment_attempt_id=payment_attempt.id,
            hold_id=hold_id,
            user_id=current_user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("Could not create Stripe Checkout Session"),
        ) from exc

    if stripe_session.url is None:
        logger.error(
            "stripe_checkout_session_missing_url",
            payment_attempt_id=payment_attempt.id,
            stripe_checkout_session_id=(stripe_session.id),
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=("Stripe Checkout Session has no URL"),
        )

    payment_attempt = await payments_service.mark_payment_attempt_pending(
        db,
        payment_attempt_id=payment_attempt.id,
        stripe_checkout_session_id=(stripe_session.id),
    )

    await db.commit()

    logger.info(
        "payment_attempt_pending",
        payment_attempt_id=payment_attempt.id,
        stripe_checkout_session_id=(stripe_session.id),
        hold_id=payment_attempt.hold_id,
        user_id=payment_attempt.user_id,
        seat_id=payment_attempt.seat_id,
    )

    if payment_attempt.checkout_expires_at is None:
        raise RuntimeError("Payment attempt has no checkout expiration")

    return CheckoutSessionResponse(
        payment_attempt_id=payment_attempt.id,
        checkout_url=stripe_session.url,
        expires_at=(payment_attempt.checkout_expires_at),
    )


@router.get(
    "/payments/{payment_attempt_id}",
    response_model=PaymentStatusResponse,
)
async def get_payment_status(
    db: db_dep,
    current_user: CurrentUser,
    payment_attempt_id: int,
) -> PaymentStatusResponse:
    payment_attempt = await payments_service.get_payment_attempt_for_user(
        db,
        payment_attempt_id=payment_attempt_id,
        user_id=current_user.id,
    )

    return PaymentStatusResponse(
        payment_attempt_id=payment_attempt.id,
        status=payment_attempt.status,
        booking_id=payment_attempt.booking_id,
        amount=payment_attempt.amount,
        currency=payment_attempt.currency,
        checkout_expires_at=(payment_attempt.checkout_expires_at),
    )
