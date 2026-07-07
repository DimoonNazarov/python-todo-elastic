import logging
from datetime import UTC, datetime, timedelta

from app.core import UnitOfWork
from app.models import Notification

logger = logging.getLogger(__name__)


class ReminderService:
    """Находит задачи с приближающимся дедлайном и создаёт напоминания."""

    async def notify_due_soon(self, uow_session: UnitOfWork, before_minutes: int) -> list[dict]:
        """
        Создаёт Notification(type="deadline") для задач, дедлайн которых наступит
        в течение `before_minutes`, и помечает их как уведомлённые.

        Возвращает список payload'ов для рассылки по WebSocket.
        """
        now = datetime.now(UTC)
        threshold = now + timedelta(minutes=before_minutes)

        payloads: list[dict] = []
        async with uow_session.start():
            todos = await uow_session.todo.get_todos_due_soon(now, threshold)
            for todo in todos:
                notification = Notification(
                    recipient_id=todo.author_id,
                    todo_id=todo.id,
                    comment_id=None,
                    type="deadline",
                )
                await uow_session.notification.add(notification)
                await uow_session.todo.mark_reminder_sent(todo.id)
                payloads.append(
                    {
                        "recipient_id": todo.author_id,
                        "todo_id": todo.id,
                        "todo_title": todo.title,
                        "due_at": todo.due_at.isoformat() if todo.due_at else None,
                    }
                )

        if payloads:
            logger.info("Отправлено напоминаний о дедлайне: %s", len(payloads))
        return payloads