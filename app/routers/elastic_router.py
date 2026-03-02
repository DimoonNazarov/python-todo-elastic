from datetime import datetime

from loguru import logger
from fastapi import APIRouter
from fastapi import Request
from fastapi import Depends
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
from fastapi import status
from fastapi import Form

from starlette.responses import HTMLResponse

from app.core.database import get_async_uow_session

from app.utils import generate_random_filename

from app.utils import import_todos

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


@elastic_router.post("/search/", response_class=HTMLResponse)
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
