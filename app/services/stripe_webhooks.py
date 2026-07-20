import secrets
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import Event
from stripe.checkout import Session as StripeCheckoutSession

from app.core.config import settings
from app.core.stripe_client import stripe_client
from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.booking import Booking
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.models.stripe_webhook_event import StripeWebhookEvent


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


async def process_stripe_event(
    db: AsyncSession,
    *,
    event: Event,
) -> None:
    if event.type != "checkout.session.completed":
        return

    checkout_session = cast(
        StripeCheckoutSession,
        event.data.object,
    )

    await process_completed_checkout(
        db,
        event=event,
        checkout_session=checkout_session,
    )


async def process_completed_checkout(
    db: AsyncSession,
    *,
    event: Event,
    checkout_session: StripeCheckoutSession,
) -> None:
    if checkout_session.payment_status != "paid":
        return

    metadata = checkout_session.metadata

    if metadata is None:
        raise RuntimeError(
            "Stripe Checkout Session has no metadata"
        )

    payment_attempt_id_value = metadata.get(
        "payment_attempt_id"
    )

    if payment_attempt_id_value is None:
        raise RuntimeError("Stripe Checkout Session has no payment_attempt_id")

    try:
        payment_attempt_id = int(payment_attempt_id_value)
    except ValueError as exc:
        raise RuntimeError("Invalid payment_attempt_id in Stripe metadata") from exc

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

    if webhook_event_id is None:
        return

    payment_attempt = await db.scalar(
        select(PaymentAttempt)
        .where(PaymentAttempt.id == payment_attempt_id)
        .with_for_update()
    )

    if payment_attempt is None:
        raise RuntimeError("Payment attempt not found")

    if payment_attempt.status == PaymentAttemptStatus.SUCCEEDED:
        return

    if payment_attempt.stripe_checkout_session_id != checkout_session.id:
        raise RuntimeError("Stripe Checkout Session does not match the payment attempt")

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
        return

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
