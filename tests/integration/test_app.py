from httpx import AsyncClient

async def test_root_returns_hello_world(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World!"}

