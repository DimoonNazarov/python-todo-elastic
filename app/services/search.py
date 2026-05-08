import logging
import math
from typing import Callable

from app.core import UnitOfWork
from app.exceptions import InvalidPageException
from app.schemas import SUserInfo, UserRole
from app.services.search_index import TodoClassificationService

logger = logging.getLogger(__name__)

SEARCH_RESULTS_FETCH_LIMIT = 1000


class SearchService:
    def __init__(self):
        self._classification = TodoClassificationService()

    @staticmethod
    def _resolve_author_id(user: SUserInfo) -> int | None:
        """
        VIEWER видит только свои задачи.
        ADMIN видит всё.
        """
        return user.id if user.role == UserRole.VIEWER else None

    async def _index_todo(
        self,
        uow_session: UnitOfWork,
        todo,
        file_content: str = "",
    ) -> None:
        """Индексация todo в Elasticsearch"""
        document = self._classification.build_search_document(todo=todo, file_content=file_content)
        await uow_session.elastic.ensure_index_exists()
        await uow_session.elastic.index_document(todo_id=todo.id, document=document)

    async def delete_todo(
        self,
        uow_session: UnitOfWork,
        todo_id: int,
    ) -> None:
        """Удаление todo из Elasticsearch."""
        await uow_session.elastic.delete_todo(todo_id)

    async def search_todos(
        self,
        uow_session: UnitOfWork,
        current_user: SUserInfo,
        limit: int,
        skip: int,
        tag: str | None,
        query: str | None,
        search_tag: str | None,
        search_date_from: str | None,
    ) -> dict:
        """Поиск todo через Elasticsearch"""
        author_id = self._resolve_author_id(current_user)

        # SEARCH BY QUERY
        if query
            return await self._search_response(
                uow_session=uow_session,
                search_callable=uow_session.elastic.search_todos,
                search_kwargs={
                    "query_text": query,
                    "tag": tag,
                    "author_id": author_id,
                },
                limit=limit,
                skip=skip,
                search_mode="query",
                subtitle=f"Результаты поиска по запросу: {query}",
            )

        # SEARCH BY TAG
        if search_tag
            return await self._search_response(
                uow_session=uow_session,
                search_callable=uow_session.elastic.search_by_tag,
                search_kwargs={
                    "tag": search_tag.capitalize(),
                    "author_id": author_id,
                },
                limit=limit,
                skip=skip,
                search_mode="tag",
                subtitle=f"Результаты поиска по тегу: {search_tag.capitalize()}",
            )

        # SEARCH BY DATE
        if search_date_from:
            return await self._search_response(
                uow_session=uow_session,
                search_callable=uow_session.elastic.search_by_date,
                search_kwargs={
                    "date_from": search_date_from,
                    "author_id": author_id,
                },
                limit=limit,
                skip=skip,
                search_mode="date",
                subtitle=f"Результаты поиска после {search_date_from}",
            )

        return {
            "todos": [],
            "skip": skip,
            "pages": 1,
            "total": 0,
            "search_mode": None,
            "subtitle": None,
        }

    async def _search_response(
    self,
    uow_session: UnitOfWork,
    search_callable: Callable,
    search_kwargs: dict,
    limit: int,
    skip: int,
    search_mode: str,
    subtitle: str
    ):

        search_result = await search_callable(
            limit=SEARCH_RESULTS_FETCH_LIMIT,
            skip=0,
            **search_kwargs
        )
        found_todos = await self._get_search_todos_from_hits(
            uow_session=uow_session,
            hits=search_result["items"],
        )
        total = len(found_todos)

        pages = math.ceil(total / limit) if total else 1

        if skip > pages:
            raise InvalidPageException(
                f"Page {skip} does not exist, total pages: {pages}",
            )

        start = skip * limit
        end = start + limit

        return {
            "todos": found_todos[start:end],
            "skip": skip,
            "pages": pages,
            "total": total,
            "search_mode": search_mode,
            "subtitle": subtitle,
        }

