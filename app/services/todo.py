import logging
import math
import random
from collections.abc import Sequence
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import UploadFile

from app.core import UnitOfWork
from app.exceptions import (
    ForbiddenException,
    InvalidTodoDataException,
    InvalidPageException,
    LLMRequestException,
    NotFoundException,
)
from app.models import Todo as TodoORM
from app.schemas import SUserInfo, Tags, Todo as TodoSchema, TodoSource, UserRole
from app.services.openrouter import OpenRouterService
from app.services.search_index import build_search_document
from app.services.search_index import enrich_todo_display_list
from app.services.search_index import merge_search_hits_with_todos
from app.services.clustering import cluster_todos
from app.services.summary import build_spacy_summary
from app.utils import (
    delete_image,
    generate_random_filename,
    hash_image,
    hash_text,
    load_image,
    export_todos,
)

logger = logging.getLogger(__name__)
TODO_DETAILS_MAX_LENGTH = 1000

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
    def __init__(self, openrouter_service: OpenRouterService) -> None:
        self._openrouter_service = openrouter_service

    @staticmethod
    def _can_view_only_own_todos(user: SUserInfo) -> bool:
        return user.role == UserRole.VIEWER

    @staticmethod
    def _can_delete_any_todo(user: SUserInfo) -> bool:
        return user.role == UserRole.ADMIN

    @staticmethod
    def _resolve_author_id(user: SUserInfo) -> int | None:
        return user.id if user.role == UserRole.VIEWER else None

    @staticmethod
    def _normalize_llm_text(text: str, fallback: str | None = None) -> str:
        normalized = text.strip().strip("\"'«»")
        normalized = " ".join(normalized.split())
        return normalized or (fallback or "")

    @staticmethod
    def _normalize_details(details: str | None) -> str | None:
        if details is None:
            return None
        return details.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _ensure_llm_source_text(details: str | None) -> str:
        if not details or not details.strip():
            raise LLMRequestException("Для выполнения операции нужно заполнить описание заметки.")
        return details.strip()

    @staticmethod
    def _validate_details(details: str | None) -> None:
        if details is None:
            return
        if len(details) > TODO_DETAILS_MAX_LENGTH:
            raise InvalidTodoDataException(
                "Описание заметки не может превышать 1000 символов."
            )

    @staticmethod
    def _build_cluster_context(cluster_todos_data: Sequence[TodoORM]) -> str:
        lines = []
        for todo in cluster_todos_data[:8]:
            tag = todo.tag or "без тега"
            lines.append(
                f"- Заголовок: {todo.title or 'без заголовка'}; "
                f"Тег: {tag}; "
                f"Описание: {(todo.details or '').strip()[:180]}"
            )
        return "\n".join(lines) if lines else "Похожих заметок в кластере не найдено."

    def _get_cluster_for_draft(
        self,
        todos: Sequence[TodoORM],
        title: str | None,
        details: str,
    ) -> list[TodoORM]:
        draft = SimpleNamespace(id=-1, title=title or "", details=details)
        clusters = cluster_todos([*todos, draft], n_clusters=3)
        for cluster in clusters:
            cluster_items = cluster["todos"]
            if any(getattr(item, "id", None) == -1 for item in cluster_items):
                return [
                    item for item in cluster_items if getattr(item, "id", None) != -1
                ]
        return list(todos[:5])

    @staticmethod
    async def _resolve_image(
        uow_session: UnitOfWork,
        todo: TodoORM,
        image: UploadFile | None,
        existing_image: str | None,
        image_path: str | None,
    ) -> tuple[str | None, str | None]:
        """Возвращает (image_path, image_hash) для обновления todo."""
        if image and image.filename:
            image_hash = await hash_image(image)
            duplicate = await uow_session.todo.is_duplicate_image(image_hash)
            if (
                await uow_session.todo.get_todos_by_image_path(todo.image_path, todo.id)
                is None
            ):
                await delete_image(todo.image_path)
            if duplicate:
                logger.info("Duplicate image detected.")
                return duplicate.image_path, image_hash
            random_filename = (
                generate_random_filename() + "." + image.filename.split(".")[-1]
            )
            await load_image(image, random_filename)
            return random_filename, image_hash

        if existing_image:
            if todo.image_path == existing_image:
                image_hash = todo.image_hash
            else:
                data = await uow_session.todo.get_todo_by_image_path(existing_image)
                if data is None:
                    raise NotFoundException(f"Image '{existing_image}' not found")
                image_hash = data.image_hash
            if (
                await uow_session.todo.get_todos_by_image_path(todo.image_path, todo.id)
                is None
            ):
                await delete_image(todo.image_path)
            return existing_image, image_hash

        return image_path, todo.image_hash

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

    @staticmethod
    async def _get_search_todos_from_hits(
        uow_session: UnitOfWork,
        hits: list[dict],
    ) -> list[dict]:
        todo_ids = [hit["todo_id"] for hit in hits]
        if not todo_ids:
            return []

        async with uow_session.start():
            todos = await uow_session.todo.get_todos_by_ids(todo_ids)
        return merge_search_hits_with_todos(hits, todos)

    async def create(
        self,
        uow_session: UnitOfWork,
        title: str,
        details: str,
        tag: str | None,
        source: TodoSource,
        image: UploadFile | None,
        author_id: int,
        due_at: datetime | None = None,
    ) -> None:
        details = self._normalize_details(details)
        self._validate_details(details)

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
                due_at=due_at,
                image_path=image_path,
                image_hash=image_hash,
                details_hash=hash_text(details),
                completed=False,
                author_id=author_id,
            )

            await uow_session.todo.add(todo)
        try:
            await self._sync_todo_to_search_index(uow_session, todo.id)
        except Exception as e:
            logger.error("Elastic indexing failed: %s", e)

    async def get_todos_page(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
        limit: int,
        skip: int,
        created_from: str | None,
        created_to: str | None,
        tag: str | None,
        query: str | None,
        search_tag: str | None,
        search_date_from: str | None,
    ) -> dict:
        author_id = self._resolve_author_id(current_user)

        if query:
            logger.debug("Поиск по запросу: %s", query)
            hits = await uow_session.elastic.search_todos(
                query_text=query,
                tag=tag,
                limit=limit,
                skip=skip,
                author_id=author_id,
            )
            todos = await self._get_search_todos_from_hits(uow_session, hits)
            return {
                "todos": todos,
                "skip": 0,
                "pages": 1,
                "search_mode": "query",
                "subtitle": "Результаты поиска по запросу: %s" % query,
            }

        if search_tag:
            tag_display = search_tag.capitalize()

            logger.debug("Поиск по тегу: %s", tag_display)
            todos = enrich_todo_display_list(
                await uow_session.elastic.search_by_tag(
                    search_tag.capitalize(),
                    author_id=author_id,
                )
            )
            return {
                "todos": todos,
                "skip": 0,
                "pages": 1,
                "search_mode": "tag",
                "subtitle": "Результаты поиска по тегу: %s" % tag_display,
            }

        if search_date_from:
            date_from_dt = datetime.fromisoformat(search_date_from)
            logger.debug("Поиск по дате от: %s", date_from_dt)
            todos = enrich_todo_display_list(
                await uow_session.elastic.search_by_date(
                    date_from_dt.isoformat(), author_id=author_id
                )
            )
            return {
                "todos": todos,
                "skip": 0,
                "pages": 1,
                "search_mode": "date",
                "subtitle": "Результаты поиска после %s"
                % date_from_dt.strftime("%d.%m.%Y %H:%M"),
            }

        todos, skip, pages = await self.get_todos(
            uow_session=uow_session,
            current_user=current_user,
            limit=limit,
            skip=skip,
            created_from=created_from,
            created_to=created_to,
            tag=tag,
        )

        return {
            "todos": todos,
            "skip": skip,
            "pages": pages,
            "search_mode": None,
            "subtitle": None,
        }

    async def get_todos(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
        limit: int,
        skip: int,
        created_from: str | None,
        created_to: str | None,
        tag: str | None,
    ) -> tuple[Sequence[TodoORM], int, int]:
        created_from = self._parse_data(created_from)
        created_to = self._parse_data(created_to)
        author_id = self._resolve_author_id(current_user)

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
        tag: str | None,
        created_at: datetime | None,
        image_path: str | None,
        existing_image: str | None,
        image: UploadFile | None,
    ) -> TodoORM:
        details = self._normalize_details(details)

        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id)

            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")

            if todo.author_id != user.id:
                raise ForbiddenException("Вы можете редактировать только свои задачи")

            if details != todo.details:
                self._validate_details(details)

            resolved_image_path, resolved_image_hash = await self._resolve_image(
                uow_session, todo, image, existing_image, image_path
            )
            todo_change = TodoSchema(
                title=title,
                details=details,
                completed=completed,
                tag=tag,
                created_at=created_at,
                image_path=resolved_image_path,
                image_hash=resolved_image_hash,
                details_hash=hash_text(details) if details else todo.details_hash,
                spacy_summary=todo.spacy_summary,
                llm_summary=todo.llm_summary,
            )

            if todo_change.completed:
                todo_change.completed_at = datetime.now(UTC)

            todo_change.source = TodoSource(todo.source)
            if title != todo.title or details != todo.details:
                todo_change.spacy_summary = None
                todo_change.llm_summary = None

            await uow_session.todo.update(
                todo_id=todo_id,
                values=todo_change.model_dump(exclude={"id"}),
                user_id=user.id,
            )
            updated_todo = await uow_session.todo.get_todo_by_id(todo_id)
        try:
            await self._sync_todo_to_search_index(uow_session, todo_id)
        except Exception as e:
            logger.error("Elastic update failed: %s", e)

        return updated_todo

    async def summarize_with_spacy(
        self,
        uow_session: UnitOfWork,
        todo_id: int,
        user: SUserInfo,
    ) -> str:
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id)

            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")

            if todo.author_id != user.id:
                raise ForbiddenException("Вы можете реферировать только свои задачи")

            summary = build_spacy_summary(todo.title, todo.details)
            await uow_session.todo.update_summary(
                todo_id=todo_id,
                spacy_summary=summary,
                user_id=user.id,
            )
            return summary

    async def summarize_with_llm(
        self,
        uow_session: UnitOfWork,
        todo_id: int,
        user: SUserInfo,
    ) -> str:
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id)
            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")
            if todo.author_id != user.id:
                raise ForbiddenException("Вы можете реферировать только свои задачи")

            summary = await self._openrouter_service.generate_summary(todo.title, todo.details)
            summary = self._normalize_llm_text(summary)
            await uow_session.todo.update_llm_summary(
                todo_id=todo_id,
                llm_summary=summary,
                user_id=user.id,
            )
            return summary

    async def generate_title_with_llm(
        self,
        details: str | None,
        current_title: str | None = None,
    ) -> str:
        resolved_details = self._ensure_llm_source_text(details)
        title = await self._openrouter_service.generate_title(
            details=resolved_details,
            current_title=current_title,
        )
        return self._normalize_llm_text(title, fallback=current_title)

    async def suggest_tag_with_llm(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
        title: str | None,
        details: str | None,
    ) -> dict:
        resolved_details = self._ensure_llm_source_text(details)
        author_id = self._resolve_author_id(current_user)

        async with uow_session.start():
            todos = await uow_session.todo.get_many(
                limit=1000,
                skip=0,
                author_id=author_id,
            )
            existing_tags = await uow_session.elastic.get_all_tags()

        cluster_items = self._get_cluster_for_draft(todos, title, resolved_details)
        cluster_context = self._build_cluster_context(cluster_items)
        suggested_tag = await self._openrouter_service.suggest_tag(
            title=title,
            details=resolved_details,
            cluster_context=cluster_context,
            existing_tags=existing_tags,
        )
        return {
            "tag": self._normalize_llm_text(suggested_tag),
            "cluster_size": len(cluster_items),
        }

    async def get_clusters(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
        n_clusters: int = 3,
    ) -> list[dict]:
        """Кластеризует заметки по содержимому через TF-IDF + KMeans."""
        author_id = self._resolve_author_id(current_user)
        async with uow_session.start():
            todos = await uow_session.todo.get_many(
                limit=1000,
                skip=0,
                author_id=author_id,
            )
        return cluster_todos(todos, n_clusters=n_clusters)

    async def get_duplicates(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
    ) -> list[dict]:
        """Возвращает группы дублирующихся заметок по хешу описания."""
        author_id = self._resolve_author_id(current_user)
        async with uow_session.start():
            return await uow_session.todo.get_duplicate_groups(author_id=author_id)

    async def get_todo_for_edit(
        self,
        uow_session: UnitOfWork,
        todo_id: int,
        user: SUserInfo,
    ) -> tuple[TodoORM, list]:
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id)
            if not todo:
                raise NotFoundException(f"Not found todo by this id: {todo_id}")

            images = await uow_session.todo.get_all_image_paths()

            if todo.author_id != user.id:
                raise ForbiddenException("Вы можете редактировать только свои задачи")

        return todo, images

    async def delete(
        self, uow_session: UnitOfWork, todo_id: int, current_user: SUserInfo
    ) -> TodoORM:
        """Удаление todo с проверкой владельца"""
        async with uow_session.start():
            todo = await uow_session.todo.get_todo_by_id(todo_id=todo_id)
            if not todo:
                raise NotFoundException(f"Todo with id {todo_id} not found")
            if todo.author_id != current_user.id and not self._can_delete_any_todo(
                current_user
            ):
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
        is_admin = self._can_delete_any_todo(current_user)
        async with uow_session.start():
            if is_admin:
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

            for image_path in set(image_paths_to_delete):
                try:
                    await delete_image(image_path)
                except Exception as e:
                    logger.error("Failed to delete image %s: %s", image_path, e)
            if is_admin:
                await uow_session.todo.delete_all()
            else:
                await uow_session.todo.delete_by_author_id(current_user.id)
            for todo_id in todo_ids:
                try:
                    await uow_session.elastic.delete_todo(todo_id=todo_id)
                except Exception as e:
                    logger.error("Elastic delete failed: %s", e)
            return len(todo_ids)

    async def get_notes_per_day(
        self, uow_session: UnitOfWork, current_user: SUserInfo, days: int, interval: str
    ) -> dict:
        """Возвращает данные для графика активности пользователей по дням."""
        author_id = self._resolve_author_id(current_user)

        # Получаем данные из Elasticsearch
        data = await uow_session.elastic.get_notes_per_day_by_user(
            days,
            author_id=author_id,
            interval=interval,
        )

        if not data:
            return {"dates": [], "series": [], "total": 0, "users_count": 0}

        # Извлекаем даты и ID пользователей
        dates = [item["date"] for item in data]
        user_ids = sorted(
            {bucket["author_id"] for item in data for bucket in item["users"]}
        )

        # Загружаем информацию о пользователях
        async with uow_session.start():
            users = await uow_session.auth.get_users_by_ids(user_ids)
        users_by_id = {user.id: user for user in users}

        # Формируем данные для серий графика
        series = []
        for user_id in user_ids:
            user = users_by_id.get(user_id)
            label = user.email if user else f"Пользователь #{user_id}"
            counts = []
            for item in data:
                count_map = {b["author_id"]: b["count"] for b in item["users"]}
                counts.append(count_map.get(user_id, 0))
            series.append({"label": label, "data": counts})

        return {
            "dates": dates,
            "series": series,
            "total": sum(item["total"] for item in data),
            "users_count": len(series),
        }


    async def export(self, uow_session: UnitOfWork, current_user: SUserInfo) -> str:
        """Экспортирует задачи пользователя в Excel-файл."""
        author_id = self._resolve_author_id(current_user)
        async with uow_session.start():
            if author_id:
                todos: Sequence[TodoORM] = (
                    await uow_session.todo.get_todos_by_author_id(author_id=author_id)
                )
            else:
                todos: Sequence[TodoORM] = await uow_session.todo.get_all()

        filename = datetime.now(UTC).strftime("%Y_%m_%d_%H_%M_%S") + ".xlsx"
        file_path = f"data/{filename}"

        export_todos(todos, file_path)
        return file_path
