from urllib.parse import urlparse
from typing import Annotated
from fastapi import APIRouter, Depends, Request, status, Response
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from app.dependencies import get_auth_service
from app.exceptions import (
    InvalidCredentials,
)
from app.utils import (
    OAuth2PasswordBearerWithCookie,
    extract_bearer_token,
)
from app.schemas import (
    SUserRegister,
    SUserAuth,
    SUserInfo,
    SUserRoleUpdate,
    Token,
    UserRole,
)
from app.core import get_async_uow_session, UnitOfWork
from app.services import AuthService
from app.routers.dependencies import (
    get_current_active_user,
    get_optional_current_active_user,
)
from app.config import settings

# pylint: disable=invalid-name
templates = Jinja2Templates(directory="app/templates")
auth_router = APIRouter(prefix="/auth", tags=["Auth"])
oauth2_scheme = OAuth2PasswordBearerWithCookie(tokenUrl="token")


async def _build_register_context(
    request: Request,
    uow_session: UnitOfWork,
) -> dict:
    current_user = await get_optional_current_active_user(request, uow_session)
    async with uow_session.start():
        users_count = await uow_session.auth.count()

    first_user = users_count == 0
    can_choose_role = first_user or (
        current_user is not None and current_user.role == UserRole.ADMIN
    )
    default_role = UserRole.ADMIN.value if first_user else UserRole.EDITOR.value

    return {
        "request": request,
        "can_choose_role": can_choose_role,
        "default_role": default_role,
        "first_user": first_user,
        "role_options": [
            {"value": UserRole.ADMIN.value, "label": "Администратор"},
            {"value": UserRole.EDITOR.value, "label": "Редактор"},
            {"value": UserRole.VIEWER.value, "label": "Пользователь"},
        ],
        "current_user": current_user,
    }


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


@auth_router.get("/login", response_class=HTMLResponse, status_code=status.HTTP_200_OK)
async def get_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@auth_router.post(
    "/token", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND
)
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
async def get_register(
    request: Request,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
):
    context = await _build_register_context(request, uow_session)
    if not context["first_user"] and (
        context["current_user"] is None
        or context["current_user"].role != UserRole.ADMIN
    ):
        return RedirectResponse(
            url="/todo/home/", status_code=status.HTTP_303_SEE_OTHER
        )

    return templates.TemplateResponse(
        "register.html",
        context,
    )


@auth_router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    user_data: SUserRegister,
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
    current_user: Annotated[
        SUserInfo | None, Depends(get_optional_current_active_user)
    ],
):
    await auth_service.register_user(
        uow_session=uow_session,
        user_data=user_data,
        current_user=current_user,
    )

    return RedirectResponse(url="/auth/login", status_code=status.HTTP_303_SEE_OTHER)


@auth_router.get(
    "/logout", response_class=RedirectResponse, status_code=status.HTTP_302_FOUND
)
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


@auth_router.post(
    "/refresh", response_class=JSONResponse, status_code=status.HTTP_200_OK
)
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


@auth_router.get(
    "/refresh-and-redirect",
    response_class=RedirectResponse,
    status_code=status.HTTP_303_SEE_OTHER,
)
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


@auth_router.get(
    "/users/me", response_class=JSONResponse, status_code=status.HTTP_200_OK
)
async def read_users_me(
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
):
    return current_user


@auth_router.get(
    "/users/active", response_class=JSONResponse, status_code=status.HTTP_200_OK
)
async def read_active_users(
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
):
    async with uow_session.start():
        users = sorted(
            await uow_session.auth.get_active_users(),
            key=lambda user: (
                user.first_name.lower(),
                user.last_name.lower(),
                user.email.lower(),
            ),
        )

    return [
        {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role.value,
        }
        for user in users
    ]


@auth_router.patch(
    "/users/{user_id}/role", response_class=JSONResponse, status_code=status.HTTP_200_OK
)
async def update_user_role(
    user_id: int,
    role_data: SUserRoleUpdate,
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    updated_user = await auth_service.update_user_role(
        user_id=user_id,
        new_role=role_data.role,
        current_user=current_user,
        uow_session=uow_session,
    )
    return JSONResponse(updated_user)


@auth_router.delete(
    "/users/{user_id}", response_class=JSONResponse, status_code=status.HTTP_200_OK
)
async def delete_user(
    user_id: int,
    current_user: Annotated[SUserInfo, Depends(get_current_active_user)],
    uow_session: Annotated[UnitOfWork, Depends(get_async_uow_session)],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    deleted_user = await auth_service.delete_user(
        user_id=user_id,
        current_user=current_user,
        uow_session=uow_session,
    )

    response = JSONResponse(deleted_user)
    if deleted_user["deleted_current_user"]:
        response.delete_cookie("access_token", path="/")
        response.delete_cookie("refresh_token", path="/")
    return response
