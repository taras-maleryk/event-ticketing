from celery import Celery

from app.core.config import settings
from celery.schedules import crontab

celery_app = Celery(
    "event_ticketing",
    broker=settings.REDIS_URL,
    include=[
        "app.tasks.holds"
    ]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-old-holds-daily": {
        "task": "app.tasks.holds.cleanup_old_holds",
        "schedule": crontab(hour=3, minute=0),
    },
}