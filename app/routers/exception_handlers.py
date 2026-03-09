from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.exceptions import (
    NotFoundException,
    InvalidPageException,
    IncorrectEmailOrPasswordException,
    ForbiddenException,
)


async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, NotFoundException)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)}
    )


async def invalid_page_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidPageException)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND, content={"det ail": str(exc)}
    )


async def invalid_credentials_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, IncorrectEmailOrPasswordException)
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"Incorrect email or password": str(exc)},
    )


async def forbidden_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ForbiddenException)
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN, content={"detail": str(exc)}
    )
