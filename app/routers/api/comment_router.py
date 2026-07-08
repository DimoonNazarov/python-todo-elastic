import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from app.core import get_async_uow_session, UnitOfWork
from app.routers.dependencies import get_current_active_user
from app.schemas.comment import CommentCreate, CommentResponse, NotificationResponse
from app.schemas.user import SUserInfo
from app.services.comment import CommentService
from app.services.websocket_manager import manager, TODOS_FEED_CHANNEL, user_manager
from app.utils import extract_bearer_token, verify_access_token

logger = logging.getLogger(__name__)

comment_router = APIRouter(tags=["Comments"])
comment_service = CommentService()


@comment_router.get(
    "/todo/{todo_id}/comments/",
    response_model=list[CommentResponse],
    status_code=status.HTTP_200_OK,
)
async def get_comments(
    todo_id: int,
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    return await comment_service.get_comments(uow, todo_id)


@comment_router.post(
    "/todo/{todo_id}/comments/",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    todo_id: int,
    data: CommentCreate,
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    comment = await comment_service.create_comment(uow, todo_id, data, current_user)
    await manager.broadcast(todo_id, {"type": "new_comment", "comment": comment.model_dump(mode="json")})
    return comment


@comment_router.delete(
    "/todo/{todo_id}/comments/{comment_id}/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_comment(
    todo_id: int,
    comment_id: int,
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    await comment_service.delete_comment(uow, todo_id, comment_id, current_user)
    await manager.broadcast(todo_id, {"type": "delete_comment", "comment_id": comment_id})


# --- Notifications ---

@comment_router.get(
    "/api/notifications/",
    response_model=list[NotificationResponse],
    status_code=status.HTTP_200_OK,
)
async def get_notifications(
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    return await comment_service.get_notifications(uow, current_user)


@comment_router.get(
    "/api/notifications/count/",
    status_code=status.HTTP_200_OK,
)
async def count_unread_notifications(
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    count = await comment_service.count_unread(uow, current_user)
    return {"unread": count}


@comment_router.post(
    "/api/notifications/{notification_id}/read/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_notification_read(
    notification_id: int,
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    await comment_service.mark_read(uow, notification_id, current_user)


@comment_router.post(
    "/api/notifications/read-all/",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def mark_all_notifications_read(
    uow: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    await comment_service.mark_all_read(uow, current_user)


# --- WebSocket ---

@comment_router.websocket("/ws/todo/{todo_id}/")
async def websocket_comments(todo_id: int, websocket: WebSocket):
    await manager.connect(todo_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(todo_id, websocket)


@comment_router.websocket("/ws/todos/")
async def websocket_todos_feed(websocket: WebSocket):
    """Канал страницы списка задач (например, выполнение задачи из Telegram)."""
    await manager.connect(TODOS_FEED_CHANNEL, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(TODOS_FEED_CHANNEL, websocket)


@comment_router.websocket("/ws/notifications/")
async def websocket_notifications(websocket: WebSocket):
    """Личный канал пользователя: push уведомлений (упоминания, ответы, дедлайны)."""
    token = extract_bearer_token(websocket.cookies.get("access_token"))
    payload = verify_access_token(token) if token else None
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = int(payload["user_id"])
    await user_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        user_manager.disconnect(user_id, websocket)
