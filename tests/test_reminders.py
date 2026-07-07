from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.database import async_session_maker
from app.core.uow import UnitOfWork
from app.models import Notification, Todo, User
from app.schemas import TodoSource
from app.services.reminder import ReminderService


async def _register_and_login(ac: AsyncClient, email: str, password: str = "password123") -> AsyncClient:
    await ac.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "confirm_password": password,
            "first_name": "Test",
            "last_name": "User",
        },
        follow_redirects=False,
    )
    await ac.post(
        "/auth/token",
        json={"email": email, "password": password},
        follow_redirects=False,
    )
    return ac


@pytest.fixture
async def reminder_client(ac: AsyncClient) -> AsyncClient:
    return await _register_and_login(ac, "reminder_user@example.com")


@pytest.mark.asyncio(loop_scope="session")
async def test_add_todo_with_due_at_persists(reminder_client: AsyncClient):
    response = await reminder_client.post(
        "/todo/add/",
        data={
            "title": "Задача с дедлайном",
            "details": "desc",
            "tag": "Планы",
            "source": "Созданная",
            "due_at": "2026-12-31T10:00:00",
        },
    )
    assert response.status_code == 201

    async with async_session_maker() as session:
        todo = (
            await session.execute(select(Todo).where(Todo.title == "Задача с дедлайном"))
        ).scalar_one()
        assert todo.due_at is not None
        assert todo.reminder_sent is False


@pytest.mark.asyncio(loop_scope="session")
async def test_edit_todo_preserves_due_at_when_resubmitted(reminder_client: AsyncClient):
    """Регрессия: раньше update() всегда затирал due_at, т.к. TodoSchema
    строился без due_at (дефолт None) и это уходило в UPDATE."""
    await reminder_client.post(
        "/todo/add/",
        data={
            "title": "Задача для сохранения дедлайна",
            "details": "desc",
            "tag": "Планы",
            "source": "Созданная",
            "due_at": "2026-12-31T10:00:00",
        },
    )

    async with async_session_maker() as session:
        todo_id = (
            await session.execute(
                select(Todo.id).where(Todo.title == "Задача для сохранения дедлайна")
            )
        ).scalar_one()

    response = await reminder_client.put(
        f"/todo/edit/{todo_id}/",
        data={
            "title": "Задача для сохранения дедлайна (изменена)",
            "details": "desc",
            "completed": "false",
            "tag": "Планы",
            "created_at": "2026-01-01T00:00:00",
            "due_at": "2026-12-31T10:00:00",
        },
    )
    assert response.status_code == 200

    async with async_session_maker() as session:
        todo = await session.get(Todo, todo_id)
        assert todo.due_at is not None


@pytest.mark.asyncio(loop_scope="session")
async def test_edit_todo_changing_due_at_resets_reminder_sent(reminder_client: AsyncClient):
    await reminder_client.post(
        "/todo/add/",
        data={
            "title": "Задача с уже отправленным напоминанием",
            "details": "desc",
            "tag": "Планы",
            "source": "Созданная",
            "due_at": "2026-12-31T10:00:00",
        },
    )

    async with async_session_maker() as session:
        todo = (
            await session.execute(
                select(Todo).where(Todo.title == "Задача с уже отправленным напоминанием")
            )
        ).scalar_one()
        todo.reminder_sent = True
        todo_id = todo.id
        await session.commit()

    response = await reminder_client.put(
        f"/todo/edit/{todo_id}/",
        data={
            "title": "Задача с уже отправленным напоминанием",
            "details": "desc",
            "completed": "false",
            "tag": "Планы",
            "created_at": "2026-01-01T00:00:00",
            "due_at": "2027-01-15T10:00:00",
        },
    )
    assert response.status_code == 200

    async with async_session_maker() as session:
        todo = await session.get(Todo, todo_id)
        assert todo.reminder_sent is False


@pytest.mark.asyncio(loop_scope="session")
async def test_reminder_service_notifies_only_due_soon_incomplete_todos(ac: AsyncClient):
    await _register_and_login(ac, "reminder_service_user@example.com")

    async with async_session_maker() as session:
        user = (
            await session.execute(select(User).where(User.email == "reminder_service_user@example.com"))
        ).scalar_one()

        due_soon = Todo(
            title="Скоро дедлайн",
            details="desc",
            tag="Планы",
            source=TodoSource.created,
            author_id=user.id,
            due_at=datetime.now(UTC) + timedelta(minutes=30),
        )
        due_later = Todo(
            title="Дедлайн ещё далеко",
            details="desc",
            tag="Планы",
            source=TodoSource.created,
            author_id=user.id,
            due_at=datetime.now(UTC) + timedelta(days=5),
        )
        completed_due_soon = Todo(
            title="Скоро дедлайн, но выполнена",
            details="desc",
            tag="Планы",
            source=TodoSource.created,
            author_id=user.id,
            due_at=datetime.now(UTC) + timedelta(minutes=30),
            completed=True,
        )
        session.add_all([due_soon, due_later, completed_due_soon])
        await session.commit()
        await session.refresh(due_soon)
        await session.refresh(due_later)
        due_soon_id, due_later_id = due_soon.id, due_later.id

    uow = UnitOfWork(async_session_maker, es_client=None)
    payloads = await ReminderService().notify_due_soon(uow, before_minutes=60)

    assert len(payloads) == 1
    assert payloads[0]["todo_id"] == due_soon_id
    assert payloads[0]["recipient_id"] == user.id

    async with async_session_maker() as session:
        assert (await session.get(Todo, due_soon_id)).reminder_sent is True
        assert (await session.get(Todo, due_later_id)).reminder_sent is False

        notification = (
            await session.execute(select(Notification).where(Notification.todo_id == due_soon_id))
        ).scalar_one()
        assert notification.type == "deadline"
        assert notification.recipient_id == user.id
        assert notification.comment_id is None

    # Уже уведомлённая задача не должна попасть в выборку повторно
    payloads_again = await ReminderService().notify_due_soon(uow, before_minutes=60)
    assert payloads_again == []