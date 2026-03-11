import logging
from datetime import datetime, UTC, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.repository import AuthRepository
from app.repository.token_repository import TokenRepository
from app.schemas import SUserRegister, SUserAuth, Token
from app.core import UnitOfWork
from app.models import User
from app.exceptions import (
    UserAlreadyExists,
    InactiveUserException,
    IncorrectEmailOrPasswordException,
    InvalidCredentials,
)
from app.utils import (
    verify_password,
    create_access_token,
    create_refresh_token,
    get_password_hash,
)

logger = logging.getLogger(__name__)


class AuthService:
    """Auth service"""

    async def login_user(
        self,
        user_data: SUserAuth,
        user_agent: str | None = None,
        ip_address: str | None = None,
        uow_session: UnitOfWork | None = None,
    ) -> Token:
        """Аутентифицирует пользователя и возвращает токены."""

        async with uow_session.start():
            user = await uow_session.auth.find_by_email(email=user_data.email)

            if not user or not verify_password(
                user_data.password, user.hashed_password
            ):
                raise IncorrectEmailOrPasswordException

            token_data = {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
            }

            access_token = create_access_token(data=token_data)
            refresh_token = create_refresh_token()

            refresh_token_expires = datetime.now(UTC) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )
            await uow_session.token.create_refresh_token(
                refresh_token=refresh_token,
                user_id=user.id,
                expires_at=refresh_token_expires,
                user_agent=user_agent,
                ip_address=ip_address,
            )

            logger.info("Refresh token создан для %s", user.email)

        logger.info("Пользователь %s успешно вошел в систему", user.email)

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register_user(
        self, uow_session: UnitOfWork, user_data: SUserRegister
    ) -> None:
        """Регистрирует нового пользователя."""
        async with uow_session.start():

            if await uow_session.auth.find_by_email(email=user_data.email):
                raise UserAlreadyExists()

            hashed_password = get_password_hash(user_data.password)

            user = User(
                email=user_data.email,
                hashed_password=hashed_password,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
            )

            await uow_session.auth.add_user(user)

    async def logout(
        self,
        *,
        refresh_token: str | None,
        uow_session: UnitOfWork,
    ) -> None:
        async with uow_session.start():
            if refresh_token:
                await uow_session.token.revoke_refresh_token(
                    refresh_token=refresh_token
                )

    async def logout_all_devices(
        self,
        *,
        user_id: int,
        uow_session: UnitOfWork,
    ) -> None:
        async with uow_session.start():
            await uow_session.token.revoke_all_user_tokens(user_id=user_id)

    async def refresh_tokens(
        self,
        *,
        refresh_token: str,
        uow_session: UnitOfWork,
    ) -> Token:
        async with uow_session.start():
            token_record = await uow_session.token.validate_refresh_token(refresh_token)
            if not token_record:
                raise InvalidCredentials("Invalid or expired refresh token")

            user = await uow_session.auth.find_one_or_none_by_id(token_record.user_id)
            if not user or not user.is_active:
                raise InvalidCredentials("User not found or inactive")

            # Ротация — старый отзываем, создаём новый
            await uow_session.token.revoke_refresh_token(refresh_token)

            new_refresh_token = create_refresh_token()
            expires_at = datetime.now(UTC) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )

            await uow_session.token.create_refresh_token(
                refresh_token=new_refresh_token,
                user_id=user.id,
                expires_at=expires_at,
            )

            token_data = {
                "user_id": user.id,
                "email": user.email,
                "role": user.role,
                "is_active": user.is_active,
            }
            access_token = create_access_token(data=token_data)

        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
