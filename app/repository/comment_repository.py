from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Comment


class CommentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_todo_id(self, todo_id: int) -> Sequence[Comment]:
        result = await self._session.execute(
            select(Comment)
            .options(
                selectinload(Comment.author),
                selectinload(Comment.replies).selectinload(Comment.author),
            )
            .where(Comment.todo_id == todo_id, Comment.parent_id.is_(None))
            .order_by(Comment.created_at)
        )
        return result.scalars().all()

    async def get_by_id(self, comment_id: int) -> Comment | None:
        result = await self._session.execute(
            select(Comment)
            .options(selectinload(Comment.author))
            .where(Comment.id == comment_id)
        )
        return result.scalar_one_or_none()

    async def add(self, comment: Comment) -> None:
        self._session.add(comment)

    async def soft_delete(self, comment_id: int) -> None:
        await self._session.execute(
            update(Comment)
            .where(Comment.id == comment_id)
            .values(is_deleted=True, content="[удалено]", updated_at=datetime.now(timezone.utc))
        )
