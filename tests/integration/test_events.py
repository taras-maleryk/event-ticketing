from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


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



