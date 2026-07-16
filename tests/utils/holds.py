from httpx import AsyncClient


async def create_hold_for_seat(
    client: AsyncClient,
    user_headers: dict[str, str],
    seat_id: int,
) -> dict:
    response = await client.post(
        f"/api/seats/{seat_id}/hold",
        headers=user_headers,
    )

    assert response.status_code == 201

    return response.json()
