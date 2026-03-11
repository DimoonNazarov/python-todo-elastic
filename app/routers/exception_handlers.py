from fastapi import Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.exceptions import (
    NotFoundException,
    InvalidPageException,
    IncorrectEmailOrPasswordException,
    ForbiddenException,
    InvalidCredentials,
    InactiveUserException,
    UserAlreadyExists,
)

templates = Jinja2Templates(directory="app/templates")


async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, NotFoundException)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


async def invalid_page_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidPageException)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


async def user_already_exists_handler(request: Request, exc: Exception) -> HTMLResponse:
    assert isinstance(exc, UserAlreadyExists)
    return templates.TemplateResponse(
        "register.html",
        {"request": request, "error": "Username already registered"},
        status_code=400,
    )


async def forbidden_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ForbiddenException)
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)}
    )


async def invalid_credentials_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidCredentials)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)}
    )


async def incorrect_email_or_password_handler(
    request: Request, exc: Exception
) -> HTMLResponse:
    """Глобальный обработчик для ошибок аутентификации - возвращает HTML"""
    assert isinstance(exc, IncorrectEmailOrPasswordException)
    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Incorrect username or password"},
        status_code=400,
    )


async def inactive_user_handler(request: Request, exc: Exception) -> HTMLResponse:
    """Глобальный обработчик для неактивных пользователей - возвращает HTML"""
    assert isinstance(exc, InactiveUserException)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Inactive user"}, status_code=403
    )
