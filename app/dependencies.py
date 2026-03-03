from elasticsearch import AsyncElasticsearch
from fastapi import Depends

from app.core import UnitOfWork, get_async_uow_session
from app.services import AuthService
from app.services import TodoService
from app.repository import TodoRepository, AuthRepository

def get_auth_service(
        uow_session: UnitOfWork = Depends(get_async_uow_session)
) -> AuthService:
    return AuthService(auth_repository=uow_session.auth, token_repository=uow_session.token)


def get_todo_service(
    uow_session: UnitOfWork = Depends(get_async_uow_session),
) -> TodoService:
    return TodoService(todo_repository=uow_session.todo)
