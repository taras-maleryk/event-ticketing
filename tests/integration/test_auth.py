from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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

    user = await db_session.scalar(
        select(User).where(User.email == "john@example.com")
    )

    assert user is not None
    assert user.name == "John Doe"
    assert user.email == "john@example.com"
    assert user.role == "user"
    assert user.hashed_password != "StrongPass123"


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
        "confirm_password": "SuperStrongPass123"
    }

    second_response = await client.post(
        "/api/auth/register",
        json=second_payload
    )

    data = second_response.json()

    assert second_response.status_code == 400
    assert data["detail"] == "User with this email already exists"