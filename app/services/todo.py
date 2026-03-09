import logging
import math
from datetime import datetime, UTC
from typing import Optional
from collections.abc import Sequence
from fastapi import UploadFile

from app.exceptions import (
    InvalidPageException,
    NotFoundException,
    OperationNotPermittedException,
    ForbiddenException
)

from app.models import Todo as TodoORM
from app.schemas import Tags, TodoSource, SUserInfo, UserRole, Todo as TodoSchema
from app.core import UnitOfWork
from app.utils import (
    generate_random_filename,
    load_image,
    delete_image,
    hash_image,
)


logger = logging.getLogger(__name__)

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
        author_id: int,
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
                author_id=author_id,
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

    async def update(
        self,
        uow_session: UnitOfWork,
        user: SUserInfo,
        todo_id: int,
        title: str | None,
        details: str | None,
        completed: bool,
        tag: Tags | None,
        created_at: datetime | None,
        image_path: str | None,
        existing_image: str | None,
        image: UploadFile | None,
    ) -> TodoORM:
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id)

            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")

            if todo.author_id != user.id and user.role != UserRole.ADMIN:
                raise OperationNotPermittedException("Operation not permitted")

            if image and image.filename:
                random_filename = (
                    generate_random_filename() + "." + image.filename.split(".")[-1]
                )
                image_hash = await hash_image(image)
                duplicate_image_path = await uow_session.todo.is_duplicate_image(
                    image_hash
                )

                if (
                    await uow_session.todo.get_todos_by_image_path(
                        todo.image_path, todo.id
                    )
                    is None
                ):
                    await delete_image(todo.image_path)

                if duplicate_image_path:
                    logger.info("Duplicate image detected.")
                    todo_change = TodoSchema(
                        title=title,
                        details=details,
                        completed=completed,
                        tag=tag,
                        created_at=created_at,
                        image_path=duplicate_image_path,
                        image_hash=image_hash,
                    )
                else:
                    await load_image(image, random_filename)
                    todo_change = TodoSchema(
                        title=title,
                        details=details,
                        completed=completed,
                        tag=tag,
                        created_at=created_at,
                        image_path=random_filename,
                        image_hash=image_hash,
                    )
            elif existing_image:
            # Берём image_hash напрямую из текущего todo если image_path совпадает
                if todo.image_path == existing_image:
                    image_hash = todo.image_hash
                else:
                    # Ищем среди других todo
                    data = await uow_session.todo.get_todo_by_image_path(existing_image)
                    if data is None:
                        raise NotFoundException(f"Image '{existing_image}' not found")
                    image_hash = data.image_hash

                if await uow_session.todo.get_todos_by_image_path(todo.image_path, todo.id) is None:
                    await delete_image(todo.image_path)

                todo_change = TodoSchema(
                    title=title,
                    details=details,
                    completed=completed,
                    tag=tag,
                    created_at=created_at,
                    image_path=existing_image,
                    image_hash=image_hash,
                )
            else:
                todo_change = TodoSchema(
                    title=title,
                    details=details,
                    completed=completed,
                    tag=tag,
                    created_at=created_at,
                    image_path=image_path,
                    image_hash=todo.image_hash,
                )

            if todo_change.completed:
                todo_change.completed_at = datetime.now(UTC)

            todo_change.source = TodoSource(todo.source)

            await uow_session.todo.update(
                todo_id=todo_id, values=todo_change.model_dump(exclude={"id"})
            )
        try:
            await uow_session.elastic.update_todo(todo_id, todo)
        except Exception as e:
            logger.error("Elastic update failed: %s", e)

        return todo

    async def delete(self, uow_session: UnitOfWork, todo_id: int, user_id: int) -> None:
        """Удаление todo с проверкой владельца"""
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id=todo_id)
            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")
            if todo.author_id != user_id:
                raise ForbiddenException("You can only delete your own todos")

            logger.info("Deleting todo: %s", todo)
            if (
                await uow_session.todo.get_todos_by_image_path(
                    image_path=todo.image_path,
                    todo_id=todo_id,
                )
                is None
            ):
                await delete_image(todo.image_path)
            await uow_session.todo.delete_todo(todo_id)
            try:
                await uow_session.elastic.delete_todo(todo_id)
            except Exception as e:
                logger.error("Elastic delete failed: %s", e)

    async def delete_multiple(
        self, uow_session: UnitOfWork, todo_ids: list[int], user_id: int
    ) -> None:
        """Удаление нескольких todo по списку идентификаторов с проверкой прав владельца"""
        async with uow_session.start():
            todos = await uow_session.todo.get_todos_by_ids(todo_ids=todo_ids)
            if not todos:
                raise NotFoundException(f"Todos with id {todo_ids} not found")

            not_owned_ids = [todo.id for todo in todos if todo.author_id != user_id]
            if not_owned_ids:
                raise ForbiddenException("You can only delete your own todos")

            image_paths_to_delete = []
            for todo in todos:
                if (
                    todo.image_path
                    and await uow_session.todo.get_todos_by_image_path(
                        image_path=todo.image_path, todo_id=todo.id
                    )
                    is None
                ):
                    image_paths_to_delete.append(todo.image_path)

            for image_path in image_paths_to_delete:
                await delete_image(image_path)

            await uow_session.todo.delete_by_ids(todo_ids)

            for todo_id in todo_ids:
                try:
                    await uow_session.elastic.delete_todo(todo_id=todo_id)
                except Exception as e:
                    logger.error("Elastic delete failed: %s", e)

    async def delete_all_user_todos(self, uow_session: UnitOfWork, user_id: int) -> int:
        """
        Удаление всех todo пользователя
        Returns: количество удаленных записей
        """
        async with uow_session.start():
            user_todos = await uow_session.todo.get_todos_by_author_id(
                author_id=user_id
            )
            if not user_todos:
                logger.info("No user todos found")
                return 0
            logger.info(
                "Deleting all todos for user %d, count: %d", user_id, len(user_todos)
            )

            todo_ids = [todo.id for todo in user_todos]

            image_paths_to_delete = []
            for todo in user_todos:
                if todo.image_path:
                    # Проверяем, используется ли изображение другими todo (любых пользователей)
                    is_image_used_elsewhere = (
                        await uow_session.todo.is_image_used_by_other_todos(
                            image_path=todo.image_path, exclude_todo_id=todo.id
                        )
                    )
                    if not is_image_used_elsewhere:
                        image_paths_to_delete.append(todo.image_path)

            # Удаляем изображения
            for image_path in set(
                image_paths_to_delete
            ):  # используем set для уникальности
                try:
                    await delete_image(image_path)
                except Exception as e:
                    logger.error(f"Failed to delete image {image_path}: {e}")

            await uow_session.todo.delete_by_author_id(user_id)
            for todo_id in todo_ids:
                try:
                    await uow_session.elastic.delete_todo(todo_id=todo_id)
                except Exception as e:
                    logger.error("Elastic delete failed: %s", e)
            return len(todo_ids)
