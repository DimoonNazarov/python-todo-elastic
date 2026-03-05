import secrets
from typing import Optional
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError, ExpiredSignatureError

from app.config import settings
from logging import getLogger

logger = getLogger(__name__)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создает JWT Access Token"""

    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update(
        {
            "exp": expire,
            "iat": datetime.now(timezone.utc),
            "sub": str(data["user_id"]),
            "email": data["email"],
            "role": data["role"],
            "is_active": data.get("is_active", True),
            "token_type": "access",
        }
    )

    encoded_jwt = jwt.encode(
        to_encode,
        key=settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    return encoded_jwt


def create_refresh_token() -> str:
    """Создает случайный Refresh Token"""
    return secrets.token_urlsafe(48)


def verify_access_token(token: str) -> dict | None:
    """
    Проверяет JWT токен и возвращает payload если токен валидный

    Args:
        token: JWT токен для проверки

    Returns:
        dict: payload токена или None если токен невалидный
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        logger.error([payload])
        return payload

    except ExpiredSignatureError:
        logger.error("Token has expired")
        return None
    except JWTError as e:
        logger.error("Invalid token: %s", e)
        return None


# async def get_current_user(
#     token: str = Depends(get_access_token),
#     session: AsyncSession = Depends(get_session_without_commit),
# ) -> User:
#     """Проверяем access_token и возвращаем пользователя."""
#     try:
#         # Декодируем токен
#         payload = jwt.decode(
#             token, app_settings.JWT_SECRET_KEY, algorithms=[app_settings.JWT_ALGORITHM]
#         )
#     except ExpiredSignatureError:
#         raise TokenExpiredException
#     except JWTError:
#         # Общая ошибка для токенов
#         raise NoJwtException
#
#     expire: str = payload.get("exp")
#     expire_time = datetime.fromtimestamp(int(expire), tz=timezone.utc)
#     if (not expire) or (expire_time < datetime.now(timezone.utc)):
#         raise TokenExpiredException
#
#     user_id: str = payload.get("sub")
#     if not user_id:
#         raise NoUserIdException
#
#     user = await UserRepository(session).find_one_or_none_by_id(user_id=int(user_id))
#     if not user:
#         raise UserNotFoundException
#     return user
#
#
# async def get_admin_user(
#     current_user: User = Depends(get_current_user),
# ) -> TokenData:
#     if current_user.role != UserRole.ADMIN:
#         raise HTTPException(status_code=403, detail="Admin access required")
#     return TokenData(
#         id=current_user.id, email=current_user.email, role=current_user.role
#     )
#
#
# async def get_editor_user(
#     current_user: User = Depends(get_current_user),
# ) -> TokenData:
#     if current_user.role not in [UserRole.ADMIN, UserRole.EDITOR]:
#         raise HTTPException(status_code=403, detail="Editor access required")
#     return TokenData(
#         id=current_user.id, email=current_user.email, role=current_user.role
#     )
#
#
# async def get_viewer_user(
#     current_user: User = Depends(get_current_user),
# ) -> TokenData:
#     return TokenData(
#         id=current_user.id, email=current_user.email, role=current_user.role
#     )
