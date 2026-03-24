import logging
import math
import random
from datetime import datetime, UTC
from typing import Optional
from collections.abc import Sequence
from fastapi import UploadFile

from app.exceptions import (
    InvalidPageException,
    NotFoundException,
    ForbiddenException,
)

from app.models import Todo as TodoORM
from app.schemas import Tags, TodoSource, SUserInfo, UserRole, Todo as TodoSchema
from app.core import UnitOfWork
from app.services.search_index import build_search_document
from app.services.search_index import enrich_todo_display_list
from app.utils import (
    generate_random_filename,
    load_image,
    delete_image,
    hash_image,
)

logger = logging.getLogger(__name__)

GENERATED_TITLES = [
    "Купить продукты",
    "Сделать домашнее задание",
    "Позвонить маме",
    "Почитать книгу",
    "Сходить в спортзал",
    "Приготовить ужин",
    "Написать отчёт",
    "Изучить Python",
    "Посмотреть лекцию",
    "Починить велосипед",
    "Убраться в комнате",
    "Оплатить счета",
    "Записаться к врачу",
    "Составить план на неделю",
    "Полить цветы",
    "Обновить резюме",
    "Ответить на письма",
    "Настроить Docker",
    "Сделать бэкап данных",
    "Пройти онлайн-курс",
    "Написать тесты",
    "Отрефакторить код",
    "Прочитать документацию",
    "Сходить на прогулку",
    "Проверить почту",
    "Сделать презентацию",
    "Изучить Elasticsearch",
    "Запустить миграции",
    "Обновить зависимости",
    "Написать README",
]

GENERATED_DETAILS = [
    "Не забыть сделать это сегодня",
    "Важная задача, требует внимания",
    "Запланировано на эту неделю",
    "Низкий приоритет, но нужно сделать",
    "Срочно, дедлайн скоро",
    "Обсудить с командой перед выполнением",
    "Требует дополнительных ресурсов",
    "Можно делегировать при необходимости",
    "",
    "",
]


class TodoService:
    @staticmethod
    def _can_view_only_own_todos(user: SUserInfo) -> bool:
        return user.role == UserRole.VIEWER

    @staticmethod
    def _can_delete_any_todo(user: SUserInfo) -> bool:
        return user.role == UserRole.ADMIN

    @staticmethod
    def _build_random_todo_payload() -> tuple[str, str, Tags]:
        title = random.choice(GENERATED_TITLES)
        suffix = random.randint(1, 9999)
        return (
            f"{title} #{suffix}",
            random.choice(GENERATED_DETAILS),
            random.choice(list(Tags)),
        )

    @staticmethod
    async def _sync_todo_to_search_index(
        uow_session: UnitOfWork,
        todo_id: int,
    ) -> None:
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id)

        if not todo:
            return

        document = build_search_document(todo)
        await uow_session.elastic.ensure_index_exists()
        await uow_session.elastic.index_document(todo_id, document)


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
            await self._sync_todo_to_search_index(uow_session, todo.id)
        except Exception as e:
            logger.error("Elastic indexing failed: %s", e)

    async def get_todos(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
        limit: int,
        skip: int,
        created_from: str | None,
        created_to: str | None,
        tag: Tags | None,
    ) -> tuple[Sequence[TodoORM], int, int]:
        created_from = self._parse_data(created_from)
        created_to = self._parse_data(created_to)
        author_id = current_user.id if self._can_view_only_own_todos(current_user) else None

        async with uow_session.start():

            count = await uow_session.todo.get_count_todos(
                created_from=created_from,
                created_to=created_to,
                tag=tag,
                author_id=author_id,
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
                author_id=author_id,
            )

        return enrich_todo_display_list(todos), skip, pages

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

            if todo.author_id != user.id:
                raise ForbiddenException("Вы можете редактировать только свои задачи")

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

                if (
                    await uow_session.todo.get_todos_by_image_path(
                        todo.image_path, todo.id
                    )
                    is None
                ):
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
                todo_id=todo_id,
                values=todo_change.model_dump(exclude={"id"}),
                user_id=user.id,
            )
        try:
            await self._sync_todo_to_search_index(uow_session, todo_id)
        except Exception as e:
            logger.error("Elastic update failed: %s", e)

        return todo

    async def delete(
        self, uow_session: UnitOfWork, todo_id: int, current_user: SUserInfo
    ) -> TodoORM:
        """Удаление todo с проверкой владельца"""
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id=todo_id)
            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")
            if todo.author_id != current_user.id and not self._can_delete_any_todo(current_user):
                raise ForbiddenException("Вы можете удалять только свои задачи")

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
            return todo

    async def generate_random_todos(
        self,
        uow_session: UnitOfWork,
        count: int,
        author_id: int,
    ) -> None:
        for _ in range(count):
            title, details, tag = self._build_random_todo_payload()
            await self.create(
                uow_session=uow_session,
                title=title,
                details=details,
                tag=tag,
                source=TodoSource.generated,
                image=None,
                author_id=author_id,
            )

    async def delete_multiple(
        self, uow_session: UnitOfWork, todo_ids: list[int], current_user: SUserInfo
    ) -> None:
        """Удаление нескольких todo по списку идентификаторов с проверкой прав владельца"""
        async with uow_session.start():
            todos = await uow_session.todo.get_todos_by_ids(todo_ids=todo_ids)
            if not todos:
                raise NotFoundException(f"Todos with id {todo_ids} not found")

            # Проверка прав: только владелец или админ может удалять
            if not self._can_delete_any_todo(current_user):
                not_owned_ids = [
                    todo.id for todo in todos if todo.author_id != current_user.id
                ]
                if not_owned_ids:
                    raise ForbiddenException("Вы можете удалять только свои задачи")

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

    async def delete_all_user_todos(
        self, uow_session: UnitOfWork, current_user: SUserInfo
    ) -> int:
        """
        Удаление всех todo пользователя
        Returns: количество удаленных записей
        """
        async with uow_session.start():
            if self._can_delete_any_todo(current_user):
                user_todos = await uow_session.todo.get_all()
            else:
                user_todos = await uow_session.todo.get_todos_by_author_id(
                    author_id=current_user.id,
                )
            if not user_todos:
                logger.info("No user todos found")
                return 0
            logger.info(
                "Deleting all todos for user %d, count: %d",
                current_user.id,
                len(user_todos),
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

            if self._can_delete_any_todo(current_user):
                await uow_session.todo.delete_all()
            else:
                await uow_session.todo.delete_by_author_id(current_user.id)
            for todo_id in todo_ids:
                try:
                    await uow_session.elastic.delete_todo(todo_id=todo_id)
                except Exception as e:
                    logger.error("Elastic delete failed: %s", e)
            return len(todo_ids)
