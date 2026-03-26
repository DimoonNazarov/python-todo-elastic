import pytest
from httpx import AsyncClient


# Тест 1: страница логина отдаёт HTML и статус 200
@pytest.mark.asyncio(loop_scope="session")
async def test_login_page_loads(ac: AsyncClient):
    response = await ac.get("/auth/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# Тест 2: регистрация нового пользователя перенаправляет на логин
@pytest.mark.asyncio(loop_scope="session")
async def test_register_user(ac: AsyncClient):
    response = await ac.post(
        "/auth/register",
        data={
            "email": "testuser@example.com",
            "password": "testpassword",
            "first_name": "Test",
            "last_name": "User",
            "role": "editor",
        },
        follow_redirects=False,
    )
    # После регистрации ожидаем редирект на /auth/login
    assert response.status_code in (302, 303)
    assert "/auth/login" in response.headers.get("location", "")


# Тест 3: логин с правильными данными отдаёт редирект (устанавливает куки)
@pytest.mark.asyncio(loop_scope="session")
async def test_login_success(ac: AsyncClient):
    response = await ac.post(
        "/auth/token",
        json={
            "email": "testuser@example.com",
            "password": "testpassword",
        },
        follow_redirects=False,
    )
    # Успешный логин → редирект на главную, в cookies появляется access_token
    assert response.status_code in (302, 303)
    assert "access_token" in response.cookies
