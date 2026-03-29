import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _register_and_login(
    ac: AsyncClient, email: str, password: str = "password123"
) -> AsyncClient:
    """Регистрирует пользователя и возвращает клиент с куками."""
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


async def _add_todo(
    ac: AsyncClient, title: str, details: str = "desc", tag: str = "Планы"
) -> dict:
    response = await ac.post(
        "/todo/add/",
        data={
            "title": title,
            "details": details,
            "tag": tag,
            "source": "Созданная",
        },
    )
    assert response.status_code == 201
    return response.json()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def user_client(ac: AsyncClient) -> AsyncClient:
    """Клиент авторизованного обычного пользователя."""
    return await _register_and_login(ac, "todo_user@example.com")


@pytest.fixture(scope="module")
async def second_client(ac: AsyncClient) -> AsyncClient:
    """Клиент второго пользователя (для проверки 403)."""
    # Первый пользователь (admin) должен быть уже создан — регистрируем второго
    async with AsyncClient(transport=ac._transport, base_url="http://test") as client:
        return await _register_and_login(client, "todo_user2@example.com")

    # ---------------------------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_create_todo_success(user_client: AsyncClient):
    response = await user_client.post(
        "/todo/add/",
        data={
            "title": "Тестовая задача",
            "details": "Описание задачи",
            "tag": "Планы",
            "source": "Созданная",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "success"


@pytest.mark.asyncio(loop_scope="session")
async def test_create_todo_without_auth(ac: AsyncClient):
    response = await ac.post(
        "/todo/add/",
        data={
            "title": "Задача без авторизации",
            "details": "desc",
            "tag": "Планы",
            "source": "Созданная",
        },
        follow_redirects=False,
    )
    # Без куки — редирект на логин или 401
    assert response.status_code in (302, 303, 401)


# ---------------------------------------------------------------------------
# READ / LIST
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_list_todos_returns_html(user_client: AsyncClient):
    response = await user_client.get("/todo/list/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio(loop_scope="session")
async def test_list_todos_pagination(user_client: AsyncClient):
    # Создаём несколько задач
    for i in range(3):
        await _add_todo(user_client, f"Задача пагинация {i}")

    response = await user_client.get("/todo/list/?limit=2&skip=0")
    assert response.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_list_todos_filter_by_tag(user_client: AsyncClient):
    await _add_todo(user_client, "Задача с тегом учёба", tag="Учёба")

    response = await user_client.get("/todo/list/?tag=Учёба")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# ---------------------------------------------------------------------------
# EDIT
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_edit_todo_success(user_client: AsyncClient):
    # Создаём задачу
    await _add_todo(user_client, "Задача для редактирования")

    # Получаем список, чтобы найти id — через API нет прямого эндпоинта,
    # поэтому создаём и сразу редактируем последнюю (id=1 при чистой БД)
    # В реальных тестах лучше парсить ответ или добавить GET /api/todos/
    response = await user_client.put(
        "/todo/edit/1/",
        data={
            "title": "Отредактированная задача",
            "details": "Новое описание",
            "completed": "false",
            "tag": "Планы",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


@pytest.mark.asyncio(loop_scope="session")
async def test_edit_todo_mark_completed(user_client: AsyncClient):
    response = await user_client.put(
        "/todo/edit/1/",
        data={
            "title": "Выполненная задача",
            "details": "desc",
            "completed": "true",
            "tag": "Планы",
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_todo_success(user_client: AsyncClient):
    await _add_todo(user_client, "Задача для удаления")

    response = await user_client.delete("/todo/delete/1/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert "deleted_todo_title" in body


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_nonexistent_todo(user_client: AsyncClient):
    response = await user_client.delete("/todo/delete/999999/")
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_all_todos(user_client: AsyncClient):
    await _add_todo(user_client, "Задача 1 для массового удаления")
    await _add_todo(user_client, "Задача 2 для массового удаления")

    response = await user_client.delete("/todo/delete/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["deleted_count"] >= 2
