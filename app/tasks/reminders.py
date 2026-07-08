"""Celery-задачи. Сами таски синхронные (так требует Celery), но вся бизнес-логика
async (SQLAlchemy async engine), поэтому она оборачивается в asyncio.run()."""

import asyncio
import logging

from app.config import settings
from app.core.celery_app import celery_app
from app.core.database import async_session_maker, engine
from app.core.uow import UnitOfWork
from app.services.notification_bus import publish_notification_sync
from app.services.reminder import ReminderService

logger = logging.getLogger(__name__)


@celery_app.task(name="reminders.check_due_reminders")
def check_due_reminders() -> int:
    """Периодическая задача (Celery beat): находит задачи с приближающимся
    дедлайном, создаёт уведомления и публикует их в Redis для WebSocket-рассылки."""
    payloads = asyncio.run(_check_due_reminders())
    for payload in payloads:
        publish_notification_sync(payload)
    return len(payloads)


async def _check_due_reminders() -> list[dict]:
    try:
        # es_client не нужен — напоминания не трогают Elasticsearch
        uow_session = UnitOfWork(async_session_maker, es_client=None)
        return await ReminderService().notify_due_soon(
            uow_session,
            before_minutes=settings.DEADLINE_REMINDER_BEFORE_MINUTES,
        )
    finally:
        # asyncio.run() открывает новый event loop на каждый запуск таска,
        # а пул соединений asyncpg живёт на уровне модуля и переживает между
        # запусками. Соединение, отданное asyncpg в предыдущем loop'е,
        # нельзя переиспользовать в новом — отсюда "attached to a different
        # loop". Поэтому пул полностью сбрасывается в конце каждого запуска,
        # пока текущий loop ещё жив.
        await engine.dispose()