from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
)
from app.models.user import User
from tests.utils.auth import create_auth_headers_for_user


async def test_protected_endpoint_with_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/events/999/seats",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_protected_endpoint_with_refresh_token_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    email = "refresh-token-user@example.com"

    await create_auth_headers_for_user(
        db_session,
        name="Refresh Token User",
        email=email,
        role="user",
    )

    user = await db_session.scalar(
        select(User).where(User.email == email)
    )

    assert user is not None

    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )

    response = await client.get(
        "/api/events/999/seats",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    response_data = response.json()

    assert response.status_code == 403
    assert response_data["detail"] == "Invalid token type"


async def test_protected_endpoint_with_access_token_without_sub_returns_401(
    client: AsyncClient,
) -> None:
    access_token = create_access_token(data={})

    response = await client.get(
        "/api/events/999/seats",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_protected_endpoint_with_invalid_sub_returns_401(
    client: AsyncClient,
) -> None:
    access_token = create_access_token(
        data={"sub": "not-an-integer"}
    )

    response = await client.get(
        "/api/events/999/seats",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_protected_endpoint_with_unknown_user_returns_401(
    client: AsyncClient,
) -> None:
    access_token = create_access_token(
        data={"sub": "999"}
    )

    response = await client.get(
        "/api/events/999/seats",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Could not validate credentials"
    assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_protected_endpoint_accepts_access_token_from_cookie(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    auth_headers = await create_auth_headers_for_user(
        db_session,
        name="Cookie Auth User",
        email="cookie-auth@example.com",
        role="user",
    )

    access_token = auth_headers["Authorization"].removeprefix("Bearer ")

    client.cookies.set(
        "access_token",
        access_token,
    )

    response = await client.get(
        "/api/events/999/seats",
    )

    response_data = response.json()

    assert response.status_code == 404
    assert response_data["detail"] == "Event not found"