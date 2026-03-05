from fastapi import Request
from fastapi.responses import JSONResponse
from app.exceptions import NotFoundException, InvalidPageException


async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, NotFoundException)
    return JSONResponse(status_code=404, content={"detail": str(exc)})


async def invalid_page_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, InvalidPageException)
    return JSONResponse(status_code=404, content={"det ail": str(exc)})
