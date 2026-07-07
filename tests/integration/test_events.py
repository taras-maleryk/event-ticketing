from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.event import Event

async def test_create_event_without_auth_401(client: AsyncClient) -> None:
    payload = {
        "name": "SomeEvent",
        "venue": "SomeVenue",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "description": "SomeDescription",
    }

    response = await client.post(
        "/api/events",
        json=payload)

    data = response.json()

    assert response.status_code == 401
    assert data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_create_event_as_regular_user_returns_403(
    regular_user_client: AsyncClient,
) -> None:
    event_payload = {
        "name": "SomeEvent",
        "venue": "SomeVenue",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "description": "SomeDescription",
    }

    event_response = await regular_user_client.post(
        "/api/events",
        json=event_payload,
    )

    response_data = event_response.json()

    assert event_response.status_code == 403
    assert response_data["detail"] == "Not enough permissions"


async def test_create_event_as_organizer_returns_201(
    organizer_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    event_payload = {
        "name": "SomeEvent",
        "venue": "SomeVenue",
        "date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        "description": "SomeDescription",
    }

    event_response = await organizer_client.post(
        "/api/events",
        json=event_payload,
    )

    response_data = event_response.json()

    assert event_response.status_code == 201
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
