"""Main of todo app"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.core import setup_service_logging
from app.core.database import get_es_client
from app.exceptions import (
    NotFoundException,
    InvalidPageException,
    IncorrectEmailOrPasswordException,
    ForbiddenException,
    InvalidCredentials,
    InactiveUserException,
)
from app.repository.elastic_repository import ElasticRepository
from app.routers import (
    todo_router,
    auth_router
)
from app.routers.exception_handlers import (
    invalid_credentials_handler,
    incorrect_email_or_password_handler,
    inactive_user_handler,
    not_found_handler,
    invalid_page_handler,
    forbidden_handler,
)
from app.utils import create_dirs
from app.middleware import JwtAuthMiddleware

setup_service_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте — создаём индекс с нужным маппингом
    es = get_es_client()
    repo = ElasticRepository(es)
    await repo.ensure_index_exists()
    yield
    # При остановке
    from app.core.database import close_es_client

    await close_es_client()


app = FastAPI(lifespan=lifespan, redirect_slashes=True)
app.add_middleware(JwtAuthMiddleware)


@app.get("/")
async def main_page():
    return RedirectResponse("/todo/home/", status_code=303)


app.include_router(todo_router)
app.include_router(auth_router)

create_dirs()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")


app.add_exception_handler(NotFoundException, not_found_handler)
app.add_exception_handler(InvalidPageException, invalid_page_handler)
app.add_exception_handler(IncorrectEmailOrPasswordException, incorrect_email_or_password_handler)
app.add_exception_handler(InvalidCredentials, invalid_credentials_handler)
app.add_exception_handler(ForbiddenException, forbidden_handler)
app.add_exception_handler(InactiveUserException, inactive_user_handler)
