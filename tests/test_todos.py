import pytest
from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
async def test_add_todo_success(ac: AsyncClient):
    with open("data/test.png", "rb") as image_file:
        files = {
            "image": ("test.png", image_file, "image/png")
        }
        data = {
            "title": "Задача",
            "details": "Описание задачи",
            "tag": "Планы",
            "created_at": "2023-10-01T00:00:00Z",
            "completed_at": None,
            "source": "Созданная"
        }

        response = await ac.post("/todo/add/", data=data, files=files)

        assert response.status_code == 201
        assert response.json()["status"] == "success"
        assert response.json()["details"] == "Todo added"


@pytest.mark.asyncio(loop_scope="session")
async def test_add_todo_missing_fields(ac: AsyncClient):
    response = await ac.post("/todo/add/", data={})

    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="session")
async def test_get_todos_success(ac: AsyncClient):
    title = "Задача"
    details = "Описание задачи"
    tag = "Планы"
    created_at = "2023-10-01T00:00:00Z"
    source = "Созданная"

    with open("data/test.png", "rb") as image_file:
        files = {
            "image": ("test.png", image_file, "image/png")
        }
        data = {
            "title": title,
            "details": details,
            "tag": tag,
            "created_at": created_at,
            "completed_at": None,
            "source": source
        }

        await ac.post("/todo/add/", data=data, files=files)

    response = await ac.get("/todo/list/", params={
        "limit": 10,
        "skip": 0,
    })

    assert response.status_code == 200

    response_text = response.text

    assert title in response_text
    assert details in response_text
    assert tag in response_text
    assert source in response_text


@pytest.mark.asyncio(loop_scope="session")
async def test_get_todos_no_results(ac: AsyncClient):
    response = await ac.get("/todo/list/", params={
        "limit": 10,
        "skip": 1000,
    })

    assert response.status_code == 404
    assert response.json()["detail"] == "No such page"
