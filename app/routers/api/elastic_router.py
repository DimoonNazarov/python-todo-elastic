from datetime import datetime

from loguru import logger
from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
from fastapi import status, Form
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse

from app.core.database import get_async_uow_session
from app.core.uow import UnitOfWork

elastic_router = APIRouter(prefix="/elastic")


@elastic_router.get("/search/date/", status_code=status.HTTP_200_OK)
async def search_by_date(
    request: Request,
    date_from: datetime,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
):
    """Поиск тудушек, созданных после указанной даты (формат: 2024-01-01T00:00:00)"""
    results = await uow_session.elastic.search_by_date(date_from.isoformat())
    return templates.TemplateResponse(
        "tag_results.html",
        {
            "request": request,
            "results": results,
            "count": len(results),
            "subtitle": f"После {date_from.strftime('%d.%m.%Y %H:%M')}",
        },
    )


@elastic_router.get("/search/", response_class=HTMLResponse)
async def search_page(request: Request):
    """Страница поиска"""
    return templates.TemplateResponse("search.html", {"request": request})


@elastic_router.post("/search", response_class=HTMLResponse)
async def search_todos(
    request: Request,
    query: str = Form(...),
    uow_session: UnitOfWork = Depends(get_async_uow_session),
):
    try:
        results = await uow_session.elastic.search_todos(query)

        # Было: hit["_source"]["todo_id"] — неверно, _source уже развёрнут
        todo_ids = [hit["todo_id"] for hit in results]  # ✅

        if todo_ids:
            todos = await uow_session.todo.get_todos_by_ids(todo_ids)
        else:
            todos = []

        return templates.TemplateResponse(
            "search_results.html",
            {"request": request, "todos": todos, "query": query, "count": len(todos)},
        )
    except Exception as e:
        logger.error(f"Search error: {e}")


@elastic_router.get("/search/tag/{tag}", status_code=status.HTTP_200_OK)
async def search_by_tag(
    request: Request,
    tag: str,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
):
    """Поиск тудушек по тегу"""
    tag_normalized = tag.capitalize()
    results = await uow_session.elastic.search_by_tag(tag_normalized)
    return templates.TemplateResponse(
        "tag_results.html",
        {
            "request": request,
            "results": results,
            "count": len(results),
            "subtitle": f"Тег: {tag_normalized}",
        },
    )


@elastic_router.get("/search/top-words/", status_code=status.HTTP_200_OK)
async def search_by_top_words(
    request: Request,
    limit: int = 10,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
):
    """
    Возвращает топ-N популярных слов в формате JSON.
    """
    try:
        words = await uow_session.elastic.get_top_words(limit)
        return JSONResponse({"words": words})
    except Exception as e:
        logger.error("Top words error: %s", e)
        return JSONResponse({"words": []})


@elastic_router.get("/notes-per-day/", response_class=HTMLResponse)
async def notes_per_day_chart(
    request: Request,
    days: int = 30,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
):
    """
    Страница с графиком активности пользователей
    """
    try:
        data = await uow_session.elastic.get_notes_per_day(days)

        # Подготавливаем данные для графика
        dates = [item["date"] for item in data]
        counts = [item["count"] for item in data]

        return templates.TemplateResponse(
            "notes_per_day.html",
            {
                "request": request,
                "dates": dates,
                "counts": counts,
                "days": days,
                "total": sum(counts),
            },
        )
    except Exception as e:
        logger.error(f"Notes per day error: {e}")
        return templates.TemplateResponse(
            "notes_per_day.html",
            {
                "request": request,
                "dates": [],
                "counts": [],
                "days": days,
                "total": 0,
                "error": str(e),
            },
        )


@elastic_router.get("/api/notes-per-day/")
async def notes_per_day_api(
    days: int = 30, uow_session: UnitOfWork = Depends(get_async_uow_session)
):
    """
    API endpoint для получения данных в формате JSON
    """
    try:
        data = await uow_session.elastic.get_notes_per_day(days)
        return JSONResponse(
            {"data": data, "total": sum(item["count"] for item in data), "days": days}
        )
    except Exception as e:
        logger.error(f"Notes per day API error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
