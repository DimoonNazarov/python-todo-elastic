"""Main of todo app
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from app.router import todo_router
from app.auth import auth_router
from app.utils import create_dirs

app = FastAPI()


@app.get("/")
async def main_page():
    return RedirectResponse("/todo/home", status_code=303)


app.include_router(todo_router)
app.include_router(auth_router)

create_dirs()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.mount("/images", StaticFiles(directory="images"), name="images")
