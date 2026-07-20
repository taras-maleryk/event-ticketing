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
from tests.utils.auth import create_auth_headers_for_user

if settings.TEST_DATABASE_URL is None:
    raise RuntimeError("TEST_DATABASE_URL must be set before running tests")

database_name = settings.TEST_DATABASE_URL.rsplit("/", 1)[-1]

if not database_name.endswith("_test"):
    raise RuntimeError("Refusing to run tests against a non-test database")


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
                    stripe_webhook_events,
                    payment_attempts,
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
                    stripe_webhook_events,
                    payment_attempts,
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
async def regular_user_headers(
    db_session: AsyncSession,
) -> dict[str, str]:
    return await create_auth_headers_for_user(
        db_session,
        name="Regular User",
        email="regular@example.com",
        role="user",
    )


@pytest.fixture
async def another_regular_user_headers(
    db_session: AsyncSession,
) -> dict[str, str]:
    return await create_auth_headers_for_user(
        db_session,
        name="Another Regular User",
        email="another-regular@example.com",
        role="user",
    )


@pytest.fixture
async def organizer_headers(
    db_session: AsyncSession,
) -> dict[str, str]:
    return await create_auth_headers_for_user(
        db_session,
        name="Organizer User",
        email="organizer@example.com",
        role="organizer",
    )


@pytest.fixture
async def another_organizer_headers(
    db_session: AsyncSession,
) -> dict[str, str]:
    return await create_auth_headers_for_user(
        db_session,
        name="Another Organizer",
        email="another-organizer@example.com",
        role="organizer",
    )
