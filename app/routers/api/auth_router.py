from urllib.parse import urlparse
from fastapi import APIRouter, Depends, Request, Form, status, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from typing import Annotated
from app.dependencies import get_auth_service
from app.exceptions import (
    UserAlreadyExists,
    InvalidCredentials,
)
from app.utils import OAuth2PasswordBearerWithCookie, extract_bearer_token
from app.schemas import User, SUserRegister, SUserAuth
from app.core import get_async_uow_session, UnitOfWork
from app.services import AuthService
from app.routers.dependencies import get_current_user
from app.config import settings
from app.schemas import Token

# pylint: disable=invalid-name
templates = Jinja2Templates(directory="app/templates")
auth_router = APIRouter(prefix="/auth", tags=["Auth"])
oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="token")


def _set_auth_cookies(response: Response, tokens: Token) -> None:
    """Устанавливает access и refresh куки на переданный response."""
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
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        path="/",
    )


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

    tokens = await auth_service.login_user(
        user_data=user_data,
        user_agent=user_agent,
        ip_address=ip_address,
        uow_session=uow_session,
    )

    response = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    _set_auth_cookies(response, tokens)
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
async def logout(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    raw = request.cookies.get("refresh_token")
    refresh_token = extract_bearer_token(raw) if raw else None

    await auth_service.logout(refresh_token=refresh_token, uow_session=uow_session)

    response = RedirectResponse("/auth/login", status_code=302)
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token", path="/")
    return response


@auth_router.post("/refresh")
async def refresh(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise InvalidCredentials("Refresh token missing")

    refresh_token = extract_bearer_token(raw)
    if not refresh_token:
        raise InvalidCredentials("Invalid refresh token format")

    tokens = await auth_service.refresh_tokens(
        refresh_token=refresh_token,
        uow_session=uow_session,
    )

    response = JSONResponse({"access_token": tokens.access_token})
    _set_auth_cookies(response, tokens)
    return response


@auth_router.get("/refresh-and-redirect")
async def refresh_and_redirect(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    request: Request,
    next: str = "/",
):
    # Защита от open redirect
    parsed = urlparse(next)
    if parsed.netloc:
        next = "/"

    raw = request.cookies.get("refresh_token")
    if not raw:
        raise InvalidCredentials("Refresh token missing")

    refresh_token = extract_bearer_token(raw)
    if not refresh_token:
        raise InvalidCredentials("Invalid refresh token format")

    try:
        tokens = await auth_service.refresh_tokens(
            refresh_token=refresh_token,
            uow_session=uow_session,
        )
    except Exception as e:
        response = RedirectResponse("/auth/login", status_code=302)
        response.delete_cookie("access_token")
        response.delete_cookie("refresh_token", path="/auth")
        return response

    response = RedirectResponse(url=next, status_code=status.HTTP_303_SEE_OTHER)
    _set_auth_cookies(response, tokens)
    return response


@auth_router.get("/users/me")
async def read_users_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return current_user
