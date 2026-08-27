from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.event import Event
from tests.utils.events import create_event_as_organizer, make_event_payload


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


async def test_create_event_trims_required_text(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    response = await client.post(
        "/api/events",
        json=make_event_payload(
            name="  Trimmed Event  ",
            venue="  Main Hall  ",
        ),
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 201
    assert response_data["name"] == "Trimmed Event"
    assert response_data["venue"] == "Main Hall"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", "   "),
        ("venue", "\t"),
    ],
)
async def test_create_event_rejects_blank_required_text(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    field: str,
    value: str,
) -> None:
    payload = make_event_payload()
    payload[field] = value

    response = await client.post(
        "/api/events",
        json=payload,
        headers=organizer_headers,
    )

    assert response.status_code == 422


async def test_create_event_rejects_naive_datetime(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    payload = make_event_payload()
    payload["date"] = (datetime.now() + timedelta(days=1)).isoformat()

    response = await client.post(
        "/api/events",
        json=payload,
        headers=organizer_headers,
    )

    assert response.status_code == 422


async def test_list_events_rejects_naive_date_filter(client: AsyncClient) -> None:
    response = await client.get(
        "/api/events",
        params={"date_from": "2026-08-26T12:00:00"},
    )

    assert response.status_code == 422


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

    response = await client.get(f"/api/events/{created_event['id']}")

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
    assert response_data["page"] == 1
    assert response_data["page_size"] == 10
    assert response_data["total"] == 1
    assert response_data["pages"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Future Event"


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
    assert response_data["total"] == 1
    assert response_data["pages"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Past Event"


async def test_list_events_returns_requested_page_and_metadata(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    for name, days_from_now in [
        ("First Event", 1),
        ("Second Event", 2),
        ("Third Event", 3),
    ]:
        await create_event_as_organizer(
            client,
            organizer_headers,
            make_event_payload(
                name=name,
                days_from_now=days_from_now,
            ),
        )

    response = await client.get(
        "/api/events",
        params={"page": 2, "page_size": 2},
    )

    response_data = response.json()

    assert response.status_code == 200
    assert response_data["page"] == 2
    assert response_data["page_size"] == 2
    assert response_data["total"] == 3
    assert response_data["pages"] == 2
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Third Event"


async def test_list_events_with_invalid_page_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/events",
        params={"page": 0},
    )

    assert response.status_code == 422


async def test_list_events_with_too_large_page_size_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/events",
        params={"page_size": 21},
    )

    assert response.status_code == 422


async def test_update_own_event_as_organizer_returns_200(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Original Event",
            venue="Original Venue",
            description="Original Description",
        ),
    )

    update_payload = {
        "name": "Updated Event",
        "description": "Updated Description",
    }

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json=update_payload,
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 200
    assert response_data["id"] == created_event["id"]
    assert response_data["name"] == "Updated Event"
    assert response_data["venue"] == "Original Venue"
    assert response_data["description"] == "Updated Description"
    assert response_data["organizer_id"] == created_event["organizer_id"]
    assert "date" in response_data

    updated_event = await db_session.scalar(
        select(Event).where(Event.id == created_event["id"])
    )

    assert updated_event is not None
    assert updated_event.name == "Updated Event"
    assert updated_event.venue == "Original Venue"
    assert updated_event.description == "Updated Description"
    assert updated_event.organizer_id == created_event["organizer_id"]


@pytest.mark.parametrize("field", ["name", "venue", "date"])
async def test_update_event_rejects_null_required_fields(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    field: str,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json={field: None},
        headers=organizer_headers,
    )

    assert response.status_code == 422


async def test_update_event_trims_required_text(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json={"name": "  Updated Event  ", "venue": "  Updated Venue  "},
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 200
    assert response_data["name"] == "Updated Event"
    assert response_data["venue"] == "Updated Venue"


async def test_update_event_rejects_naive_datetime(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json={"date": "2026-08-27T12:00:00"},
        headers=organizer_headers,
    )

    assert response.status_code == 422


async def test_update_event_rejects_past_date(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    original_date = datetime.fromisoformat(created_event["date"])
    past_date = datetime.now(UTC) - timedelta(minutes=1)

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json={"date": past_date.isoformat()},
        headers=organizer_headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Event date must be in the future"

    event = await db_session.get(Event, created_event["id"])

    assert event is not None
    assert event.date == original_date


async def test_update_missing_event_as_organizer_returns_404(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    response = await client.patch(
        "/api/events/999",
        json={"name": "Updated Event"},
        headers=organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Event not found"


async def test_update_event_as_regular_user_returns_403(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(name="Owner Event"),
    )

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json={"name": "Updated By Regular User"},
        headers=regular_user_headers,
    )

    response_data = response.json()

    assert response.status_code == 403
    assert response_data["detail"] == "Not enough permissions"

    event_after_failed_update = await db_session.scalar(
        select(Event).where(Event.id == created_event["id"])
    )

    assert event_after_failed_update is not None
    assert event_after_failed_update.name == "Owner Event"


async def test_update_another_organizers_event_returns_403(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    another_organizer_headers: dict[str, str],
    db_session: AsyncSession,
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(name="Owner Event"),
    )

    response = await client.patch(
        f"/api/events/{created_event['id']}",
        json={"name": "Updated By Another Organizer"},
        headers=another_organizer_headers,
    )

    response_data = response.json()

    assert response.status_code == 403
    assert response_data["detail"] == "You cannot update this event"

    event_after_failed_update = await db_session.scalar(
        select(Event).where(Event.id == created_event["id"])
    )

    assert event_after_failed_update is not None
    assert event_after_failed_update.name == "Owner Event"


async def test_list_events_filters_by_date_from(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Earlier Event",
            days_from_now=1,
        ),
    )

    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Later Event",
            days_from_now=3,
        ),
    )

    date_from = datetime.now(UTC) + timedelta(days=2)

    response = await client.get(
        "/api/events",
        params={"date_from": date_from.isoformat()},
    )

    response_data = response.json()

    assert response.status_code == 200, response.text
    assert response_data["total"] == 1
    assert response_data["pages"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Later Event"


async def test_list_events_filters_by_date_to(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Earlier Event",
            days_from_now=1,
        ),
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Later Event",
            days_from_now=3,
        ),
    )

    date_to = datetime.now(UTC) + timedelta(days=2)

    response = await client.get(
        "/api/events",
        params={"date_to": date_to.isoformat()},
    )

    response_data = response.json()

    assert response.status_code == 200, response.text
    assert response_data["total"] == 1
    assert response_data["pages"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Earlier Event"


async def test_list_events_filters_by_date_range(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Before Range",
            days_from_now=1,
        ),
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Inside Range",
            days_from_now=3,
        ),
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="After Range",
            days_from_now=5,
        ),
    )

    now = datetime.now(UTC)
    date_from = now + timedelta(days=2)
    date_to = now + timedelta(days=4)

    response = await client.get(
        "/api/events",
        params={
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
        },
    )

    response_data = response.json()

    assert response.status_code == 200, response.text
    assert response_data["total"] == 1
    assert response_data["pages"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Inside Range"


async def test_list_events_with_invalid_date_range_returns_422(
    client: AsyncClient,
) -> None:
    now = datetime.now(UTC)

    response = await client.get(
        "/api/events",
        params={
            "date_from": (now + timedelta(days=3)).isoformat(),
            "date_to": (now + timedelta(days=1)).isoformat(),
        },
    )

    assert response.status_code == 422


async def test_list_events_pagination_metadata_respects_date_filters(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    for name, days_from_now in [
        ("First Event", 1),
        ("Second Event", 2),
        ("Third Event", 3),
        ("Fourth Event", 4),
        ("Fifth Event", 5),
    ]:
        await create_event_as_organizer(
            client,
            organizer_headers,
            make_event_payload(
                name=name,
                days_from_now=days_from_now,
            ),
        )

    now = datetime.now(UTC)

    response = await client.get(
        "/api/events",
        params={
            "date_from": (now + timedelta(days=2, hours=12)).isoformat(),
            "date_to": (now + timedelta(days=5, hours=12)).isoformat(),
            "page": 2,
            "page_size": 2,
        },
    )

    response_data = response.json()

    assert response.status_code == 200, response.text
    assert response_data["page"] == 2
    assert response_data["page_size"] == 2
    assert response_data["total"] == 3
    assert response_data["pages"] == 2
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Fifth Event"


async def test_list_events_combines_past_status_with_date_range(
    client: AsyncClient,
    organizer_headers: dict[str, str],
) -> None:
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Older Past Event",
            days_from_now=-5,
        ),
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Past Event Inside Range",
            days_from_now=-3,
        ),
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Recent Past Event",
            days_from_now=-1,
        ),
    )
    await create_event_as_organizer(
        client,
        organizer_headers,
        make_event_payload(
            name="Future Event",
            days_from_now=1,
        ),
    )

    now = datetime.now(UTC)

    response = await client.get(
        "/api/events",
        params={
            "event_status": "past",
            "date_from": (now - timedelta(days=4)).isoformat(),
            "date_to": (now - timedelta(days=2)).isoformat(),
        },
    )

    response_data = response.json()

    assert response.status_code == 200, response.text
    assert response_data["total"] == 1
    assert response_data["pages"] == 1
    assert len(response_data["items"]) == 1
    assert response_data["items"][0]["name"] == "Past Event Inside Range"
