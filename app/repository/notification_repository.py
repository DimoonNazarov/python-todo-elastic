from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_unread_for_user(self, user_id: int) -> Sequence[Notification]:
        from app.models.comment import Comment

        result = await self._session.execute(
            select(Notification)
            .options(
                selectinload(Notification.todo),
                selectinload(Notification.comment).selectinload(Comment.author),
            )
            .where(Notification.recipient_id == user_id, Notification.is_read == False)  # noqa: E712
            .order_by(Notification.created_at.desc())
        )
        return result.scalars().all()

    async def get_all_for_user(self, user_id: int, limit: int = 30) -> Sequence[Notification]:
        from app.models.comment import Comment

        result = await self._session.execute(
            select(Notification)
            .options(
                selectinload(Notification.todo),
                selectinload(Notification.comment).selectinload(Comment.author),
            )
            .where(Notification.recipient_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()

    async def add(self, notification: Notification) -> None:
        self._session.add(notification)

    async def mark_read(self, notification_id: int, user_id: int) -> None:
        await self._session.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.recipient_id == user_id)
            .values(is_read=True)
        )

    async def mark_all_read(self, user_id: int) -> None:
        await self._session.execute(
            update(Notification)
            .where(Notification.recipient_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )

    async def count_unread(self, user_id: int) -> int:
        result = await self._session.execute(
            select(Notification)
            .where(Notification.recipient_id == user_id, Notification.is_read == False)  # noqa: E712
        )
        return len(result.scalars().all())
