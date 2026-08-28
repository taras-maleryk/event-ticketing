from httpx import AsyncClient

from app.core.config import settings


async def test_root_returns_hello_world(client: AsyncClient) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "Hello World!"}


async def test_cors_allows_configured_origin(client: AsyncClient) -> None:
    origin = settings.CORS_ALLOWED_ORIGINS[0]

    response = await client.get("/", headers={"Origin": origin})

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


async def test_cors_handles_preflight_request(client: AsyncClient) -> None:
    origin = settings.CORS_ALLOWED_ORIGINS[0]

    response = await client.options(
        "/api/auth/refresh",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]


async def test_cors_rejects_unconfigured_origin(client: AsyncClient) -> None:
    origin = "https://untrusted.invalid"

    assert origin not in settings.CORS_ALLOWED_ORIGINS

    response = await client.get("/", headers={"Origin": origin})

    assert response.status_code == 200
    assert "Access-Control-Allow-Origin" not in response.headers
