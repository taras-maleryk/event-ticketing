from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

def make_event_payload(
    *,
    name: str = "SomeEvent",
    venue: str = "SomeVenue",
    days_from_now: int = 1,
    description: str = "SomeDescription",
) -> dict[str, str]:
    return {
        "name": name,
        "venue": venue,
        "date": (
            datetime.now(timezone.utc) + timedelta(days=days_from_now)
        ).isoformat(),
        "description": description,
    }


async def create_event_as_organizer(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    payload: dict[str, str] | None = None,
) -> dict:
    event_payload = payload or make_event_payload()

    response = await client.post(
        "/api/events",
        json=event_payload,
        headers=organizer_headers,
    )

    assert response.status_code == 201

    return response.json()