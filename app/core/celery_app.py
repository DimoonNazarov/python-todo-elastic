"""Настройка Celery для отложенных задач (напоминания о дедлайнах)."""

from datetime import timedelta

from celery import Celery

from app.config import settings

celery_app = Celery(
    "todo_reminders",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.reminders"],
)

celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "check-due-reminders": {
        "task": "reminders.check_due_reminders",
        "schedule": timedelta(seconds=settings.DEADLINE_REMINDER_CHECK_INTERVAL_SECONDS),
    },
}