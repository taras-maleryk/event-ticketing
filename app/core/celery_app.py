from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "event_ticketing",
    broker=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    timezone="UTC",
    enamte_utc=True,
)