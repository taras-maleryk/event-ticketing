from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import Event

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


async def test_create_event_without_auth_returns_401(client: AsyncClient) -> None:
    payload = make_event_payload()

    response = await client.post(
        "/api/events",
        json=payload,
    )

    data = response.json()

    assert response.status_code == 401
    assert data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_create_event_as_regular_user_returns_403(
    client: AsyncClient,
    regular_user_headers: dict[str, str],
) -> None:
    event_response = await client.post(
        "/api/events",
        json=make_event_payload(),
        headers=regular_user_headers,
    )

    response_data = event_response.json()

    assert event_response.status_code == 403
    assert response_data["detail"] == "Not enough permissions"


async def test_create_event_as_organizer_returns_201(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    response_data = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    assert response_data["id"] == 1
    assert response_data["name"] == "SomeEvent"
    assert response_data["venue"] == "SomeVenue"
    assert response_data["description"] == "SomeDescription"
    assert response_data["organizer_id"] == 1
    assert "date" in response_data

    created_event = await db_session.scalar(
        select(Event).where(Event.id == response_data["id"])
    )

    assert created_event is not None
    assert created_event.name == "SomeEvent"
    assert created_event.venue == "SomeVenue"
    assert created_event.description == "SomeDescription"
    assert created_event.organizer_id == response_data["organizer_id"]


async def test_get_event_by_id_returns_event(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    event_payload = make_event_payload(
        name="Future Event",
        venue="Main Hall",
        days_from_now=1,
        description="Future event description",
    )

    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
        event_payload,
    )

    response = await client.get(
        f"/api/events/{created_event['id']}"
    )

    response_data = response.json()

    assert response.status_code == 200
    assert response_data["id"] == created_event["id"]
    assert response_data["name"] == "Future Event"
    assert response_data["venue"] == "Main Hall"
    assert response_data["description"] == "Future event description"
    assert response_data["organizer_id"] == created_event["organizer_id"]
    assert "date" in response_data


async def test_get_missing_event_returns_404(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/events/999")

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Event not found"


async def test_list_events_returns_upcoming_events_by_default(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    future_payload = make_event_payload(
        name="Future Event",
        days_from_now=1,
    )
    past_payload = make_event_payload(
        name="Past Event",
        days_from_now=-1,
    )

    await create_event_as_organizer(
        client,
        organizer_headers,
        future_payload,
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        past_payload,
    )

    response = await client.get("/api/events")

    response_data = response.json()

    assert response.status_code == 200
    assert len(response_data) == 1
    assert response_data[0]["name"] == "Future Event"


async def test_list_events_with_past_status_returns_past_events(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    future_payload = make_event_payload(
        name="Future Event",
        days_from_now=1,
    )
    past_payload = make_event_payload(
        name="Past Event",
        days_from_now=-1,
    )

    await create_event_as_organizer(
        client,
        organizer_headers,
        future_payload,
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        past_payload,
    )

    response = await client.get(
        "/api/events",
        params={"event_status": "past"},
    )

    response_data = response.json()

    assert response.status_code == 200
    assert len(response_data) == 1
    assert response_data[0]["name"] == "Past Event"
