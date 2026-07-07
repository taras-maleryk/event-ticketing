from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import make_event_payload, create_event_as_organizer
from app.models.seat import Seat


def make_hall_config_payload() -> dict:
    return {
        "total_rows": 2,
        "seats_per_row": 3,
        "row_prices": [
            {
                "row": 1,
                "price": "10000",
            },
            {
                "row": 2,
                "price": "15000",
            },
        ],
        "excluded_seats": [],
    }


async def test_create_event_seats_without_auth_returns_401(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=make_hall_config_payload(),
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_create_event_seats_as_regular_user_returns_403(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=make_hall_config_payload(),
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 403
    assert response_data["detail"] == "Not enough permissions"


async def test_create_event_seats_for_missing_event_returns_404(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/events/999/seats",
        json=make_hall_config_payload(),
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Event not found"


async def test_create_event_seats_as_another_organizer_returns_403(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    another_organizer_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=make_hall_config_payload(),
        headers=another_organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 403
    assert response_data["detail"] == "You cannot manage seats for this event"


async def test_create_event_seats_as_owner_organizer_returns_201(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=make_hall_config_payload(),
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 201
    assert len(response_data) == 6

    assert response_data[0]["event_id"] == created_event["id"]
    assert response_data[0]["row"] == 1
    assert response_data[0]["number"] == 1
    assert "id" in response_data[0]
    assert "price" in response_data[0]

    assert response_data[-1]["event_id"] == created_event["id"]
    assert response_data[-1]["row"] == 2
    assert response_data[-1]["number"] == 3
    assert "id" in response_data[-1]
    assert "price" in response_data[-1]

    seats = (
        await db_session.execute(
            select(Seat)
            .where(Seat.event_id == created_event["id"])
            .order_by(Seat.row.asc(), Seat.number.asc())
        )
    ).scalars().all()

    assert len(seats) == 6
    assert seats[0].row == 1
    assert seats[0].number == 1
    assert seats[-1].row == 2
    assert seats[-1].number == 3