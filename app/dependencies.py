from typing import Annotated

from fastapi import Depends

from app.services import AuthService
from app.services import OpenRouterService
from app.services import TodoService


def get_auth_service() -> AuthService:
    return AuthService()


def get_openrouter_service() -> OpenRouterService:
    return OpenRouterService()


def get_todo_service(
    openrouter_service: Annotated[OpenRouterService, Depends(get_openrouter_service)],
) -> TodoService:
    return TodoService(openrouter_service)
