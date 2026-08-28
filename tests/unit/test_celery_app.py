from celery.schedules import crontab

from app.core.celery_app import celery_app


def test_cleanup_old_holds_schedule_is_configured() -> None:
    schedule_entry = celery_app.conf.beat_schedule["cleanup-old-holds-daily"]

    assert schedule_entry["task"] == "app.tasks.holds.cleanup_old_holds"

    schedule = schedule_entry["schedule"]

    assert isinstance(schedule, crontab)
    assert schedule.minute == {0}
    assert schedule.hour == {3}
