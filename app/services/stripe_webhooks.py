import secrets
from dataclasses import dataclass
from typing import Literal, cast

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import Event
from stripe.checkout import (
    Session as StripeCheckoutSession,
)

from app.core.config import settings
from app.core.stripe_client import stripe_client
from app.enums.payment_attempt_status import (
    PaymentAttemptStatus,
)
from app.models.booking import Booking
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.models.stripe_webhook_event import (
    StripeWebhookEvent,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class StripeEventOutcome:
    event_name: str
    level: Literal["info", "warning"]
    fields: dict[str, object]


def construct_stripe_event(
    *,
    payload: bytes,
    signature: str,
) -> Event:
    return stripe_client.construct_event(
        payload,
        signature,
        settings.STRIPE_WEBHOOK_SECRET,
    )


def get_payment_attempt_id(
    checkout_session: StripeCheckoutSession,
) -> int:
    metadata = checkout_session.metadata

    if metadata is None:
        raise RuntimeError("Stripe Checkout Session has no metadata")

    payment_attempt_id_value = metadata.get("payment_attempt_id")

    if payment_attempt_id_value is None:
        raise RuntimeError("Stripe Checkout Session has no payment_attempt_id")

    try:
        return int(payment_attempt_id_value)
    except ValueError as exc:
        raise RuntimeError("Invalid payment_attempt_id in Stripe metadata") from exc


def get_checkout_log_context(
    checkout_session: StripeCheckoutSession,
) -> dict[str, object]:
    metadata = checkout_session.metadata

    if metadata is None:
        return {}

    correlation_id = metadata.get("correlation_id")

    if not isinstance(correlation_id, str):
        return {}

    if not correlation_id:
        return {}

    return {
        "correlation_id": correlation_id,
    }


async def register_stripe_event(
    db: AsyncSession,
    *,
    event: Event,
) -> bool:
    insert_event_statement = (
        insert(StripeWebhookEvent)
        .values(
            stripe_event_id=event.id,
            event_type=event.type,
        )
        .on_conflict_do_nothing(
            index_elements=[
                StripeWebhookEvent.stripe_event_id,
            ]
        )
        .returning(StripeWebhookEvent.id)
    )

    webhook_event_id = await db.scalar(insert_event_statement)

    return webhook_event_id is not None


async def process_stripe_event(
    db: AsyncSession,
    *,
    event: Event,
) -> StripeEventOutcome | None:
    if event.type == "checkout.session.completed":
        checkout_session = cast(
            StripeCheckoutSession,
            event.data.object,
        )

        logger.info(
            "stripe_webhook_received",
            stripe_event_id=event.id,
            stripe_event_type=event.type,
            stripe_checkout_session_id=(checkout_session.id),
            **get_checkout_log_context(checkout_session),
        )

        return await process_completed_checkout(
            db,
            event=event,
            checkout_session=checkout_session,
        )

    if event.type == "checkout.session.expired":
        checkout_session = cast(
            StripeCheckoutSession,
            event.data.object,
        )

        logger.info(
            "stripe_webhook_received",
            stripe_event_id=event.id,
            stripe_event_type=event.type,
            stripe_checkout_session_id=(checkout_session.id),
            **get_checkout_log_context(checkout_session),
        )

        return await process_expired_checkout(
            db,
            event=event,
            checkout_session=checkout_session,
        )

    logger.info(
        "stripe_webhook_ignored",
        stripe_event_id=event.id,
        stripe_event_type=event.type,
    )

    return None


async def process_completed_checkout(
    db: AsyncSession,
    *,
    event: Event,
    checkout_session: StripeCheckoutSession,
) -> StripeEventOutcome | None:
    log_context = get_checkout_log_context(checkout_session)

    if checkout_session.payment_status != "paid":
        logger.info(
            "stripe_checkout_completion_ignored",
            stripe_event_id=event.id,
            stripe_checkout_session_id=(checkout_session.id),
            payment_status=(checkout_session.payment_status),
            **log_context,
        )
        return None

    payment_attempt_id = get_payment_attempt_id(checkout_session)

    event_registered = await register_stripe_event(
        db,
        event=event,
    )

    if not event_registered:
        logger.info(
            "stripe_webhook_duplicate",
            stripe_event_id=event.id,
            stripe_event_type=event.type,
            stripe_checkout_session_id=(checkout_session.id),
            payment_attempt_id=payment_attempt_id,
            **log_context,
        )
        return None

    payment_attempt = await db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == payment_attempt_id)
        .with_for_update()
    )

    if payment_attempt is None:
        raise RuntimeError("Payment attempt not found")

    if payment_attempt.status == PaymentAttemptStatus.SUCCEEDED:
        logger.info(
            "payment_already_succeeded",
            payment_attempt_id=payment_attempt.id,
            stripe_event_id=event.id,
            stripe_checkout_session_id=(checkout_session.id),
            **log_context,
        )
        return None
    if payment_attempt.status not in {
        PaymentAttemptStatus.CREATING,
        PaymentAttemptStatus.PENDING,
    }:
        logger.info(
            "stripe_checkout_completion_ignored",
            payment_attempt_id=payment_attempt.id,
            payment_attempt_status=payment_attempt.status.value,
            stripe_event_id=event.id,
            stripe_checkout_session_id=checkout_session.id,
            **log_context,
        )
        return None

    existing_session_id = payment_attempt.stripe_checkout_session_id

    if existing_session_id is not None and existing_session_id != checkout_session.id:
        raise RuntimeError("Stripe Checkout Session does not match the payment attempt")

    payment_attempt.stripe_checkout_session_id = checkout_session.id

    if checkout_session.amount_total is None:
        raise RuntimeError("Stripe Checkout Session has no amount_total")

    if checkout_session.amount_total != payment_attempt.amount:
        raise RuntimeError("Stripe payment amount does not match the payment attempt")

    if checkout_session.currency is None:
        raise RuntimeError("Stripe Checkout Session has no currency")

    if checkout_session.currency.lower() != payment_attempt.currency.lower():
        raise RuntimeError("Stripe payment currency does not match the payment attempt")

    existing_booking = await db.scalar(
        select(Booking).where(Booking.seat_id == payment_attempt.seat_id)
    )

    if existing_booking is not None:
        payment_attempt.status = PaymentAttemptStatus.REQUIRES_REFUND

        await db.flush()

        return StripeEventOutcome(
            event_name="payment_requires_refund",
            level="warning",
            fields={
                "payment_attempt_id": (payment_attempt.id),
                "booking_id": existing_booking.id,
                "stripe_event_id": event.id,
                "stripe_checkout_session_id": (checkout_session.id),
                **log_context,
            },
        )

    booking = Booking(
        seat_id=payment_attempt.seat_id,
        user_id=payment_attempt.user_id,
        price_paid=payment_attempt.amount,
        ticket_token=secrets.token_urlsafe(32),
    )

    db.add(booking)

    payment_attempt.status = PaymentAttemptStatus.SUCCEEDED

    if payment_attempt.hold_id is not None:
        hold = await db.get(
            Hold,
            payment_attempt.hold_id,
        )

        if hold is not None:
            await db.delete(hold)

    await db.flush()

    return StripeEventOutcome(
        event_name="payment_succeeded",
        level="info",
        fields={
            "payment_attempt_id": payment_attempt.id,
            "booking_id": booking.id,
            "stripe_event_id": event.id,
            "stripe_checkout_session_id": (checkout_session.id),
            "seat_id": payment_attempt.seat_id,
            "user_id": payment_attempt.user_id,
            "amount": payment_attempt.amount,
            "currency": payment_attempt.currency,
            **log_context,
        },
    )


async def process_expired_checkout(
    db: AsyncSession,
    *,
    event: Event,
    checkout_session: StripeCheckoutSession,
) -> StripeEventOutcome | None:
    log_context = get_checkout_log_context(checkout_session)

    payment_attempt_id = get_payment_attempt_id(checkout_session)

    event_registered = await register_stripe_event(
        db,
        event=event,
    )

    if not event_registered:
        logger.info(
            "stripe_webhook_duplicate",
            stripe_event_id=event.id,
            stripe_event_type=event.type,
            stripe_checkout_session_id=(checkout_session.id),
            payment_attempt_id=payment_attempt_id,
            **log_context,
        )
        return None

    payment_attempt = await db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == payment_attempt_id)
        .with_for_update()
    )

    if payment_attempt is None:
        raise RuntimeError("Payment attempt not found")

    existing_session_id = payment_attempt.stripe_checkout_session_id

    if existing_session_id is not None and existing_session_id != checkout_session.id:
        raise RuntimeError("Stripe Checkout Session does not match the payment attempt")

    payment_attempt.stripe_checkout_session_id = checkout_session.id

    if payment_attempt.status in {
        PaymentAttemptStatus.SUCCEEDED,
        PaymentAttemptStatus.REQUIRES_REFUND,
    }:
        logger.info(
            "stripe_checkout_expiration_ignored",
            payment_attempt_id=payment_attempt.id,
            payment_status=(payment_attempt.status.value),
            stripe_event_id=event.id,
            stripe_checkout_session_id=(checkout_session.id),
            **log_context,
        )
        return None

    if payment_attempt.status == PaymentAttemptStatus.EXPIRED:
        logger.info(
            "payment_already_expired",
            payment_attempt_id=payment_attempt.id,
            stripe_event_id=event.id,
            stripe_checkout_session_id=(checkout_session.id),
            **log_context,
        )
        return None

    if payment_attempt.status not in {
        PaymentAttemptStatus.CREATING,
        PaymentAttemptStatus.PENDING,
    }:
        raise RuntimeError(
            f"Payment attempt cannot be expired from status {payment_attempt.status}"
        )

    payment_attempt.status = PaymentAttemptStatus.EXPIRED

    if payment_attempt.hold_id is not None:
        hold = await db.get(
            Hold,
            payment_attempt.hold_id,
        )

        if hold is not None:
            await db.delete(hold)

    await db.flush()

    return StripeEventOutcome(
        event_name="payment_expired",
        level="info",
        fields={
            "payment_attempt_id": payment_attempt.id,
            "stripe_event_id": event.id,
            "stripe_checkout_session_id": (checkout_session.id),
            "seat_id": payment_attempt.seat_id,
            "user_id": payment_attempt.user_id,
            **log_context,
        },
    )
