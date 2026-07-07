from httpx import AsyncClient
from tests.utils.halls import make_hall_config_payload


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