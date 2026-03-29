from datetime import datetime, timezone
from collections.abc import Sequence
from sqlalchemy import select, delete, update, func, desc, distinct, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Todo


class TodoRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_count_todos(
        self,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        tag: str | None = None,
        author_id: int | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(Todo)

        if created_from:
            stmt = stmt.where(Todo.created_at >= created_from)
        if created_to:
            stmt = stmt.where(Todo.created_at <= created_to)
        if tag:
            stmt = stmt.where(Todo.tag == tag)
        if author_id is not None:
            stmt = stmt.where(Todo.author_id == author_id)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_todo_by_id(self, todo_id: int) -> Todo | None:
        result = await self._session.execute(
            select(Todo)
            .options(
                selectinload(Todo.author),
                selectinload(Todo.updated_by_user),
            )
            .where(Todo.id == todo_id)
        )
        return result.scalar_one_or_none()

    async def get_many(
        self,
        limit: int,
        skip: int,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
        tag: str | None = None,
        author_id: int | None = None,
    ) -> Sequence[Todo]:

        stmt = (
            select(Todo)
            .options(
                selectinload(Todo.author),
                selectinload(Todo.updated_by_user),
            )
            .order_by(desc(Todo.id))
            .offset(skip * limit)
            .limit(limit)
        )

        if created_from:
            stmt = stmt.where(Todo.created_at >= created_from)
        if created_to:
            stmt = stmt.where(Todo.created_at <= created_to)
        if tag:
            stmt = stmt.where(Todo.tag == tag)
        if author_id is not None:
            stmt = stmt.where(Todo.author_id == author_id)

        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_todos_by_ids(self, todo_ids: list[int]) -> Sequence[Todo]:
        result = await self._session.execute(
            select(Todo)
            .options(
                selectinload(Todo.author),
                selectinload(Todo.updated_by_user),
            )
            .where(Todo.id.in_(todo_ids))
        )
        return result.scalars().all()

    async def get_all(self) -> Sequence[Todo]:
        result = await self._session.execute(
            select(Todo)
            .options(
                selectinload(Todo.author),
                selectinload(Todo.updated_by_user),
            )
            .order_by(desc(Todo.id))
        )
        return result.scalars().all()

    async def add(self, todo: Todo) -> None:
        """
        Добавляет ORM-объект в сессию.
        Commit делает UnitOfWork.
        """
        self._session.add(todo)

    async def update(self, todo_id: int, values: dict, user_id: int) -> None:
        values["updated_at"] = datetime.now(timezone.utc)
        values["updated_by"] = user_id
        await self._session.execute(
            update(Todo).where(Todo.id == todo_id).values(**values)
        )

    async def update_summary(
        self,
        todo_id: int,
        spacy_summary: str | None,
        user_id: int,
    ) -> None:
        await self.update(
            todo_id=todo_id,
            values={"spacy_summary": spacy_summary},
            user_id=user_id,
        )

    async def update_llm_summary(
        self,
        todo_id: int,
        llm_summary: str | None,
        user_id: int,
    ) -> None:
        await self.update(
            todo_id=todo_id,
            values={"llm_summary": llm_summary},
            user_id=user_id,
        )

    async def delete_todo(self, todo_id: int):
        await self._session.execute(delete(Todo).where(Todo.id == todo_id))

    async def delete_by_ids(self, ids: list[int]) -> None:
        await self._session.execute(delete(Todo).where(Todo.id.in_(ids)))

    async def delete_all(self) -> None:
        await self._session.execute(delete(Todo))

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
            select(Todo)
            .options(
                selectinload(Todo.author),
                selectinload(Todo.updated_by_user),
            )
            .where(Todo.author_id == author_id)
            .order_by(desc(Todo.id))
        )
        return result.scalars().all()

    async def delete_by_author_id(self, author_id: int) -> None:
        """Удалить все todo пользователя"""
        await self._session.execute(delete(Todo).where(Todo.author_id == author_id))

    async def clear_updated_by_for_user(self, user_id: int) -> None:
        """Очистить ссылки на пользователя в поле updated_by."""
        await self._session.execute(
            update(Todo).where(Todo.updated_by == user_id).values(updated_by=None)
        )

    async def get_duplicate_groups(self, author_id: int | None = None) -> list[dict]:
        """Возвращает группы todo с одинаковым details_hash (≥2 в группе)."""
        stmt = (
            select(Todo.details_hash, func.count(Todo.id).label("cnt"))
            .where(Todo.details_hash.isnot(None))
            .group_by(Todo.details_hash)
            .having(func.count(Todo.id) > 1)
        )
        if author_id is not None:
            stmt = stmt.where(Todo.author_id == author_id)

        rows = (await self._session.execute(stmt)).all()

        groups = []
        for row in rows:
            todos_stmt = (
                select(Todo)
                .options(selectinload(Todo.author), selectinload(Todo.updated_by_user))
                .where(Todo.details_hash == row.details_hash)
                .order_by(Todo.id)
            )
            if author_id is not None:
                todos_stmt = todos_stmt.where(Todo.author_id == author_id)
            todos = (await self._session.execute(todos_stmt)).scalars().all()
            groups.append({"hash": row.details_hash, "todos": todos})

        return groups

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
