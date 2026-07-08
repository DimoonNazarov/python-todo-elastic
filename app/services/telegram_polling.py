"""Фоновый поллинг Telegram Bot API (getUpdates).

Команды бота:
- /start <код привязки> — привязывает chat_id к аккаунту (deep-link из приложения);
- /tasks — выбор пользователя (inline-кнопки), затем карточки его невыполненных
  задач с кнопкой «Отметить выполненной» (синхронизируется с приложением
  через TodoService.update: права, история изменений, Elasticsearch).

Просмотр и подтверждение задач доступны только из привязанных чатов.
Запускается из lifespan приложения, только если задан TELEGRAM_BOT_TOKEN.
"""

import asyncio
import logging

from app.core.database import async_session_maker, get_es_client
from app.core.uow import UnitOfWork
from app.exceptions import (
    ForbiddenException,
    NotFoundException,
    SearchSyncException,
    TelegramServiceException,
)
from app.schemas import SUserInfo
from app.services import (
    OpenRouterService,
    TodoClassificationService,
    TodoService,
)
from app.services.search import SearchService
from app.services.telegram import (
    MAX_TODO_CARDS,
    TelegramService,
    build_complete_keyboard,
    build_completed_keyboard,
    build_users_keyboard,
    format_pending_todos_header,
    format_todo_card,
)
from app.services.websocket_manager import manager as ws_manager
from app.services.websocket_manager import TODOS_FEED_CHANNEL

logger = logging.getLogger(__name__)

POLL_TIMEOUT_SECONDS = 25
RETRY_DELAY_SECONDS = 5

NOT_LINKED_TEXT = (
    "Чтобы привязать аккаунт, нажмите кнопку «Привязать Telegram» "
    "в приложении и перейдите по сгенерированной ссылке. "
    "Код из ссылки действует ограниченное время."
)

BOT_COMMANDS = [
    {"command": "tasks", "description": "Невыполненные задачи пользователя"},
    {"command": "start", "description": "Привязать аккаунт приложения"},
]


async def run_telegram_polling() -> None:
    service = TelegramService()
    offset: int | None = None
    logger.info("Telegram polling started")

    try:
        await service.set_my_commands(BOT_COMMANDS)
    except TelegramServiceException:
        logger.warning("Failed to register telegram bot commands")

    while True:
        try:
            payload = {
                "timeout": POLL_TIMEOUT_SECONDS,
                "allowed_updates": ["message", "callback_query"],
            }
            if offset is not None:
                payload["offset"] = offset
            updates = await service._call_api("getUpdates", payload)

            for update in updates:
                offset = update["update_id"] + 1
                try:
                    await _handle_update(service, update)
                except Exception:
                    logger.exception("Failed to handle telegram update")
        except asyncio.CancelledError:
            logger.info("Telegram polling stopped")
            raise
        except TelegramServiceException:
            await asyncio.sleep(RETRY_DELAY_SECONDS)
        except Exception:
            logger.exception("Unexpected error in telegram polling")
            await asyncio.sleep(RETRY_DELAY_SECONDS)


async def _handle_update(service: TelegramService, update: dict) -> None:
    if "callback_query" in update:
        await _handle_callback_query(service, update["callback_query"])
        return

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    chat_id = (message.get("chat") or {}).get("id")
    if not chat_id or not text:
        return

    if text.startswith("/start"):
        await _handle_start(service, chat_id, text)
    elif text.startswith("/tasks"):
        await _handle_tasks(service, chat_id)


async def _find_linked_user(chat_id: int):
    """Пользователь приложения, к которому привязан этот чат (или None)."""
    uow = UnitOfWork(async_session_maker)
    async with uow.start():
        # find_all, а не find_one_or_none: в старых данных один чат мог быть
        # привязан к нескольким аккаунтам (сейчас привязка это исключает)
        users = await uow.auth.find_all({"telegram_chat_id": chat_id})
        return users[0] if users else None


async def _handle_start(service: TelegramService, chat_id: int, text: str) -> None:
    parts = text.split(maxsplit=1)
    code = parts[1].strip() if len(parts) > 1 else ""
    user_id = service.verify_link_code(code) if code else None

    if user_id is None:
        await service.send_message(chat_id, NOT_LINKED_TEXT)
        return

    uow = UnitOfWork(async_session_maker)
    async with uow.start():
        user = await uow.auth.find_one_or_none_by_id(user_id)
        if user is None or not user.is_active:
            await service.send_message(
                chat_id, "Пользователь не найден или деактивирован."
            )
            return
        # Один чат — один аккаунт: снимаем привязку с других пользователей
        await uow.auth.update(
            {"telegram_chat_id": chat_id}, {"telegram_chat_id": None}
        )
        await uow.auth.update_by_id(user_id, {"telegram_chat_id": chat_id})
        first_name = user.first_name

    await service.send_message(
        chat_id,
        f"✅ {first_name}, ваш Telegram привязан к аккаунту. "
        "Теперь заметки можно сохранять в этот чат, а команда /tasks "
        "покажет невыполненные задачи пользователей.",
    )
    logger.info("Telegram chat %s linked to user %s", chat_id, user_id)


async def _handle_tasks(service: TelegramService, chat_id: int) -> None:
    """Отправляет клавиатуру выбора пользователя."""
    if await _find_linked_user(chat_id) is None:
        await service.send_message(chat_id, NOT_LINKED_TEXT)
        return

    uow = UnitOfWork(async_session_maker)
    async with uow.start():
        users = await uow.auth.get_active_users()

    if not users:
        await service.send_message(chat_id, "Активных пользователей не найдено.")
        return

    await service.send_message(
        chat_id,
        "Выберите пользователя, чтобы посмотреть его невыполненные задачи:",
        reply_markup=build_users_keyboard(users),
    )


def _build_todo_service() -> TodoService:
    """Собирает TodoService вне DI FastAPI (для фонового поллинга)."""
    classification_service = TodoClassificationService()
    return TodoService(
        openrouter_service=OpenRouterService(),
        search_service=SearchService(classification_service=classification_service),
        classification_service=classification_service,
    )


async def _handle_callback_query(service: TelegramService, callback: dict) -> None:
    """Обрабатывает нажатия inline-кнопок (tasks:<user_id> / done:<todo_id>)."""
    callback_id = callback.get("id")
    message = callback.get("message") or {}
    chat_id = (message.get("chat") or {}).get("id")
    data = callback.get("data") or ""

    action, _, raw_id = data.partition(":")
    if not chat_id or action not in ("tasks", "done") or not raw_id.isdigit():
        # в т.ч. "noop" — кнопка-индикатор под выполненной карточкой
        if callback_id:
            await service.answer_callback_query(callback_id)
        return

    linked_user = await _find_linked_user(chat_id)
    if linked_user is None:
        if callback_id:
            await service.answer_callback_query(callback_id)
        await service.send_message(chat_id, NOT_LINKED_TEXT)
        return

    if action == "tasks":
        if callback_id:
            await service.answer_callback_query(callback_id)
        await _send_pending_todo_cards(service, chat_id, int(raw_id))
    else:
        await _complete_todo(
            service,
            chat_id,
            message_id=message.get("message_id"),
            callback_id=callback_id,
            todo_id=int(raw_id),
            linked_user=linked_user,
        )


async def _send_pending_todo_cards(
    service: TelegramService, chat_id: int, author_id: int
) -> None:
    """Шлёт карточки невыполненных задач пользователя с кнопкой выполнения."""
    uow = UnitOfWork(async_session_maker)
    async with uow.start():
        user = await uow.auth.find_one_or_none_by_id(author_id)
        if user is None:
            await service.send_message(chat_id, "Пользователь не найден.")
            return
        todos = await uow.todo.get_pending_todos_by_author_id(user.id)

    await service.send_message(chat_id, format_pending_todos_header(user, len(todos)))

    for todo in todos[:MAX_TODO_CARDS]:
        await service.send_message(
            chat_id,
            format_todo_card(todo),
            reply_markup=build_complete_keyboard(todo.id),
        )

    if len(todos) > MAX_TODO_CARDS:
        await service.send_message(
            chat_id,
            f"…и ещё {len(todos) - MAX_TODO_CARDS} — "
            "полный список смотрите в приложении.",
        )


async def _complete_todo(
    service: TelegramService,
    chat_id: int,
    message_id: int | None,
    callback_id: str | None,
    todo_id: int,
    linked_user,
) -> None:
    """Отмечает задачу выполненной от имени владельца чата (как в приложении)."""
    actor = SUserInfo.model_validate(linked_user)
    uow = UnitOfWork(async_session_maker, get_es_client())

    async with uow.start():
        todo = await uow.todo.get_todo_by_id(todo_id)

    if todo is None:
        if callback_id:
            await service.answer_callback_query(callback_id, "Задача не найдена.")
        return

    try:
        updated_todo = await _build_todo_service().update(
            uow_session=uow,
            user=actor,
            todo_id=todo_id,
            title=todo.title,
            details=todo.details,
            completed=True,
            tag=todo.tag,
            created_at=todo.created_at,
            image_path=todo.image_path,
            existing_image=None,
            image=None,
        )
    except ForbiddenException:
        if callback_id:
            await service.answer_callback_query(callback_id)
        await service.send_message(
            chat_id,
            "⛔ Отмечать выполненными можно только свои задачи "
            "(администратор может любые).",
        )
        return
    except NotFoundException:
        if callback_id:
            await service.answer_callback_query(callback_id, "Задача не найдена.")
        return
    except SearchSyncException:
        logger.exception("Search sync failed while completing todo %s", todo_id)
        if callback_id:
            await service.answer_callback_query(callback_id)
        await service.send_message(
            chat_id,
            "⚠️ Не удалось синхронизировать изменение с поиском — "
            "задача не отмечена. Попробуйте позже.",
        )
        return

    if callback_id:
        await service.answer_callback_query(callback_id, "✅ Задача выполнена")
    if message_id:
        # Обновляем карточку: статус «Выполнена», кнопка становится индикатором
        await service.edit_message_text(
            chat_id,
            message_id,
            format_todo_card(updated_todo),
            reply_markup=build_completed_keyboard(),
        )

    # Живое обновление открытых страниц списка задач в приложении
    await ws_manager.broadcast(
        TODOS_FEED_CHANNEL,
        {
            "type": "todo_completed",
            "todo_id": todo_id,
            "completed_by": f"{actor.first_name} {actor.last_name}",
        },
    )
    logger.info(
        "Todo %s marked completed via telegram by user %s", todo_id, actor.id
    )
