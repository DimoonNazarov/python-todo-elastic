import os
import math
from datetime import datetime
from typing import Optional

from collections.abc import Sequence
from fastapi import HTTPException, status, UploadFile
from loguru import logger

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
    def __init__(self, todo_repository: TodoRepository):
        self.todo_repository = todo_repository

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
                created_at=datetime.utcnow(),
                image_path=image_path,
                image_hash=image_hash,
                completed=False,
            )

            await uow_session.todo.add(todo)
        try:
            await uow_session.elastic.index_todo(todo)
        except Exception as e:
            logger.error(f"Elastic indexing failed: {e}")


    async def get_todos(
        self,
        uow_session: UnitOfWork,
        limit: int,
        skip: int,
        created_from: str | None,
        created_to: str | None,
        tag: Tags | None
        ) -> tuple[Sequence[TodoORM], int, int]:
        created_from = (datetime.strptime(created_from, "%Y-%m-%d") if created_from else None)
        created_to = (
            datetime.strptime(created_to, "%Y-%m-%d") if created_to else None
        )
        async with uow_session.start():

            count = await uow_session.todo.get_count_todos(
                created_from, created_to, tag
            )
            pages = math.ceil(count / limit)

            if skip > pages:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="No such page"
                )
            if not pages:
                pages = 1

            todos = await uow_session.todo.get_many(
                limit, skip, created_from, created_to, tag
            )

            return todos, skip, pages