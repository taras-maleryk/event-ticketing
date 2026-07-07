from httpx import AsyncClient
from tests.utils.halls import make_hall_config_payload
from tests.utils.events import create_event_as_organizer

async def create_seats_for_event(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    event_id: int,
    hall_config: dict | None = None,
) -> list[dict]:
    response = await client.post(
        f"/api/events/{event_id}/seats",
        json=hall_config or make_hall_config_payload(),
        headers=organizer_headers,
    )

    assert response.status_code == 201

    return response.json()


async def create_event_with_seats(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    hall_config: dict | None = None,
) -> tuple[dict, list[dict]]:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    created_seats = await create_seats_for_event(
        client,
        organizer_headers,
        created_event["id"],
        hall_config,
    )

    return created_event, created_seats