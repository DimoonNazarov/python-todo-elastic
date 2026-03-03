from elasticsearch import AsyncElasticsearch
from fastapi import Depends

from app.core import UnitOfWork, get_async_uow_session
from app.services import AuthService
from app.services import TodoService


def get_auth_service() -> AuthService:
    return AuthService()


def get_todo_service() -> TodoService:
    return TodoService()
