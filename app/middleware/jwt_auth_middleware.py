from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from fastapi import Request, Response
from starlette.datastructures import URL
from starlette.responses import JSONResponse, RedirectResponse
from logging import getLogger
from app.utils import verify_access_token, extract_bearer_token

logger = getLogger(__name__)


def extract_token(request: Request) -> str | None:
    """
    Извлекает JWT токен из запроса (сначала из cookie, потом из header)
    """
    # Сначала пробуем из cookie
    token = request.cookies.get("access_token")
    if token:
        logger.debug("Token found in cookie")
        return extract_bearer_token(token)

    auth_header = request.headers.get("Authorization")
    if auth_header:
        logger.debug("Token found in Authorization header")
        return extract_bearer_token(auth_header)

    logger.debug("No token found in request")
    return None


def _normalize_path(request: Request, original_path: str, normalized_path: str) -> None:
    """Нормализует путь запроса"""

    new_url = str(request.url).replace(original_path, normalized_path, 1)
    request.scope["path"] = normalized_path
    request.scope["raw_path"] = normalized_path.encode()
    request._url = URL(new_url)

    # Обновляем путь в scope для дальнейшей обработки
    request.scope["path"] = normalized_path
    request.scope["raw_path"] = normalized_path.encode()


def _check_authorization(request: Request) -> tuple[JSONResponse | None, dict | None]:
    """
    Проверяет авторизацию запроса.

    Returns:
        tuple: (error_response, user_payload)
        - Если ошибка: (JSONResponse, None)
        - Если успех: (None, user_payload)
    """

    token = extract_token(request)
    if not token:
        return (
            JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            ),
            None,
        )
    user_payload = verify_access_token(token)
    if not user_payload:
        return (
            JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired authentication token"},
                headers={"WWW-Authenticate": "Bearer"},
            ),
            None,
        )
    return None, user_payload

def _is_browser_request(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept

class JwtAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware для проверки JWT токенов

    Применяется ко ВСЕМ запросам, кроме публичных endpoints.

    Публичные endpoints (не требуют токен):
    - POST /auth/register
    - POST /auth/login
    - POST /auth/refresh
    - GET /health

    Для защищенных endpoints:
    1. Извлекает токен из Authorization header
    2. Проверяет JWT локально (verify_jwt_token)
    3. Сохраняет данные пользователя в request.state.user
    4. Передает запрос дальше (к proxy)
    """

    PUBLIC_PATHS = {
        "/docs",
        "/redoc",
        "/health",
        "/openapi.json",
        "/favicon.ico",
        "/auth/register",
        "/auth/login",
        "/auth/token",
        "/auth/refresh",
        "/auth/logout",
        "/auth/refresh-and-redirect",
    }

    # Пути к статике тоже публичные
    PUBLIC_PREFIXES = ("/static/",)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        path = request.url.path

        # Публичные пути — пропускаем
        if path in self.PUBLIC_PATHS or any(
            path.startswith(p) for p in self.PUBLIC_PREFIXES
        ):
            _, user_payload = _check_authorization(request)
            if user_payload is not None:
                request.state.user = user_payload
            return await call_next(request)

        # Проверяем авторизацию
        error_response, user_payload = _check_authorization(request)

        # Если есть ошибка — не авторизован
        if error_response is not None:
            is_browser = _is_browser_request(request)

            if is_browser:
                # Браузерный запрос — редирект на refresh endpoint
                # Он сам проверит есть ли refresh_token в куках
                next_url = request.url.path
                if request.url.query:
                    next_url += f"?{request.url.query}"
                return RedirectResponse(
                    url=f"/auth/refresh-and-redirect?next={next_url}",
                    status_code=302,
                )
            else:
                # API/fetch — 401, JS обработает
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Token expired"},
                    headers={"WWW-Authenticate": "Bearer"},
                )

        # Успешная авторизация
        request.state.user = user_payload
        return await call_next(request)
