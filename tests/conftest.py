from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.async_session import get_db
from app.main import app


if settings.TEST_DATABASE_URL is None:
    raise RuntimeError(
        "TEST_DATABASE_URL must be set before running tests"
    )

database_name = settings.TEST_DATABASE_URL.rsplit("/", 1)[-1]

if not database_name.endswith("_test"):
    raise RuntimeError(
        "Refusing to run tests against a non-test database"
    )


test_engine = create_async_engine(
    settings.TEST_DATABASE_URL,
    echo=settings.DB_ECHO,
)

test_session_maker = async_sessionmaker(
    bind=test_engine,
    expire_on_commit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_maker() as session:
        yield session


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncGenerator[None, None]:
    async with test_engine.begin() as connection:
        await connection.execute(
            text(
                """
                TRUNCATE TABLE
                    bookings,
                    holds,
                    seats,
                    events,
                    users
                RESTART IDENTITY CASCADE
                """
            )
        )

    yield

    async with test_engine.begin() as connection:
        await connection.execute(
            text(
                """
                TRUNCATE TABLE
                    bookings,
                    holds,
                    seats,
                    events,
                    users
                RESTART IDENTITY CASCADE
                """
            )
        )


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_session_maker() as session:
        yield session


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
async def regular_user_client(client: AsyncClient) -> AsyncClient:
    register_payload = {
        "name": "Regular User",
        "email": "regular@example.com",
        "password": "StrongPass123",
        "confirm_password": "StrongPass123",
    }

    register_response = await client.post(
        "/api/auth/register",
        json=register_payload,
    )

    assert register_response.status_code == 201

    login_payload = {
        "username": "regular@example.com",
        "password": "StrongPass123",
    }

    login_response = await client.post(
        "/api/auth/login",
        data=login_payload,
    )

    assert login_response.status_code == 200
    assert "access_token" in client.cookies

    return client