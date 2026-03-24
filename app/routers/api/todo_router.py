import logging
import os
from typing import Any
import shutil
from datetime import datetime
from fastapi import (
    APIRouter,
    Request,
    File,
    UploadFile,
    Depends,
    status,
    HTTPException,
    Form,
)
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.responses import JSONResponse
from starlette.responses import HTMLResponse
from typing import Annotated

from app.core import get_async_uow_session, UnitOfWork
from app.dependencies import get_todo_service
from app.routers.dependencies import get_current_user, get_current_active_user
from app.schemas import TodoSource, Todo, Tags, SUserInfo, UserRole
from app.services.search_index import enrich_todo_display
from app.services.todo import TodoService
from app.utils import (
    import_todos,
    export_todos,
)

todo_router = APIRouter(prefix="/todo", tags=["Todo"])

# pylint: disable=invalid-name
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)


def _todos_page_context(
    request: Request,
    *,
    todos: list | Any,
    limit: int,
    skip: int,
    pages: int,
    created_from,
    created_to,
    tag,
    search_query: str | None = None,
    search_date_from: str | None = None,
    search_mode: str | None = None,
    subtitle: str | None = None,
):
    current_user_role = request.state.user["role"]
    if hasattr(current_user_role, "value"):
        current_user_role = current_user_role.value

    return {
        "request": request,
        "todos": todos,
        "page": skip,
        "pages": pages,
        "limit": limit,
        "creation_date_start": created_from,
        "creation_date_end": created_to,
        "tag": tag,
        "search_query": search_query,
        "search_date_from": search_date_from,
        "search_mode": search_mode,
        "subtitle": subtitle,
        "is_search_result": search_mode is not None,
        "current_user_id": int(request.state.user["user_id"]),
        "current_user_role": current_user_role,
    }


@todo_router.get("/home/", status_code=status.HTTP_200_OK)
async def get_home(request: Request):
    """Main page with todo list"""
    logger.info("In home")

    return templates.TemplateResponse("index.html", {"request": request})


@todo_router.get("/401", status_code=status.HTTP_200_OK)
async def page_401(request: Request):
    """Main page with todo list"""
    return templates.TemplateResponse("401.html", {"request": request})


@todo_router.get("/info-tasks/", status_code=status.HTTP_200_OK)
async def get_home(request: Request):
    """Main page with todo list"""

    return templates.TemplateResponse("info-tasks.html", {"request": request})


@todo_router.get("/list/", status_code=status.HTTP_200_OK)
async def get_todos(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    limit: int = 10,
    skip: int = 0,
    created_from: str = None,
    created_to: str = None,
    tag: Tags = None,
    query: str | None = None,
    search_tag: str | None = None,
    search_date_from: str | None = None,
):
    result = await todo_service.get_todos_page(
        uow_session=uow_session,
        current_user=current_user,
        limit=limit,
        skip=skip,
        created_from=created_from,
        created_to=created_to,
        tag=tag,
        query=query,
        search_tag=search_tag,
        search_date_from=search_date_from,
    )

    return templates.TemplateResponse(
        "todos.html",
        _todos_page_context(
            request,
            todos=result["todos"],
            limit=limit,
            skip=result["skip"],
            pages=result["pages"],
            created_from=created_from,
            created_to=created_to,
            tag=tag,
            search_query=query,
            search_date_from=search_date_from,
            search_mode=result["search_mode"],
            subtitle=result["subtitle"],
        ),
    )


@todo_router.get("/search/top-words/", status_code=status.HTTP_200_OK)
async def search_by_top_words(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    limit: int = 10,
):
    """Возвращает топ-N популярных слов в формате JSON."""
    try:
        author_id = current_user.id if current_user.role == UserRole.VIEWER else None
        words = await uow_session.elastic.get_top_words(limit, author_id=author_id)
        return JSONResponse({"words": words})
    except Exception as e:
        logger.error("Top words error: %s", e)
        return JSONResponse({"words": []})


@todo_router.get("/notes-per-day/", response_class=HTMLResponse)
async def notes_per_day_chart(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    days: int = 30,
):
    """Страница с графиком активности пользователей"""
    try:
        author_id = current_user.id if current_user.role == UserRole.VIEWER else None
        data = await uow_session.elastic.get_notes_per_day_by_user(
            days,
            author_id=author_id,
        )
        dates = [item["date"] for item in data]

        user_ids = sorted(
            {
                user_bucket["author_id"]
                for item in data
                for user_bucket in item["users"]
            }
        )

        async with uow_session.start():
            users = await uow_session.auth.get_users_by_ids(user_ids)

        users_by_id = {user.id: user for user in users}
        series = []
        for user_id in user_ids:
            user = users_by_id.get(user_id)
            label = user.email if user else f"Пользователь #{user_id}"
            counts = []
            for item in data:
                users_count_map = {
                    bucket["author_id"]: bucket["count"] for bucket in item["users"]
                }
                counts.append(users_count_map.get(user_id, 0))
            series.append({"label": label, "data": counts})

        return templates.TemplateResponse(
            "notes_per_day.html",
            {
                "request": request,
                "dates": dates,
                "series": series,
                "days": days,
                "total": sum(item["total"] for item in data),
                "users_count": len(series),
            },
        )
    except Exception as e:
        logger.error("Notes per day error: %s", e)
        return templates.TemplateResponse(
            "notes_per_day.html",
            {
                "request": request,
                "dates": [],
                "series": [],
                "days": days,
                "total": 0,
                "users_count": 0,
                "error": str(e),
            },
        )


@todo_router.get("/api/notes-per-day/")
async def notes_per_day_api(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    days: int = 30,
):
    """API endpoint для получения данных графика в JSON."""
    try:
        author_id = current_user.id if current_user.role == UserRole.VIEWER else None
        data = await uow_session.elastic.get_notes_per_day_by_user(
            days,
            author_id=author_id,
        )
        return JSONResponse(
            {"data": data, "total": sum(item["total"] for item in data), "days": days}
        )
    except Exception as e:
        logger.error("Notes per day API error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)


@todo_router.post("/add/", status_code=status.HTTP_201_CREATED)
async def add_todo(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    user: Annotated[SUserInfo, Depends(get_current_active_user)],
    title: str = Form(...),
    details: str = Form(...),
    tag: Tags = Form(...),
    image: UploadFile = File(None),
    source: TodoSource = Form(...),
):
    """Add new todo"""
    logger.info(
        "Creating todo: title= %s, details= %s, tag= %s, source= %s",
        title,
        details,
        tag,
        source,
    )

    await todo_service.create(
        uow_session=uow_session,
        title=title,
        details=details,
        tag=tag,
        source=source,
        image=image,
        author_id=user.id,
    )

    return {"status": "success", "details": "Todo added"}


@todo_router.get("/edit/{todo_id}/", status_code=status.HTTP_200_OK)
async def get_todo(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    user: Annotated[SUserInfo, Depends(get_current_active_user)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    todo_id: int,
    limit: int = 10,
    skip: int = 0,
):
    """Get todo"""
    todo, images = await todo_service.get_todo_for_edit(
        uow_session=uow_session,
        todo_id=todo_id,
        user=user,
    )

    logger.info("Getting todo: %s", todo)
    todo = enrich_todo_display(todo)

    return templates.TemplateResponse(
        "edit.html",
        {
            "request": request,
            "todo": todo,
            "tags": Tags,
            "limit": limit,
            "skip": skip,
            "images": images,
        },
    )


@todo_router.put("/edit/{todo_id}/", status_code=status.HTTP_200_OK)
async def edit_todo(
    user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    todo_id: int,
    title: str = Form(None),
    details: str = Form(None),
    completed: bool = Form(False),
    tag: Tags = Form(None),
    created_at: datetime = Form(None),
    image_path: str = Form(None),
    existing_image: str = Form(None),
    image: UploadFile = File(None),
):
    """Edit todo"""
    todo = await todo_service.update(
        uow_session=uow_session,
        user=user,
        todo_id=todo_id,
        title=title,
        details=details,
        completed=completed,
        tag=tag,
        created_at=created_at,
        image_path=image_path,
        existing_image=existing_image,
        image=image,
    )
    return {"status": "success", "details": "Todo edited"}


@todo_router.delete("/delete/{todo_id}/", status_code=status.HTTP_200_OK)
async def delete_todo(
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    todo_id: int,
    limit: int = 10,
    skip: int = 0,
) -> dict[str, Any]:
    """Удаление задачи только ее владельцем"""

    todo = await todo_service.delete(
        uow_session=uow_session, todo_id=todo_id, current_user=current_user
    )
    return {
        "status": "success",
        "details": "Todo deleted",
        "deleted_todo_title": todo.title,
        "deleted_for_user_email": current_user.email,
        "limit": limit,
        "skip": skip,
    }


@todo_router.delete("/delete/", status_code=status.HTTP_200_OK)
async def delete_todos(
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    limit: int = 10,
    skip: int = 0,
    start: int = 0,
    end: int = 0,
):
    """Удаление всех задач текущего пользователя"""

    deleted_count = await todo_service.delete_all_user_todos(
        uow_session=uow_session,
        current_user=current_user,
    )

    return {
        "status": "success",
        "deleted_count": deleted_count,
        "details": f"Successfully deleted {deleted_count} todos",
        "deleted_for_user_id": current_user.id,
        "deleted_for_user_email": current_user.email,
        "deleted_scope": "all" if current_user.role == UserRole.ADMIN else "own",
    }


@todo_router.get("/visualize/", status_code=status.HTTP_200_OK)
async def visualize_todos(
    days: int = 30,
):
    """Публичная точка входа в визуализацию активности пользователей."""
    return RedirectResponse(
        url=f"/todo/notes-per-day/?days={days}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@todo_router.get("/generate/", status_code=status.HTTP_200_OK)
async def show_generate(request: Request):
    return templates.TemplateResponse("generate.html", {"request": request})


@todo_router.post("/generate/", status_code=status.HTTP_200_OK)
async def generate_todos(
    user: Annotated[SUserInfo, Depends(get_current_active_user)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    count: int = Form(20),
):
    """Generate a number of random todos for the current user."""
    if count < 1 or count > 200:
        raise HTTPException(status_code=422, detail="Count must be between 1 and 200")

    logger.info("Generating %s todos for user %s", count, user.id)
    try:
        await todo_service.generate_random_todos(
            uow_session=uow_session,
            count=count,
            author_id=user.id,
        )
        logger.info("Todos generated successfully")
        return {"status": "success", "details": f"Generated {count} todos"}
    except Exception as e:
        logger.error("An error occurred during todo generation: %s", e)
        raise HTTPException(
            status_code=500, detail="An error occurred while generating todos"
        )


@todo_router.get("/export/", status_code=status.HTTP_200_OK)
async def visualize_todos(request: Request):
    """Page export and import todos from excel file"""
    return templates.TemplateResponse("export.html", {"request": request})


@todo_router.post("/import")
async def import_file(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    file: UploadFile = File(...),
):
    file_location = os.path.join("./files/", file.filename)
    with open(file_location, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    todos = import_todos(file_location)

    for todo in todos:
        await uow_session.todo.add(todo)

    return RedirectResponse("/todo/home", status_code=status.HTTP_303_SEE_OTHER)


@todo_router.get("/import-log")
async def import_file(request: Request):
    files = os.listdir("./files/")
    return templates.TemplateResponse(
        "import-log.html", {"request": request, "files": files}
    )


@todo_router.get("/import-log/{filename}")
async def import_file(filename: str):
    file_location = os.path.join("./files/", filename)
    return FileResponse(
        path=file_location,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@todo_router.post("/export/")
async def export_data(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    if current_user.role == UserRole.VIEWER:
        todos = await uow_session.todo.get_todos_by_author_id(current_user.id)
    else:
        todos = await uow_session.todo.get_all()

    export_todos(todos)

    return FileResponse(
        "data/todos.xlsx",
        filename=datetime.now().strftime("%Y_%m_%d_%H_%M_%S") + ".xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
