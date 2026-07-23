from datetime import UTC, datetime, timedelta

import structlog
from celery import Task
from sqlalchemy import delete

from app.core.celery_app import celery_app
from app.db.sync_session import sync_session_maker
from app.models.hold import Hold

logger = structlog.get_logger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.holds.cleanup_old_holds",
)
def cleanup_old_holds(self: Task) -> None:
    cutoff = datetime.now(UTC) - timedelta(days=7)

    task_logger = logger.bind(
        task_id=self.request.id,
        task_name=self.name,
    )

    statement = delete(Hold).where(Hold.held_until < cutoff).returning(Hold.id)

    try:
        with sync_session_maker.begin() as session:
            result = session.execute(statement)
            deleted_count = len(result.scalars().all())
    except Exception:
        task_logger.exception(
            "old_holds_cleanup_failed",
            cutoff=cutoff.isoformat(),
        )
        raise

    task_logger.info(
        "old_holds_cleanup_completed",
        cutoff=cutoff.isoformat(),
        deleted_count=deleted_count,
    )
