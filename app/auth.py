from fastapi import APIRouter
from typing import Annotated

from fastapi import Depends
from fastapi import HTTPException
from fastapi import Request
from fastapi import Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi import status
from starlette.responses import HTMLResponse

from app.utils import OAuth2PasswordBearerWithCookie
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas import User
from app.models import User as UserDb
from app.database import get_async_uow_session
from app.uow import UnitOfWork

# pylint: disable=invalid-name
templates = Jinja2Templates(directory="app/templates")

auth_router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)


def fake_hash_password(password: str):
    return "fakehashed" + password


oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="token")


def get_user(db, username: str):
    if username in db:
        user_dict = db[username]
        return user_dict


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)],
                           uow_session: UnitOfWork = Depends(get_async_uow_session)):
    user = await uow_session.auth.get_user(token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_active_user(
        current_user: Annotated[User, Depends(get_current_user)],
):
    if current_user.disabled:
        raise HTTPException(status_code=401, detail="Inactive user")
    return current_user


@auth_router.post("/token", response_class=HTMLResponse)
async def login( request: Request, form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                uow_session: UnitOfWork = Depends(get_async_uow_session)):
    user = await uow_session.auth.get_user(form_data.username)
    if not user:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect username or password"}, status_code=status.HTTP_400_BAD_REQUEST)
    if form_data.password != user.password:
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect username or password"}, status_code=status.HTTP_400_BAD_REQUEST)

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(key="access_token", value=f"Bearer {form_data.username}", httponly=True)
    await uow_session.auth.set_disabled(form_data.username, False)
    return response


@auth_router.get("/logout")
async def login(current_user: Annotated[User, Depends(get_current_active_user)],
                uow_session: UnitOfWork = Depends(get_async_uow_session), ):
    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("access_token")
    await uow_session.auth.set_disabled(current_user.name, True)
    return response


@auth_router.get("/login", status_code=status.HTTP_200_OK)
async def get_home(request: Request):
    return templates.TemplateResponse("login.html",
                                      {"request": request})


@auth_router.get("/users/me")
async def read_users_me(
        current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user

@auth_router.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@auth_router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    uow_session: UnitOfWork = Depends(get_async_uow_session)
):
    user = UserDb(name=username, password=password, disabled=False)

    existing_user = await uow_session.auth.get_user(username)
    if existing_user:
        return templates.TemplateResponse("register.html", {"request": request, "error": "Username already registered"},  status_code=status.HTTP_400_BAD_REQUEST)

    await uow_session.auth.add_user(user)

    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)