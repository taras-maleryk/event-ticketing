from httpx import AsyncClient

from app.enums.seat_status import SeatStatus
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


def find_seat_by_id(
    response_data: list[dict],
    seat_id: int,
) -> dict:
    return next(
        seat
        for seat in response_data
        if seat["id"] == seat_id
    )


async def test_get_event_seats_returns_held_statuses(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    another_regular_user_headers: dict[str, str],
) -> None:
    created_event, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    held_seat_id = created_seats[0]["id"]
    available_seat_id = created_seats[1]["id"]

    await create_hold_for_seat(
        client,
        regular_user_headers,
        held_seat_id,
    )

    response_for_another_user = await client.get(
        f"/api/events/{created_event['id']}/seats",
        headers=another_regular_user_headers,
    )

    response_for_another_user_data = response_for_another_user.json()

    assert response_for_another_user.status_code == 200

    held_seat_for_another_user = find_seat_by_id(
        response_for_another_user_data,
        held_seat_id,
    )
    available_seat_for_another_user = find_seat_by_id(
        response_for_another_user_data,
        available_seat_id,
    )

    assert held_seat_for_another_user["status"] == SeatStatus.HELD.value
    assert available_seat_for_another_user["status"] == SeatStatus.AVAILABLE.value

    response_for_holder = await client.get(
        f"/api/events/{created_event['id']}/seats",
        headers=regular_user_headers,
    )

    response_for_holder_data = response_for_holder.json()

    assert response_for_holder.status_code == 200

    held_seat_for_holder = find_seat_by_id(
        response_for_holder_data,
        held_seat_id,
    )
    available_seat_for_holder = find_seat_by_id(
        response_for_holder_data,
        available_seat_id,
    )

    assert held_seat_for_holder["status"] == SeatStatus.HELD_BY_ME.value
    assert available_seat_for_holder["status"] == SeatStatus.AVAILABLE.value