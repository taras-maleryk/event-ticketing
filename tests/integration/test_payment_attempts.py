from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.payment_attempt import PaymentAttempt
from app.models.seat import Seat
from app.models.user import User
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


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
