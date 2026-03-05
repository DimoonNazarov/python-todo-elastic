from starlette import status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from fastapi import Request, Response
from starlette.datastructures import URL
from starlette.responses import JSONResponse
from logging import getLogger
from app.utils import verify_access_token

logger = getLogger(__name__)


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    """
    Извлекает JWT токен из заголовка Authorization.

    Ожидаемый формат: "Bearer <token>"

    Args:
        authorization_header: значение заголовка Authorization

    Returns:
        Токен или None, если заголовок отсутствует или имеет неверный формат
    """
    if authorization_header is None:
        logger.error("Auth Middleware: authorization_header is None")
        return None

    parts = authorization_header.strip().split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        logger.error("Auth Middleware: authorization_header is not Bearer")
        return None
    return parts[1]


def extract_token(request: Request) -> str | None:
    """
    Извлекает JWT токен из запроса (сначала из cookie, потом из header)
    """
    # Сначала пробуем из cookie
    token = request.cookies.get("access_token")
    if token:
        logger.debug("Token found in cookie")
        return _extract_bearer_token(token)

    auth_header = request.headers.get("Authorization")
    if auth_header:
        logger.debug("Token found in Authorization header")
        return _extract_bearer_token(auth_header)

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
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:

        original_path = request.url.path
        normalized_path = original_path.rstrip("/")

        if original_path != normalized_path:
            _normalize_path(
                request=request,
                original_path=original_path,
                normalized_path=normalized_path,
            )
        if normalized_path in self.PUBLIC_PATHS:
            return await call_next(request)

        error_response, user_payload = _check_authorization(request=request)

        if error_response:
            return error_response

        request.state.user = user_payload

        response = await call_next(request)
        return response
