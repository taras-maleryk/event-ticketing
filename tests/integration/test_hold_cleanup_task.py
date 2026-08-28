from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.hold import Hold
from app.tasks import holds as holds_tasks
from tests.utils.holds import create_hold_for_seat
from tests.utils.seats import create_event_with_seats


async def test_cleanup_old_holds_deletes_only_stale_records(
    client: AsyncClient,
    organizer_headers: dict[str, str],
    regular_user_headers: dict[str, str],
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, created_seats = await create_event_with_seats(
        client,
        organizer_headers,
    )

    stale_hold_data = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[0]["id"],
    )
    recent_hold_data = await create_hold_for_seat(
        client,
        regular_user_headers,
        created_seats[1]["id"],
    )

    stale_hold = await db_session.get(Hold, stale_hold_data["id"])
    recent_hold = await db_session.get(Hold, recent_hold_data["id"])

    assert stale_hold is not None
    assert recent_hold is not None

    now = datetime.now(UTC)
    stale_hold.held_from = now - timedelta(days=9)
    stale_hold.held_until = now - timedelta(days=8)
    recent_hold.held_from = now - timedelta(days=7)
    recent_hold.held_until = now - timedelta(days=6)
    await db_session.commit()

    assert settings.TEST_DATABASE_URL is not None

    sync_test_database_url = settings.TEST_DATABASE_URL.replace(
        "postgresql+asyncpg://",
        "postgresql+psycopg://",
        1,
    )
    test_sync_engine = create_engine(sync_test_database_url)
    test_sync_session_maker = sessionmaker(
        bind=test_sync_engine,
        expire_on_commit=False,
    )
    monkeypatch.setattr(
        holds_tasks,
        "sync_session_maker",
        test_sync_session_maker,
    )

    try:
        holds_tasks.cleanup_old_holds.run()
    finally:
        test_sync_engine.dispose()

    db_session.expire_all()

    remaining_hold_ids = set(
        await db_session.scalars(
            select(Hold.id).where(
                Hold.id.in_([stale_hold_data["id"], recent_hold_data["id"]])
            )
        )
    )

    assert stale_hold_data["id"] not in remaining_hold_ids
    assert recent_hold_data["id"] in remaining_hold_ids
