from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.utils.events import create_event_as_organizer
from tests.utils.halls import make_hall_config_payload
from app.models.seat import Seat


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


async def test_create_event_seats_twice_returns_409(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    first_response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=make_hall_config_payload(),
        headers=organizer_headers,
    )

    assert first_response.status_code == 201

    second_response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=make_hall_config_payload(),
        headers=organizer_headers,
    )

    response_data = second_response.json()

    assert second_response.status_code == 409
    assert response_data["detail"] == "Seats have already been created for this event"


async def test_create_event_seats_respects_excluded_seats(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    hall_config = make_hall_config_payload(
        total_rows=2,
        seats_per_row=3,
        excluded_seats=[
            {
                "row": 1,
                "excluded_numbers": [2],
            },
            {
                "row": 2,
                "excluded_numbers": [1, 3],
            },
        ],
    )

    response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=hall_config,
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 201
    assert len(response_data) == 3

    returned_positions = [
        (seat["row"], seat["number"])
        for seat in response_data
    ]

    assert returned_positions == [
        (1, 1),
        (1, 3),
        (2, 2),
    ]

    seats = (
        await db_session.execute(
            select(Seat)
            .where(Seat.event_id == created_event["id"])
            .order_by(Seat.row.asc(), Seat.number.asc())
        )
    ).scalars().all()

    db_positions = [
        (seat.row, seat.number)
        for seat in seats
    ]

    assert db_positions == [
        (1, 1),
        (1, 3),
        (2, 2),
    ]


async def test_create_event_seats_uses_row_prices(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    hall_config = make_hall_config_payload(
        total_rows=2,
        seats_per_row=2,
        row_prices=[
            {
                "row": 1,
                "price": 1000,
            },
            {
                "row": 2,
                "price": 2500,
            },
        ],
    )

    response = await client.post(
        f"/api/events/{created_event['id']}/seats",
        json=hall_config,
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 201

    returned_prices = [
        seat["price"]
        for seat in response_data
    ]

    assert returned_prices == [
        1000,
        1000,
        2500,
        2500,
    ]

    seats = (
        await db_session.execute(
            select(Seat)
            .where(Seat.event_id == created_event["id"])
            .order_by(Seat.row.asc(), Seat.number.asc())
        )
    ).scalars().all()

    db_prices = [
        seat.price
        for seat in seats
    ]

    assert db_prices == [
        1000,
        1000,
        2500,
        2500,
    ]
