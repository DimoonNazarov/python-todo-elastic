import logging
import os
import shutil
from datetime import datetime
from typing import Annotated, Any
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
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from starlette.responses import HTMLResponse

from app.core import get_async_uow_session, UnitOfWork
from app.dependencies import get_todo_service
from app.routers.dependencies import get_current_user, get_current_active_user
from app.schemas import TodoSource, Todo, SUserInfo, UserRole
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

DAYS_RU = [
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
]
VALID_INTERVALS = {"day", "week", "month"}


def _group_todos_by_due_date(todos: list) -> list[dict]:
    """Группирует задачи по дате срока выполнения (due_at)."""
    from collections import defaultdict

    groups: dict = defaultdict(list)
    no_due = []

    for todo in todos:
        due_at = (
            getattr(todo, "due_at", None)
            if not isinstance(todo, dict)
            else todo.get("due_at")
        )
        if due_at:
            date_key = due_at.date() if hasattr(due_at, "date") else due_at
            groups[date_key].append(todo)
        else:
            no_due.append(todo)

    result = []
    for date_key in sorted(groups.keys()):
        day_name = DAYS_RU[date_key.weekday()]
        label = f"{day_name} {date_key.strftime('%d/%m/%Y')}"
        result.append({"label": label, "date": date_key, "todos": groups[date_key]})

    if no_due:
        result.append({"label": "Без срока", "date": None, "todos": no_due})

    return result


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

    grouped_todos = _group_todos_by_due_date(todos) if search_mode is None else None

    return {
        "request": request,
        "todos": todos,
        "grouped_todos": grouped_todos,
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


@todo_router.get("/home/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def get_home(request: Request):
    """Main page with todo list"""
    logger.info("In home")

    return templates.TemplateResponse("index.html", {"request": request})


@todo_router.get(
    "/401", response_class=HTMLResponse, status_code=status.HTTP_401_UNAUTHORIZED
)
async def page_401(request: Request):
    """Main page with todo list"""
    return templates.TemplateResponse("401.html", {"request": request})


@todo_router.get(
    "/info-tasks/", response_class=HTMLResponse, status_code=status.HTTP_200_OK
)
async def get_home(request: Request):
    """Main page with todo list"""

    return templates.TemplateResponse("info-tasks.html", {"request": request})


@todo_router.get("/list/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def get_todos(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    limit: int = 10,
    skip: int = 0,
    created_from: str = None,
    created_to: str = None,
    tag: str | None = None,
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


@todo_router.get(
    "/search/top-words/", response_class=JSONResponse, status_code=status.HTTP_200_OK
)
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
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    days: int = 30,
    interval: str = "day",
):
    """Страница с графиком активности пользователей"""
    if interval not in VALID_INTERVALS:
        interval = "day"
    result = await todo_service.get_notes_per_day(
        uow_session=uow_session,
        current_user=current_user,
        days=days,
        interval=interval,
    )
    return templates.TemplateResponse(
        "notes_per_day.html",
        {"request": request, **result, "days": days, "interval": interval},
    )


@todo_router.get("/api/notes-per-day/", response_class=JSONResponse)
async def notes_per_day_api(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    days: int = 30,
    interval: str = "day",
):
    """API endpoint для получения данных графика в JSON."""
    if interval not in VALID_INTERVALS:
        interval = "day"
    result = await todo_service.get_notes_per_day(
        uow_session=uow_session,
        current_user=current_user,
        days=days,
        interval=interval,
    )
    return JSONResponse(result)


@todo_router.get(
    "/tags/",
    response_class=HTMLResponse,
    dependencies=[Depends(get_current_active_user)],
)
async def tags_page(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
):
    """Страница управления тегами."""
    tags = await uow_session.elastic.get_all_tags()
    return templates.TemplateResponse("tags.html", {"request": request, "tags": tags})


@todo_router.get(
    "/api/tags/",
    response_class=JSONResponse,
    dependencies=[Depends(get_current_active_user)],
)
async def api_get_tags(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
):
    """JSON: список всех тегов."""
    tags = await uow_session.elastic.get_all_tags()
    return JSONResponse({"tags": tags})


@todo_router.get(
    "/api/tags/suggest/",
    response_class=JSONResponse,
    dependencies=[Depends(get_current_active_user)],
)
async def api_suggest_tags(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    q: str = "",
):
    """JSON: автодополнение тегов."""
    if not q.strip():
        tags = await uow_session.elastic.get_all_tags()
        return JSONResponse({"suggestions": tags[:10]})
    suggestions = await uow_session.elastic.suggest_tags(q.strip())
    return JSONResponse({"suggestions": suggestions})


@todo_router.post(
    "/api/tags/",
    response_class=JSONResponse,
    dependencies=[Depends(get_current_active_user)],
)
async def api_create_tag(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    name: str = Form(...),
):
    """JSON: создать тег."""
    name = name.strip()
    if not name:
        return JSONResponse(
            {"error": "Имя тега не может быть пустым."}, status_code=400
        )
    created = await uow_session.elastic.create_tag(name)
    if not created:
        return JSONResponse({"error": f"Тег «{name}» уже существует."}, status_code=409)
    return JSONResponse({"name": name, "created": True})


@todo_router.delete(
    "/api/tags/{tag_name}/",
    response_class=JSONResponse,
    dependencies=[Depends(get_current_active_user)],
)
async def api_delete_tag(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    tag_name: str,
):
    """JSON: удалить тег."""
    deleted = await uow_session.elastic.delete_tag(tag_name)
    if not deleted:
        return JSONResponse({"error": "Тег не найден."}, status_code=404)
    return JSONResponse({"deleted": True, "name": tag_name})


@todo_router.post("/add/", status_code=status.HTTP_201_CREATED)
async def add_todo(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    user: Annotated[SUserInfo, Depends(get_current_active_user)],
    title: str = Form(...),
    details: str = Form(...),
    tag: str = Form(""),
    image: UploadFile = File(None),
    source: TodoSource = Form(...),
    due_at: datetime | None = Form(None),
):
    """Add new todo"""
    tag = tag.strip() if tag and tag.strip() else "Планы"
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
        due_at=due_at,
    )

    return {"status": "success", "details": "Todo added"}


@todo_router.get(
    "/edit/{todo_id}/", response_class=HTMLResponse, status_code=status.HTTP_200_OK
)
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

    tags = await uow_session.elastic.get_all_tags()
    return templates.TemplateResponse(
        "edit.html",
        {
            "request": request,
            "todo": todo,
            "tags": tags,
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
    tag: str | None = Form(None),
    created_at: datetime = Form(None),
    image_path: str = Form(None),
    existing_image: str = Form(None),
    image: UploadFile = File(None),
):
    """Edit todo"""
    tag = tag.strip() if tag and tag.strip() else "Планы"
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


@todo_router.post("/summarize/{todo_id}/", status_code=status.HTTP_200_OK)
async def summarize_todo(
    todo_id: int,
    user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
):
    summary = await todo_service.summarize_with_spacy(
        uow_session=uow_session,
        todo_id=todo_id,
        user=user,
    )
    return {
        "status": "success",
        "details": "Spacy summary created",
        "spacy_summary": summary,
    }


@todo_router.delete("/delete/{todo_id}/", status_code=status.HTTP_200_OK)
async def delete_todo(
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    todo_service: Annotated[TodoService, Depends(get_todo_service)],
    todo_id: int,
    limit: int = 10,
    skip: int = 0,
) -> dict:
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


@todo_router.get(
    "/visualize/",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
)
async def visualize_todos(
    days: int = 30,
):
    """Публичная точка входа в визуализацию активности пользователей."""
    return RedirectResponse(
        url=f"/todo/notes-per-day/?days={days}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@todo_router.get("/generate/", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def show_generate(request: Request):
    return templates.TemplateResponse("generate.html", {"request": request})


@todo_router.post("/generate/", status_code=status.HTTP_201_CREATED)
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


@todo_router.get(
    "/export/", response_class=HTMLResponse, status_code=status.HTTP_200_OK
)
async def visualize_todos(request: Request):
    """Page export and import todos from excel file"""
    return templates.TemplateResponse("export.html", {"request": request})


@todo_router.post(
    "/import", response_class=RedirectResponse, status_code=status.HTTP_303_SEE_OTHER
)
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


@todo_router.get("/import-log",response_class=HTMLResponse)
async def import_file(request: Request):
    files = os.listdir("./files/")
    return templates.TemplateResponse(
        "import-log.html", {"request": request, "files": files}
    )


@todo_router.get("/import-log/{filename}", response_class=FileResponse)
async def import_file(filename: str):
    file_location = os.path.join("./files/", filename)
    return FileResponse(
        path=file_location,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@todo_router.post("/export/", response_class=FileResponse)
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
