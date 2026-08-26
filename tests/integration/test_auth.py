from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token
from app.models.user import User


async def test_register_user_successfully(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {
        "name": "John Doe",
        "email": "john@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    response = await client.post(
        "/api/auth/register",
        json=payload,
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == 1
    assert data["name"] == "John Doe"
    assert data["email"] == "john@example.com"
    assert data["role"] == "user"
    assert "created_at" in data
    assert "hashed_password" not in data
    assert "password" not in data

    user = await db_session.scalar(select(User).where(User.email == "john@example.com"))

    assert user is not None
    assert user.name == "John Doe"
    assert user.email == "john@example.com"
    assert user.role == "user"
    assert user.hashed_password != "StrongPass123"


async def test_register_trims_user_name(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    payload = {
        "name": "  John Doe  ",
        "email": "john@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 201
    assert response.json()["name"] == "John Doe"

    user = await db_session.scalar(select(User).where(User.email == "john@example.com"))

    assert user is not None
    assert user.name == "John Doe"


async def test_register_rejects_blank_user_name(client: AsyncClient) -> None:
    payload = {
        "name": "   ",
        "email": "john@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 422


async def test_register_rejects_user_name_longer_than_database_limit(
    client: AsyncClient,
) -> None:
    payload = {
        "name": "a" * 101,
        "email": "john@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 422


async def test_register_rejects_password_longer_than_limit(
    client: AsyncClient,
) -> None:
    password = "StrongPass123" + "a" * 116
    payload = {
        "name": "John Doe",
        "email": "john@example.com",
        "password": password,
        "confirm_password": password,
    }

    response = await client.post("/api/auth/register", json=payload)

    assert response.status_code == 422


async def test_register_duplicate_email(
    client: AsyncClient,
) -> None:
    payload = {
        "name": "John Doe",
        "email": "john@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }
    response = await client.post(
        "/api/auth/register",
        json=payload,
    )

    assert response.status_code == 201

    second_payload = {
        "name": "Tom Norris",
        "email": "john@example.com",
        "password": "SuperStrongPass123",
        "confirm_password": "SuperStrongPass123",
    }

    second_response = await client.post("/api/auth/register", json=second_payload)

    data = second_response.json()

    assert second_response.status_code == 400
    assert data["detail"] == "User with this email already exists"


async def test_login_user_successfully(
    client: AsyncClient,
) -> None:
    register_payload = {
        "name": "Tom Norris",
        "email": "tom@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    register_response = await client.post(
        "/api/auth/register",
        json=register_payload,
    )

    assert register_response.status_code == 201

    login_payload = {
        "username": "tom@example.com",
        "password": "StrongPass123",
    }

    login_response = await client.post(
        "/api/auth/login",
        data=login_payload,
    )

    assert login_response.status_code == 200

    login_data = login_response.json()

    assert login_data["access_token"] is not None
    assert login_data["refresh_token"] is not None
    assert login_data["token_type"] == "bearer"

    assert "access_token" in login_response.cookies
    assert "refresh_token" in login_response.cookies


async def test_login_with_incorrect_password_returns_401(
    client: AsyncClient,
) -> None:
    register_payload = {
        "name": "Tom Norris",
        "email": "tom@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    register_response = await client.post(
        "/api/auth/register",
        json=register_payload,
    )

    assert register_response.status_code == 201

    login_payload = {
        "username": "tom@example.com",
        "password": "IncorrectPass123",
    }

    login_response = await client.post(
        "/api/auth/login",
        data=login_payload,
    )

    login_data = login_response.json()

    assert login_response.status_code == 401
    assert login_data["detail"] == "Incorrect email or password"
    assert login_response.headers["WWW-Authenticate"] == "Bearer"
    assert "access_token" not in login_response.cookies
    assert "refresh_token" not in login_response.cookies


async def test_refresh_token_successfully(
    client: AsyncClient,
) -> None:
    register_payload = {
        "name": "Tom Norris",
        "email": "tom@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    register_response = await client.post(
        "/api/auth/register",
        json=register_payload,
    )

    assert register_response.status_code == 201

    login_payload = {
        "username": "tom@example.com",
        "password": "StrongPass123",
    }

    login_response = await client.post(
        "/api/auth/login",
        data=login_payload,
    )

    assert login_response.status_code == 200
    assert "refresh_token" in login_response.cookies

    refresh_response = await client.post("/api/auth/refresh")

    assert refresh_response.status_code == 200

    refresh_data = refresh_response.json()

    assert refresh_data["access_token"] is not None
    assert refresh_data["token_type"] == "bearer"
    assert "access_token" in refresh_response.cookies


async def test_refresh_token_without_cookie_returns_401(
    client: AsyncClient,
) -> None:
    refresh_response = await client.post("/api/auth/refresh")

    refresh_data = refresh_response.json()

    assert refresh_response.status_code == 401
    assert refresh_data["detail"] == "Refresh token missing"


async def test_logout_successfully(
    client: AsyncClient,
) -> None:
    register_payload = {
        "name": "Tom Norris",
        "email": "tom@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    register_response = await client.post(
        "/api/auth/register",
        json=register_payload,
    )

    assert register_response.status_code == 201

    login_payload = {
        "username": "tom@example.com",
        "password": "StrongPass123",
    }

    login_response = await client.post(
        "/api/auth/login",
        data=login_payload,
    )

    assert login_response.status_code == 200
    assert "access_token" in client.cookies
    assert "refresh_token" in client.cookies

    logout_response = await client.post("/api/auth/logout")

    logout_data = logout_response.json()

    assert logout_response.status_code == 200
    assert logout_data["detail"] == "Successfully logged out"
    assert "access_token" not in client.cookies
    assert "refresh_token" not in client.cookies


async def test_refresh_with_invalid_token_returns_401(
    client: AsyncClient,
) -> None:
    client.cookies.set(
        "refresh_token",
        "not-a-valid-token",
    )

    response = await client.post("/api/auth/refresh")

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Invalid or expired refresh token"


async def test_refresh_with_access_token_returns_401(
    client: AsyncClient,
) -> None:
    access_token = create_access_token(data={"sub": "1"})

    client.cookies.set(
        "refresh_token",
        access_token,
    )

    response = await client.post("/api/auth/refresh")

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Invalid or expired refresh token"


async def test_refresh_token_without_sub_returns_401(
    client: AsyncClient,
) -> None:
    refresh_token = create_refresh_token(data={})

    client.cookies.set(
        "refresh_token",
        refresh_token,
    )

    response = await client.post("/api/auth/refresh")

    response_data = response.json()

    assert response.status_code == 401
    assert response_data["detail"] == "Invalid token claims"
