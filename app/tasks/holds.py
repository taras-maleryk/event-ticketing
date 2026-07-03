from app.core.celery_app import celery_app
from app.db.sync_session import sync_session_maker
from sqlalchemy import delete
from app.models.hold import Hold
from datetime import datetime, timezone, timedelta


@celery_app.task(name="app.tasks.holds.cleanup_old_holds")
def cleanup_old_holds() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    stmt = delete(Hold).where(Hold.held_until < cutoff)

    with sync_session_maker.begin() as session:
        session.execute(stmt)

