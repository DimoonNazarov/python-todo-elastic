import logging
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.core import get_async_uow_session, UnitOfWork
from app.dependencies import get_telegram_service
from app.exceptions import NotFoundException, TelegramNotLinkedException
from app.routers.dependencies import get_current_active_user
from app.schemas import SUserInfo
from app.services.telegram import TelegramService

telegram_router = APIRouter(prefix="/telegram", tags=["Telegram"])

logger = logging.getLogger(__name__)


@telegram_router.get("/link/", status_code=status.HTTP_200_OK)
async def get_telegram_link(
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    telegram_service: Annotated[TelegramService, Depends(get_telegram_service)],
):
    """Статус привязки и deep-link для подключения Telegram."""
    async with uow_session.start():
        user = await uow_session.auth.find_one_or_none_by_id(current_user.id)
        linked = bool(user and user.telegram_chat_id)

    link_url = None
    if not linked:
        link_url = await telegram_service.build_link_url(current_user.id)

    return {"status": "success", "linked": linked, "link_url": link_url}


@telegram_router.post("/unlink/", status_code=status.HTTP_200_OK)
async def unlink_telegram(
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
):
    """Отвязать Telegram-чат от аккаунта."""
    async with uow_session.start():
        await uow_session.auth.update_by_id(
            current_user.id, {"telegram_chat_id": None}
        )
    return {"status": "success", "details": "Telegram unlinked"}


@telegram_router.post("/send/{todo_id}/", status_code=status.HTTP_200_OK)
async def send_todo_to_telegram(
    todo_id: int,
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    telegram_service: Annotated[TelegramService, Depends(get_telegram_service)],
):
    """Сохранить заметку в Telegram-чат текущего пользователя."""
    async with uow_session.start():
        user = await uow_session.auth.find_one_or_none_by_id(current_user.id)
        chat_id = user.telegram_chat_id if user else None
        todo = await uow_session.todo.get_todo_by_id(todo_id)
        if todo is None:
            raise NotFoundException(f"Заметка {todo_id} не найдена")

    if not chat_id:
        raise TelegramNotLinkedException(
            "Telegram не привязан к аккаунту. Привяжите чат и повторите."
        )

    await telegram_service.send_todo(chat_id, todo)
    logger.info("Todo %s sent to telegram chat of user %s", todo_id, current_user.id)
    return {"status": "success", "details": "Todo sent to Telegram"}
