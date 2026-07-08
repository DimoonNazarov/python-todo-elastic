"""Main of todo app"""

import asyncio
from contextlib import asynccontextmanager, suppress
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core import setup_service_logging
from app.core.database import get_es_client
from app.services.notification_bus import listen_for_notifications
from app.exceptions import (
    NotFoundException,
    InvalidPageException,
    IncorrectEmailOrPasswordException,
    ForbiddenException,
    InvalidTodoDataException,
    InvalidCredentials,
    InactiveUserException,
    LLMConfigurationException,
    LLMRequestException,
    LLMServiceException,
    SearchSyncException,
    TelegramConfigurationException,
    TelegramServiceException,
    TelegramNotLinkedException,
)
from app.repository.elastic_repository import ElasticRepository
from app.routers import (
    todo_router,
    auth_router,
    comment_router,
    telegram_router,
)
from app.routers.exception_handlers import (
    invalid_credentials_handler,
    incorrect_email_or_password_handler,
    inactive_user_handler,
    not_found_handler,
    invalid_page_handler,
    invalid_todo_data_handler,
    llm_configuration_handler,
    llm_request_handler,
    llm_service_handler,
    search_sync_handler,
    forbidden_handler,
    telegram_configuration_handler,
    telegram_service_handler,
    telegram_not_linked_handler,
)
from app.services.telegram_polling import run_telegram_polling
from app.utils import create_dirs
from app.middleware import JwtAuthMiddleware

setup_service_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте — создаём индекс с нужным маппингом
    es = get_es_client()
    repo = ElasticRepository(es)
    await repo.ensure_index_exists()
    await repo.ensure_file_content_field()
    
    # Поллинг Telegram-бота (привязка чатов через /start <код>)
    telegram_task = None
    if settings.TELEGRAM_BOT_TOKEN:
        telegram_task = asyncio.create_task(run_telegram_polling())
        
    # Фоновая подписка на Redis Pub/Sub: доставляет уведомления о дедлайнах
    # (созданные Celery-воркером в отдельном процессе) в WebSocket этого инстанса
    notifications_listener = asyncio.create_task(listen_for_notifications())

    yield

    # При остановке
    if telegram_task is not None:
        telegram_task.cancel()
        with suppress(asyncio.CancelledError):
            await telegram_task

    from app.core.database import close_es_client

    notifications_listener.cancel()
    await close_es_client()


app = FastAPI(lifespan=lifespan, redirect_slashes=True)
app.add_middleware(JwtAuthMiddleware)


@app.get("/")
async def main_page():
    return RedirectResponse("/todo/home/", status_code=303)


app.include_router(todo_router)
app.include_router(auth_router)
app.include_router(comment_router)
app.include_router(telegram_router)

create_dirs()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")
app.mount("/files", StaticFiles(directory="files"), name="files")


app.add_exception_handler(NotFoundException, not_found_handler)
app.add_exception_handler(InvalidPageException, invalid_page_handler)
app.add_exception_handler(IncorrectEmailOrPasswordException, incorrect_email_or_password_handler)
app.add_exception_handler(InvalidCredentials, invalid_credentials_handler)
app.add_exception_handler(ForbiddenException, forbidden_handler)
app.add_exception_handler(InvalidTodoDataException, invalid_todo_data_handler)
app.add_exception_handler(InactiveUserException, inactive_user_handler)
app.add_exception_handler(LLMConfigurationException, llm_configuration_handler)
app.add_exception_handler(LLMRequestException, llm_request_handler)
app.add_exception_handler(LLMServiceException, llm_service_handler)
app.add_exception_handler(SearchSyncException, search_sync_handler)
app.add_exception_handler(TelegramConfigurationException, telegram_configuration_handler)
app.add_exception_handler(TelegramServiceException, telegram_service_handler)
app.add_exception_handler(TelegramNotLinkedException, telegram_not_linked_handler)
