from fastapi import Request, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from app.exceptions import (
    NotFoundException,
    InvalidPageException,
    IncorrectEmailOrPasswordException,
    ForbiddenException,
    InvalidTodoDataException,
    InvalidCredentials,
    InactiveUserException,
    LLMConfigurationException,
    LLMRequestException,
    LLMServiceException,
    UserAlreadyExists,
)
from app.schemas import UserRole

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
        request,
        "register.html",
        {
            "error": "Username already registered",
            "can_choose_role": False,
            "default_role": UserRole.EDITOR.value,
            "first_user": False,
            "role_options": [
                {"value": UserRole.ADMIN.value, "label": "Администратор"},
                {"value": UserRole.EDITOR.value, "label": "Редактор"},
                {"value": UserRole.VIEWER.value, "label": "Пользователь"},
            ],
        },
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
        request,
        "login.html",
        {"error": "Incorrect username or password"},
        status_code=400,
    )


async def inactive_user_handler(request: Request, exc: Exception) -> HTMLResponse:
    """Глобальный обработчик для неактивных пользователей - возвращает HTML"""
    assert isinstance(exc, InactiveUserException)
    return templates.TemplateResponse(
        request, "login.html", {"error": "Inactive user"}, status_code=403
    )


async def llm_configuration_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, LLMConfigurationException)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


async def llm_service_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, LLMServiceException)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": str(exc)},
    )


async def llm_request_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, LLMRequestException)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


async def invalid_todo_data_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidTodoDataException)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )
