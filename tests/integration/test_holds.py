from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.hold import Hold
from app.models.seat import Seat
from app.models.user import User
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

    hold = await db_session.scalar(
        select(Hold).where(Hold.seat_id == seat_id)
    )

    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None
    assert hold is not None
    assert hold.seat_id == seat_id
    assert hold.user_id == user.id
    assert hold.held_until > datetime.now(timezone.utc)


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

    seat = await db_session.scalar(
        select(Seat).where(Seat.id == seat_id)
    )
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