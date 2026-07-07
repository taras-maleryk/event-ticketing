from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking
from app.models.hold import Hold
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


async def test_book_hold_without_auth_returns_401(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
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

    response = await client.post(
        f"/api/holds/{created_hold['id']}/book",
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_book_missing_hold_returns_404(
    client: AsyncClient,
    regular_user_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/holds/999/book",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Hold not found"


async def test_book_hold_successfully(
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

    response = await client.post(
        f"/api/holds/{created_hold['id']}/book",
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 201
    assert response_data["seat_id"] == created_seat["id"]
    assert response_data["price_paid"] == created_seat["price"]
    assert "id" in response_data
    assert "ticket_token" in response_data
    assert response_data["ticket_token"]

    booking = await db_session.scalar(
        select(Booking).where(Booking.id == response_data["id"])
    )

    hold = await db_session.scalar(
        select(Hold).where(Hold.id == created_hold["id"])
    )

    assert booking is not None
    assert booking.seat_id == created_seat["id"]
    assert booking.price_paid == created_seat["price"]
    assert booking.ticket_token == response_data["ticket_token"]

    assert hold is None