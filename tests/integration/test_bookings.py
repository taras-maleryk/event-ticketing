from datetime import datetime

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, User
from tests.utils.seats import create_event_with_seats


async def create_booking_for_regular_user(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> tuple[Booking, dict, dict]:
    created_event, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )
    user = await db_session.scalar(
        select(User).where(User.email == "regular@example.com")
    )

    assert user is not None

    created_seat = created_seats[0]
    booking = Booking(
        seat_id=created_seat["id"],
        user_id=user.id,
        price_paid=created_seat["price"],
        ticket_token="test-ticket-token",
    )
    db_session.add(booking)
    await db_session.commit()
    await db_session.refresh(booking)

    return booking, created_event, created_seat


async def test_user_can_get_own_booking(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    booking, created_event, created_seat = await create_booking_for_regular_user(
        client,
        organizer_headers,
        db_session,
    )

    response = await client.get(
        f"/api/bookings/{booking.id}",
        headers=regular_user_headers,
    )

    assert response.status_code == 200

    response_data = response.json()

    assert response_data["id"] == booking.id
    assert response_data["seat_id"] == created_seat["id"]
    assert response_data["event_id"] == created_event["id"]
    assert response_data["event_name"] == created_event["name"]
    assert response_data["venue"] == created_event["venue"]
    assert response_data["row"] == created_seat["row"]
    assert response_data["number"] == created_seat["number"]
    assert response_data["price_paid"] == booking.price_paid
    assert response_data["ticket_token"] == booking.ticket_token
    assert datetime.fromisoformat(
        response_data["event_date"]
    ) == datetime.fromisoformat(created_event["date"])
    assert response_data["booked_at"] is not None


async def test_user_cannot_get_another_users_booking(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    another_regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    booking, _, _ = await create_booking_for_regular_user(
        client,
        organizer_headers,
        db_session,
    )

    response = await client.get(
        f"/api/bookings/{booking.id}",
        headers=another_regular_user_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


async def test_get_missing_booking_returns_404(
    client: AsyncClient,
    regular_user_headers: dict[str, str],
) -> None:
    response = await client.get(
        "/api/bookings/999999",
        headers=regular_user_headers,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


async def test_get_booking_without_auth_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/bookings/1")

    assert response.status_code == 401
