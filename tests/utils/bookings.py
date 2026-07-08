from httpx import AsyncClient


async def create_booking_for_hold(
    client: AsyncClient,
    user_headers: dict[str, str],
    hold_id: int,
) -> dict:
    response = await client.post(
        f"/api/holds/{hold_id}/book",
        headers=user_headers,
    )

    assert response.status_code == 201

    return response.json()