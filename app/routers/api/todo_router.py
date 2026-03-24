import base64
import logging
import io
from typing import Any
import squarify
import shutil
import matplotlib.pyplot as plt
import seaborn as sb
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
from app.services.search_index import enrich_todo_display_list
from app.services.search_index import merge_search_hits_with_todos
from app.services.todo import TodoService
from app.utils import (
    import_todos,
    export_todos,
)

todo_router = APIRouter(prefix="/todo", tags=["Todo"])

# pylint: disable=invalid-name
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)


async def _get_search_todos_from_hits(
    uow_session: UnitOfWork,
    hits: list[dict],
) -> list[dict]:
    todo_ids = [hit["todo_id"] for hit in hits]
    if not todo_ids:
        return []

    async with uow_session.start():
        todos = await uow_session.todo.get_todos_by_ids(todo_ids)
    return merge_search_hits_with_todos(hits, todos)


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
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    current_user: SUserInfo = Depends(get_current_active_user),
    limit: int = 10,
    skip: int = 0,
    created_from: str = None,
    created_to: str = None,
    tag: Tags = None,
    query: str | None = None,
    search_tag: str | None = None,
    search_date_from: str | None = None,
    todo_service: TodoService = Depends(get_todo_service),
):
    author_id = current_user.id if current_user.role == UserRole.VIEWER else None

    if query:
        hits = await uow_session.elastic.search_todos(
            query_text=query,
            tag=tag.value if tag else None,
            limit=limit,
            skip=skip,
            author_id=author_id,
        )
        todos = await _get_search_todos_from_hits(uow_session, hits)
        return templates.TemplateResponse(
            "todos.html",
            _todos_page_context(
                request,
                todos=todos,
                limit=limit,
                skip=0,
                pages=1,
                created_from=created_from,
                created_to=created_to,
                tag=tag,
                search_query=query,
                search_mode="query",
                subtitle=f"Результаты поиска по запросу: {query}",
            ),
        )

    if search_tag:
        results = enrich_todo_display_list(
            await uow_session.elastic.search_by_tag(
                search_tag.capitalize(),
                author_id=author_id,
            )
        )
        return templates.TemplateResponse(
            "todos.html",
            _todos_page_context(
                request,
                todos=results,
                limit=limit,
                skip=0,
                pages=1,
                created_from=created_from,
                created_to=created_to,
                tag=tag,
                search_mode="tag",
                subtitle=f"Результаты поиска по тегу: {search_tag.capitalize()}",
            ),
        )

    if search_date_from:
        date_from_dt = datetime.fromisoformat(search_date_from)
        results = enrich_todo_display_list(
            await uow_session.elastic.search_by_date(
                date_from_dt.isoformat(),
                author_id=author_id,
            )
        )
        return templates.TemplateResponse(
            "todos.html",
            _todos_page_context(
                request,
                todos=results,
                limit=limit,
                skip=0,
                pages=1,
                created_from=created_from,
                created_to=created_to,
                tag=tag,
                search_date_from=search_date_from,
                search_mode="date",
                subtitle=f"Результаты поиска после {date_from_dt.strftime('%d.%m.%Y %H:%M')}",
            ),
        )

    todos, skip, pages = await todo_service.get_todos(
        uow_session=uow_session,
        current_user=current_user,
        limit=limit,
        skip=skip,
        created_from=created_from,
        created_to=created_to,
        tag=tag,
    )

    return templates.TemplateResponse(
        "todos.html",
        _todos_page_context(
            request,
            todos=todos,
            limit=limit,
            skip=skip,
            pages=pages,
            created_from=created_from,
            created_to=created_to,
            tag=tag,
        ),
    )


@todo_router.get("/search/top-words/", status_code=status.HTTP_200_OK)
async def search_by_top_words(
    limit: int = 10,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    current_user: SUserInfo = Depends(get_current_active_user),
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
    days: int = 30,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    current_user: SUserInfo = Depends(get_current_active_user),
):
    """Страница с графиком активности пользователей"""
    try:
        author_id = current_user.id if current_user.role == UserRole.VIEWER else None
        data = await uow_session.elastic.get_notes_per_day(days, author_id=author_id)
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
        logger.error("Notes per day error: %s", e)
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


@todo_router.get("/api/notes-per-day/")
async def notes_per_day_api(
    days: int = 30,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    current_user: SUserInfo = Depends(get_current_active_user),
):
    """API endpoint для получения данных графика в JSON."""
    try:
        author_id = current_user.id if current_user.role == UserRole.VIEWER else None
        data = await uow_session.elastic.get_notes_per_day(days, author_id=author_id)
        return JSONResponse(
            {"data": data, "total": sum(item["count"] for item in data), "days": days}
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
    todo_id: int,
    limit: int = 10,
    skip: int = 0,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    user: SUserInfo = Depends(get_current_active_user),
):
    """Get todo"""
    async with uow_session.start():
        todo = await uow_session.todo.get_todo_by_id(todo_id)
        if not todo:
            logger.warning(f"Todo not found: {todo_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Not found todo by this id: {todo_id}",
            )

        images = await uow_session.todo.get_all_image_paths()

        if todo.author_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Вы можете редактировать только свои задачи",
            )

    logger.info(f"Getting todo: {todo}")
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
    todo_id: int,
    limit: int = 10,
    skip: int = 0,
    current_user: SUserInfo = Depends(get_current_active_user),
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    todo_service: TodoService = Depends(get_todo_service),
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
    todo_service: TodoService = Depends(get_todo_service),
    current_user: SUserInfo = Depends(get_current_active_user),
    uow_session: UnitOfWork = Depends(get_async_uow_session),
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
    request: Request,
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    current_user: SUserInfo = Depends(get_current_active_user),
):
    """Visualize todos as a treemap by tags"""
    author_id = current_user.id if current_user.role == UserRole.VIEWER else None
    todos = await uow_session.todo.get_many(limit=1000, skip=0, author_id=author_id)

    tag_counts = {tag.value: 0 for tag in Tags}
    for todo in todos:
        tag_counts[todo.tag] += 1

    tag_counts = {tag: count for tag, count in tag_counts.items() if count > 0}

    if not tag_counts:
        fig, ax = plt.subplots()
        ax.text(0.5, 0.5, "No todos available", ha="center", va="center", fontsize=18)
        plt.axis("off")
    else:
        fig, ax = plt.subplots()
        squarify.plot(
            sizes=list(tag_counts.values()),
            label=list(tag_counts.keys()),
            pad=0.2,
            text_kwargs={"fontsize": 10, "color": "white"},
            color=sb.color_palette("rocket", len(tag_counts)),
        )
        plt.axis("off")

    buf = io.BytesIO()
    plt.savefig(buf, format="png")
    buf.seek(0)
    plt.close(fig)

    image_url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
    return templates.TemplateResponse(
        "visualization.html", {"request": request, "image_url": image_url}
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
        raise HTTPException(
            status_code=422, detail="Count must be between 1 and 200"
        )

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
    file: UploadFile = File(...),
    uow_session: UnitOfWork = Depends(get_async_uow_session),
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
    uow_session: UnitOfWork = Depends(get_async_uow_session),
    current_user: SUserInfo = Depends(get_current_active_user),
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
