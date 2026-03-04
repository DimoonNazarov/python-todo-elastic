from fastapi import APIRouter, Depends, HTTPException, Request, Form, status
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
from typing import Annotated

from app.dependencies import get_auth_service
from app.exceptions import UserAlreadyExists, InactiveUserException, InvalidCredentials
from app.utils import OAuth2PasswordBearerWithCookie
from app.schemas import User, SUserRegister, SUserAuth
from app.core import get_async_uow_session, UnitOfWork
from app.services import AuthService

# pylint: disable=invalid-name
templates = Jinja2Templates(directory="app/templates")

auth_router = APIRouter(prefix="/auth", tags=["Auth"])

oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="token")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    uow_session: UnitOfWork = Depends(get_async_uow_session),
):
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


@auth_router.get("/login", status_code=status.HTTP_200_OK)
async def get_home(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@auth_router.post("/token", response_class=HTMLResponse)
async def login(
    request: Request,
    user_data: SUserAuth,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):

    user_agent = request.headers.get("User-Agent")
    ip_address = request.client.host if request.client else None

    try:
        tokens = await auth_service.login_user(
            user_data=user_data,
            user_agent=user_agent,
            ip_address=ip_address,
            uow_session=uow_session,
        )
    except InvalidCredentials:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Incorrect username or password"},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except InactiveUserException:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Inactive user"},
            status_code=400,
        )

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {tokens.access_token}",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=tokens.expires_in,
        path="/",
    )

    response.set_cookie(
        key="refresh_token",
        value=f"Bearer {tokens.refresh_token}",
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=tokens.expires_in,
        path="/auth/refresh",
    )
    return response


@auth_router.get("/register", response_class=HTMLResponse)
async def get_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@auth_router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    user_data: SUserRegister,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    try:
        await auth_service.register_user(uow_session=uow_session, user_data=user_data)
    except UserAlreadyExists:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username already registered"},
            status_code=400,
        )

    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)


@auth_router.get("/logout")
async def login(
    current_user: Annotated[User, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    await auth_service.logout(username=current_user.name, uow_session=uow_session)

    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("access_token")
    return response


@auth_router.get("/users/me")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_active_user)],
):
    return current_user
