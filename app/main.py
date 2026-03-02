"""Main of todo app
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.database import get_es_client
from app.elastic_repository import ElasticRepository
from app.router import todo_router
from app.elastic_router import elastic_router
from app.auth import auth_router
from app.utils import create_dirs


@asynccontextmanager
async def lifespan(app: FastAPI):
    # При старте — создаём индекс с нужным маппингом
    es = get_es_client()
    repo = ElasticRepository(es)
    await repo.ensure_index_exists()
    yield
    # При остановке
    from app.database import close_es_client
    await close_es_client()

app = FastAPI(lifespan=lifespan)


@app.get("/")
async def main_page():
    return RedirectResponse("/todo/home", status_code=303)


app.include_router(todo_router)
app.include_router(auth_router)
app.include_router(elastic_router)

create_dirs()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")
