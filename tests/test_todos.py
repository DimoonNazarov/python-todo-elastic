import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
async def test_login_page_loads(ac: AsyncClient):
    response = await ac.get("/auth/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


@pytest.mark.asyncio(loop_scope="session")
async def test_register_user(ac: AsyncClient):
    response = await ac.post(
        "/auth/register",
        json={
            "email": "testuser@example.com",
            "password": "testpassword",
            "confirm_password": "testpassword",
            "first_name": "Test",
            "last_name": "User",
            "role": "editor",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert "/auth/login" in response.headers.get("location", "")


@pytest.mark.asyncio(loop_scope="session")
async def test_login_success(ac: AsyncClient):

    await ac.post(
        "/auth/register",
        json={
            "email": "login_user@example.com",
            "password": "testpassword",
            "confirm_password": "testpassword",
            "first_name": "Test",
            "last_name": "User",
        },
        follow_redirects=False,
    )
    response = await ac.post(
        "/auth/token",
        json={
            "email": "login_user@example.com",
            "password": "testpassword",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    assert "access_token" in response.cookies
