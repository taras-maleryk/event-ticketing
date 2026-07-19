from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from stripe import StripeError

from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models import Seat, User
from app.models.booking import Booking
from app.models.hold import Hold
from app.models.payment_attempt import PaymentAttempt
from app.services import payments as payments_service
from app.services.payments import get_or_create_payment_attempt
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


@dataclass
class FakeStripeCheckoutSession:
    id: str
    url: str | None


async def test_payment_attempt_stores_price_snapshot(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_seat = created_seats[0]

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seat["id"],
    )

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None

    original_price = created_seat["price"]

    payment_attempt = PaymentAttempt(
        hold_id=created_hold["id"],
        user_id=user.id,
        seat_id=created_seat["id"],
        amount=original_price,
        currency="uah",
    )

    db_session.add(payment_attempt)
    await db_session.commit()
    await db_session.refresh(payment_attempt)

    assert payment_attempt.status == PaymentAttemptStatus.CREATING
    assert payment_attempt.amount == original_price
    assert payment_attempt.currency == "uah"
    assert payment_attempt.booking_id is None
    assert payment_attempt.stripe_checkout_session_id is None
    assert payment_attempt.stripe_payment_intent_id is None

    seat = await db_session.get(Seat, created_seat["id"])

    assert seat is not None

    seat.price = original_price + 500

    await db_session.commit()
    await db_session.refresh(payment_attempt)

    assert payment_attempt.amount == original_price


async def test_create_payment_attempt_for_hold(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_seat = created_seats[0]

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seat["id"],
    )

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None

    payment_attempt = await get_or_create_payment_attempt(
        db_session,
        hold_id=created_hold["id"],
        user_id=user.id,
    )

    assert payment_attempt.id is not None
    assert payment_attempt.hold_id == created_hold["id"]
    assert payment_attempt.user_id == user.id
    assert payment_attempt.seat_id == created_seat["id"]
    assert payment_attempt.amount == created_seat["price"]
    assert payment_attempt.currency == "uah"
    assert payment_attempt.status == PaymentAttemptStatus.CREATING


async def test_reuses_existing_active_payment_attempt(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None

    first_attempt = await get_or_create_payment_attempt(
        db_session,
        hold_id=created_hold["id"],
        user_id=user.id,
    )

    second_attempt = await get_or_create_payment_attempt(
        db_session,
        hold_id=created_hold["id"],
        user_id=user.id,
    )

    attempts_count = await db_session.scalar(
        select(func.count())
        .select_from(PaymentAttempt)
        .where(PaymentAttempt.hold_id == created_hold["id"])
    )

    assert second_attempt.id == first_attempt.id
    assert attempts_count == 1


async def test_payment_attempt_for_another_users_hold_returns_403(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    another_regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )

    another_user = await db_session.scalar(
        select(User).where(User.email == "another-regular@example.com")
    )

    assert another_user is not None

    with pytest.raises(HTTPException) as exc_info:
        await get_or_create_payment_attempt(
            db_session,
            hold_id=created_hold["id"],
            user_id=another_user.id,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Hold is not yours"


async def test_payment_attempt_for_expired_hold_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )

    hold = await db_session.get(Hold, created_hold["id"])

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert hold is not None
    assert user is not None

    hold.held_from = datetime.now(UTC) - timedelta(minutes=20)
    hold.held_until = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_or_create_payment_attempt(
            db_session,
            hold_id=hold.id,
            user_id=user.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Hold has expired"


async def test_payment_attempt_for_booked_seat_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_seat = created_seats[0]

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seat["id"],
    )

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None

    booking = Booking(
        seat_id=created_seat["id"],
        user_id=user.id,
        price_paid=created_seat["price"],
        ticket_token="payment-attempt-booked-seat",
    )

    db_session.add(booking)
    await db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_or_create_payment_attempt(
            db_session,
            hold_id=created_hold["id"],
            user_id=user.id,
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Seat is already booked"


async def test_create_checkout_session_successfully(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )

    async def fake_create_stripe_checkout_session(
        _payment_attempt: PaymentAttempt,
    ) -> FakeStripeCheckoutSession:
        return FakeStripeCheckoutSession(
            id="cs_test_checkout_session",
            url=("https://checkout.stripe.com/c/pay/cs_test_checkout_session"),
        )

    monkeypatch.setattr(
        payments_service,
        "create_stripe_checkout_session",
        fake_create_stripe_checkout_session,
    )

    response = await client.post(
        (f"/api/holds/{created_hold['id']}/checkout-session"),
        headers=regular_user_headers,
    )

    assert response.status_code == 201

    response_data = response.json()

    assert response_data["checkout_url"] == (
        "https://checkout.stripe.com/c/pay/cs_test_checkout_session"
    )

    payment_attempt = await db_session.scalar(
        select(PaymentAttempt).where(
            PaymentAttempt.id == response_data["payment_attempt_id"]
        )
    )

    hold = await db_session.get(
        Hold,
        created_hold["id"],
    )

    assert payment_attempt is not None
    assert hold is not None

    assert payment_attempt.status == PaymentAttemptStatus.PENDING
    assert payment_attempt.stripe_checkout_session_id == ("cs_test_checkout_session")
    assert payment_attempt.checkout_expires_at is not None
    assert hold.held_until == payment_attempt.checkout_expires_at


async def test_checkout_returns_502_when_stripe_fails(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )

    async def fake_create_stripe_checkout_session(
        _payment_attempt: PaymentAttempt,
    ) -> FakeStripeCheckoutSession:
        raise StripeError("Stripe is unavailable")

    monkeypatch.setattr(
        payments_service,
        "create_stripe_checkout_session",
        fake_create_stripe_checkout_session,
    )

    response = await client.post(
        (f"/api/holds/{created_hold['id']}/checkout-session"),
        headers=regular_user_headers,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == ("Could not create Stripe Checkout Session")

    payment_attempt = await db_session.scalar(
        select(PaymentAttempt).where(PaymentAttempt.hold_id == created_hold["id"])
    )

    assert payment_attempt is not None
    assert payment_attempt.status == PaymentAttemptStatus.CREATING
    assert payment_attempt.stripe_checkout_session_id is None
    assert payment_attempt.checkout_expires_at is not None
