import asyncio

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hold import Hold
from tests.utils.auth import create_auth_headers_for_user
from tests.utils.events import create_event_as_organizer
from tests.utils.seats import create_seats_for_event


async def test_concurrent_hold_requests_allow_only_one_success(
    client: AsyncClient,
    db_session: AsyncSession,
    organizer_headers: dict[str, str],
) -> None:
    created_event = await create_event_as_organizer(
        client,
        organizer_headers,
    )

    created_seats = await create_seats_for_event(
        client,
        organizer_headers,
        created_event["id"],
    )

    seat_id = created_seats[0]["id"]

    users_headers = []

    for index in range(10):
        headers = await create_auth_headers_for_user(
            db_session,
            name=f"Concurrent User {index}",
            email=f"concurrent-user-{index}@example.com",
            role="user",
        )
        users_headers.append(headers)

    requests = [
        client.post(
            f"/api/seats/{seat_id}/hold",
            headers=headers,
        )
        for headers in users_headers
    ]

    responses = await asyncio.gather(*requests)

    status_codes = [response.status_code for response in responses]

    assert status_codes.count(201) == 1
    assert status_codes.count(409) == 9
    assert all(status_code in {201, 409} for status_code in status_codes)

    active_holds_count = await db_session.scalar(
        select(func.count(Hold.id)).where(
            Hold.seat_id == seat_id,
            Hold.held_until > func.now(),
        )
    )

    assert active_holds_count == 1
