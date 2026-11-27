from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "task_management",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "cancel-overdue-tasks": {
            "task": "app.workers.tasks.cancel_overdue_tasks",
            "schedule": float(settings.overdue_check_interval_seconds),
        }
    },
)
