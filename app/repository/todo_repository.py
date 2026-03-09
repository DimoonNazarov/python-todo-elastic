from datetime import datetime
from collections.abc import Sequence
from sqlalchemy import select, delete, update, func, desc, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.util import deprecated

from app.models import Todo
from app.models import User
from app.schemas import Tags


class TodoRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_count_todos(
        self,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        tag: Tags | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Todo)

        if created_from:
            stmt = stmt.where(Todo.created_at >= created_from)
        if created_to:
            stmt = stmt.where(Todo.created_at <= created_to)
        if tag:
            stmt = stmt.where(Todo.tag == tag)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_todo_by_id(self, todo_id: int) -> Todo | None:
        result = await self._session.execute(select(Todo).where(Todo.id == todo_id))
        return result.scalar_one_or_none()

    async def get_many(
        self,
        limit: int,
        skip: int,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        tag: Tags = None,
    ) -> Sequence[Todo]:

        stmt = select(Todo).order_by(desc(Todo.id)).offset(skip * limit).limit(limit)

        if created_from:
            stmt = stmt.where(Todo.created_at >= created_from)
        if created_to:
            stmt = stmt.where(Todo.created_at <= created_to)
        if tag:
            stmt = stmt.where(Todo.tag == tag)

        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_todos_by_ids(self, todo_ids: list[int]) -> Sequence[Todo]:
        result = await self._session.execute(select(Todo).where(Todo.id.in_(todo_ids)))
        return result.scalars().all()

    async def get_all(self) -> Sequence[Todo]:
        result = await self._session.execute(select(Todo).order_by(desc(Todo.id)))
        return result.scalars().all()

    async def add(self, todo: Todo) -> None:
        """
        Добавляет ORM-объект в сессию.
        Commit делает UnitOfWork.
        """
        self._session.add(todo)

    async def update(self, todo_id: int, values: dict) -> None:
        await self._session.execute(
            update(Todo).where(Todo.id == todo_id).values(**values)
        )

    async def delete_todo(self, todo_id: int):
        await self._session.execute(delete(Todo).where(Todo.id == todo_id))

    async def delete_by_ids(self, ids: list[int]) -> None:
        await self._session.execute(delete(Todo).where(Todo.id.in_(ids)))

    @deprecated
    async def delete_todos(self, skip: int, limit: int, start: int, end: int):
        if not start and not end:
            await self._session.execute(delete(Todo))
        else:
            subquery = (
                select(Todo.id)
                .order_by(desc(Todo.id))
                .offset(skip * limit + (start - 1))
                .limit(end - start + 1)
            )

            await self._session.execute(delete(Todo).where(Todo.id.in_(subquery)))

    async def get_all_image_paths(self):
        find_images = await self._session.execute(
            select(distinct(Todo.image_path)).where(Todo.image_path.isnot(None))
        )
        data = find_images.scalars().all()
        return data

    async def is_duplicate_image(self, image_hash: str):
        find_hash = await self._session.execute(
            select(Todo).where(Todo.image_hash == image_hash)
        )
        data = find_hash.scalars().first()
        return data.image_path if data else None

    async def get_todo_by_image_path(self, image_path: str) -> Todo | None:
        result = await self._session.execute(
            select(Todo).where(Todo.image_path == image_path)
        )
        return result.scalars().first()

    async def get_todos_by_image_path(self, image_path: str, todo_id: int):
        find_path = await self._session.execute(
            select(Todo).where(and_(Todo.image_path == image_path, Todo.id != todo_id))
        )
        data = find_path.scalars().first()
        return data

    async def get_todos_by_author_id(self, author_id: int):
        """Получить все todd пользоователя"""
        result = await self._session.execute(
            select(Todo).where(Todo.author_id == author_id).order_by(desc(Todo.id))
        )
        return result.scalars().all()

    async def delete_by_author_id(self, author_id: int) -> None:
        """Удалить все todo пользователя"""
        await self._session.execute(delete(Todo).where(Todo.author_id == author_id))

    async def is_image_used_by_other_todos(
        self, image_path: str, exclude_todo_id: int
    ) -> bool:
        """
        Проверить, используется ли изображение другими todo
        (независимо от владельца)
        """
        result = await self._session.execute(
            select(func.count(Todo.id)).where(
                and_(Todo.image_path == image_path, Todo.id != exclude_todo_id)
            )
        )
        count = result.scalar_one()
        return count > 0
