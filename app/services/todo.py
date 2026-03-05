import os
import math
from datetime import datetime, UTC
from typing import Optional

from collections.abc import Sequence
from fastapi import HTTPException, status, UploadFile
from loguru import logger

from app.exceptions import InvalidPageException, NotFoundException
from app.models import Todo as TodoORM
from app.schemas import Tags, TodoSource
from app.repository import TodoRepository
from app.core import UnitOfWork
from app.utils import (
    generate_random_filename,
    load_image,
    delete_image,
    hash_image,
)


class TodoService:

    @staticmethod
    def _parse_data(date_str: str | None) -> datetime | None:
        """Парсит строку с датой или возвращает None"""
        if not date_str:
            return None
        return datetime.strptime(date_str, "%Y-%m-%d")

    async def create(
        self,
        uow_session: UnitOfWork,
        title: str,
        details: str,
        tag: Tags,
        source: TodoSource,
        image: Optional[UploadFile],
    ) -> None:

        async with uow_session.start():

            image_path = None
            image_hash = None

            if image and image.filename:
                image_hash = await hash_image(image)
                duplicate = await uow_session.todo.is_duplicate_image(image_hash)

                if duplicate:
                    image_path = duplicate.image_path
                else:
                    filename = (
                        generate_random_filename() + "." + image.filename.split(".")[-1]
                    )
                    await load_image(image, filename)
                    image_path = filename

            todo = TodoORM(
                title=title,
                details=details,
                tag=tag,
                source=source,
                created_at=datetime.now(UTC),
                image_path=image_path,
                image_hash=image_hash,
                completed=False,
            )

            await uow_session.todo.add(todo)
        try:
            await uow_session.elastic.index_todo(todo)
        except Exception as e:
            logger.error("Elastic indexing failed: %s", e)

    async def get_todos(
        self,
        uow_session: UnitOfWork,
        limit: int,
        skip: int,
        created_from: str | None,
        created_to: str | None,
        tag: Tags | None,
    ) -> tuple[Sequence[TodoORM], int, int]:
        created_from = self._parse_data(created_from)
        created_to = self._parse_data(created_to)

        async with uow_session.start():

            count = await uow_session.todo.get_count_todos(
                created_from=created_from, created_to=created_to, tag=tag
            )
            pages = math.ceil(count / limit) if count else 1

            if skip > pages:
                raise InvalidPageException(
                    f"Page {skip} does not exist, total pages: {pages}"
                )

            todos = await uow_session.todo.get_many(
                limit=limit,
                skip=skip,
                created_from=created_from,
                created_to=created_to,
                tag=tag,
            )

        return todos, skip, pages

    async def delete(self, uow_session: UnitOfWork, todo_id: int) -> None:
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id=todo_id)

            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")
            logger.info("Deleting todo: %s", todo)

            if (
                await uow_session.todo.get_todos_by_image_path(
                    image_path=todo.image_path, todo_id=todo_id
                )
                is None
            ):
                await delete_image(todo.image_path)

            await uow_session.todo.delete_todo(todo_id=todo_id)

        try:
            await uow_session.elastic.delete_todo(todo_id)
        except Exception as e:
            logger.error("Elastic delete failed: %s", e)
