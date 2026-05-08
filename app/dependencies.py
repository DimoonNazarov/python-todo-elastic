from typing import Annotated
from fastapi import Depends

from app.services import (
    AuthService,
    TodoService,
    OpenRouterService,
    TodoClassificationService,
)
from app.services.search import SearchService


def get_auth_service() -> AuthService:
    """Возвращает сервис аутентификации."""
    return AuthService()


def get_openrouter_service() -> OpenRouterService:
    """Возвращает сервис работы с LLM (OpenRouter)."""
    return OpenRouterService()


def get_classification_service() -> TodoClassificationService:
    """Возвращает сервис работы с LLM (OpenRouter)."""
    return TodoClassificationService()


def get_search_service(
    classification_service: Annotated[
        TodoClassificationService, Depends(get_classification_service)
    ],
) -> SearchService:
    """Возвращает сервис поиска"""
    return SearchService(classification_service=classification_service)


def get_todo_service(
    openrouter_service: Annotated[OpenRouterService, Depends(get_openrouter_service)],
    search_service: Annotated[SearchService, Depends(get_search_service)],
    classification_service: Annotated[
        TodoClassificationService, Depends(get_classification_service)
    ],
) -> TodoService:
    """Возвращает основной сервис работы с todo (CRUD, LLM, поиск)."""
    return TodoService(
        openrouter_service=openrouter_service,
        search_service=search_service,
        classification_service=classification_service,
    )
