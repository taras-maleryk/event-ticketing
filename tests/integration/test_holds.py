from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.payment_attempt_status import PaymentAttemptStatus
from app.models.booking import Booking
from app.models.event import Event
from app.models.hold import Hold
from app.models.seat import Seat
from app.models.user import User
from app.services.payments import get_or_create_payment_attempt
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


async def test_hold_seat_without_auth_returns_401(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    response = await client.post(
        f"/api/seats/{seat_id}/hold",
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_hold_missing_seat_returns_404(
    client: AsyncClient,
    regular_user_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/seats/999/hold",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Seat not found"


async def test_hold_seat_successfully(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    response = await client.post(
        f"/api/seats/{seat_id}/hold",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 201
    assert response_data["seat_id"] == seat_id
    assert "id" in response_data
    assert "held_until" in response_data

    hold = await db_session.scalar(select(Hold).where(Hold.seat_id == seat_id))

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None
    assert hold is not None
    assert hold.seat_id == seat_id
    assert hold.user_id == user.id
    assert hold.held_until > datetime.now(UTC)


async def test_hold_seat_for_started_event_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    event = await db_session.get(Event, created_event["id"])

    assert event is not None

    event.date = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.commit()

    response = await client.post(
        f"/api/seats/{created_seats[0]['id']}/hold",
        headers=regular_user_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Event has already started"

    hold = await db_session.scalar(
        select(Hold).where(Hold.seat_id == created_seats[0]["id"])
    )

    assert hold is None


async def test_hold_already_held_seat_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    another_regular_user_headers: dict[str, str],
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    first_response = await client.post(
        f"/api/seats/{seat_id}/hold",
        headers=regular_user_headers,
    )

    assert first_response.status_code == 201

    second_response = await client.post(
        f"/api/seats/{seat_id}/hold",
        headers=another_regular_user_headers,
    )

    response_data = second_response.json()

    assert second_response.status_code == 409
    assert response_data["detail"] == "Seat is already held"


async def test_hold_booked_seat_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    seat = await db_session.scalar(select(Seat).where(Seat.id == seat_id))
    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert seat is not None
    assert user is not None

    booking = Booking(
        seat_id=seat.id,
        user_id=user.id,
        price_paid=seat.price,
        ticket_token="test-ticket-token",
    )

    db_session.add(booking)
    await db_session.commit()

    response = await client.post(
        f"/api/seats/{seat_id}/hold",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 409
    assert response_data["detail"] == "Seat is already booked"


async def test_release_hold_without_auth_returns_401(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    response = await client.delete(
        f"/api/seats/{seat_id}/hold",
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_release_hold_for_missing_seat_returns_404(
    client: AsyncClient,
    regular_user_headers: dict[str, str],
) -> None:
    response = await client.delete(
        "/api/seats/999/hold",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Seat not found"


async def test_release_hold_successfully(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        seat_id,
    )

    response = await client.delete(
        f"/api/seats/{seat_id}/hold",
        headers=regular_user_headers,
    )

    assert response.status_code == 204
    assert response.content == b""

    hold = await db_session.scalar(select(Hold).where(Hold.id == created_hold["id"]))

    assert hold is None


@pytest.mark.parametrize(
    "payment_status",
    [
        PaymentAttemptStatus.CREATING,
        PaymentAttemptStatus.PENDING,
    ],
)
async def test_release_hold_with_active_payment_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    payment_status: PaymentAttemptStatus,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]
    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        seat_id,
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
    payment_attempt.status = payment_status
    await db_session.commit()

    response = await client.delete(
        f"/api/seats/{seat_id}/hold",
        headers=regular_user_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Hold has an active payment"
    assert await db_session.get(Hold, created_hold["id"]) is not None


async def test_release_hold_when_user_has_no_hold_returns_404(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    seat_id = created_seats[0]["id"]

    response = await client.delete(
        f"/api/seats/{seat_id}/hold",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Hold not found"


async def test_release_another_users_hold_returns_404(
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

    seat_id = created_seats[0]["id"]

    created_hold = await create_hold_for_seat(
        client,
        regular_user_headers,
        seat_id,
    )

    response = await client.delete(
        f"/api/seats/{seat_id}/hold",
        headers=another_regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Hold not found"

    hold = await db_session.scalar(select(Hold).where(Hold.id == created_hold["id"]))

    assert hold is not None
    assert hold.seat_id == seat_id
