from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

from app.core.config import settings
from app.core.logging import configure_logging


@setup_logging.connect
def configure_celery_logging(**_: object) -> None:
    configure_logging(
        log_level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT,
    )


celery_app = Celery(
    "event_ticketing",
    broker=settings.REDIS_URL,
    include=["app.tasks.holds"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
    worker_hijack_root_logger=False,
)

celery_app.conf.beat_schedule = {
    "cleanup-old-holds-daily": {
        "task": "app.tasks.holds.cleanup_old_holds",
        "schedule": crontab(hour=3, minute=0),
    },
}
