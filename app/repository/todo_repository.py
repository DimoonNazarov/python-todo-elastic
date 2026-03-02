from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import distinct
from sqlalchemy import insert
from sqlalchemy import desc
from sqlalchemy import func
from sqlalchemy import update
from sqlalchemy import delete
from sqlalchemy import and_

from app.models import Todo
from app.models import User
from app.schemas import Tags


class TodoRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_count_todos(
        self,
        creation_date_start: datetime = None,
        creation_date_end: datetime = None,
        tag: Tags = None,
    ):
        query = select(func.count()).select_from(Todo)

        if creation_date_start:
            query = query.where(Todo.created_at >= creation_date_start)
        if creation_date_end:
            query = query.where(Todo.created_at <= creation_date_end)
        if tag:
            query = query.where(Todo.tag == tag)

        count_todo = await self._session.execute(query)
        data = count_todo.scalar()
        return data

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

    async def get_todos(
        self,
        limit: int,
        skip: int,
        creation_date_start: datetime = None,
        creation_date_end: datetime = None,
        tag: Tags = None,
    ):

        query = select(Todo).order_by(desc(Todo.id)).offset(skip * limit).limit(limit)

        if creation_date_start:
            query = query.where(Todo.created_at >= creation_date_start)
        if creation_date_end:
            query = query.where(Todo.created_at <= creation_date_end)
        if tag:
            query = query.where(Todo.tag == tag)

        find_todos = await self._session.execute(query)
        data = find_todos.scalars().all()
        return data

    async def get_todos_by_ids(self, todo_ids: list):

        query = select(Todo).where(Todo.id.in_(todo_ids))
        result = await self._session.execute(query)
        return result.scalars().all()

    async def get_all_todos(self):
        find_todos = await self._session.execute(select(Todo).order_by(desc(Todo.id)))
        data = find_todos.scalars().all()
        return data

    async def add_todo(self, data: dict):
        data["created_at"] = datetime.utcnow()

        # Создаем объект Todo
        todo = Todo(**data)

        # Добавляем в сессию
        self._session.add(todo)
        await self._session.commit()
        await self._session.refresh(todo)  # обновляем, чтобы получить ID

        return todo

    async def add_todo_object(self, todo: Todo):
        self._session.add(todo)

    async def get_todo(self, todo_id: int):
        find_todo = await self._session.execute(select(Todo).where(Todo.id == todo_id))
        data = find_todo.scalars().one_or_none()
        return data

    async def update_todo(self, todo_id: int, data: dict):
        if data.get("completed"):
            data["completed_at"] = datetime.utcnow()
        else:
            data["completed_at"] = None
        await self._session.execute(
            update(Todo).where(Todo.id == todo_id).values(**data)
        )

    async def delete_todo(self, todo_id: int):
        await self._session.execute(delete(Todo).where(Todo.id == todo_id))

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

    async def get_todos_by_image_path(self, image_path: str, todo_id: int):
        find_path = await self._session.execute(
            select(Todo).where(and_(Todo.image_path == image_path, Todo.id != todo_id))
        )
        data = find_path.scalars().first()
        return data
