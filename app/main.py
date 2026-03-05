"""Main of todo app"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.core.database import get_es_client
from app.repository.elastic_repository import ElasticRepository
from app.routers import todo_router, elastic_router, auth_router
from app.utils import create_dirs
from app.middleware import JwtAuthMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте — создаём индекс с нужным маппингом
    es = get_es_client()
    repo = ElasticRepository(es)
    await repo.ensure_index_exists()
    yield
    # При остановке
    from app.core.database import close_es_client

    await close_es_client()


app = FastAPI(lifespan=lifespan)
app.add_middleware(JwtAuthMiddleware)


@app.get("/")
async def main_page():
    return RedirectResponse("/todo/home", status_code=303)


app.include_router(todo_router)
app.include_router(auth_router)
app.include_router(elastic_router)

create_dirs()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")
