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
    InvalidCredentials,
    InactiveUserException,
    IncorrectEmailOrPasswordException,
)
from app.utils import verify_password, create_access_token, create_refresh_token

logger = logging.getLogger(__name__)


class AuthService:
    """Auth service"""

    def __init__(self, auth_repository: AuthRepository, token_repository: TokenRepository):
        self.auth_repo = auth_repository
        self.token_repo = token_repository

    async def login_user(
        self,
        user_data: SUserAuth,
        user_agent: str | None = None,
        ip_address: str | None = None,
        uow_session: UnitOfWork | None = None,
    ) -> Token:
        """Аутентифицирует пользователя и возвращает токены."""

        async with uow_session.start():
            user = await self.auth_repo.find_by_email(email=user_data.email)

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
            await self.token_repo.create_refresh_token(
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
            expires_in=auth_service_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register(self, *, username: str, password: str, uow_session: UnitOfWork):
        async with uow_session.start():
            existing_user = await uow_session.auth.get_user(username)
            if existing_user:
                raise UserAlreadyExists()

            user = User(username=username, password=password, disabled=False)

            await uow_session.auth.add_user(user)

    async def register_user(
        self, uow_session: UnitOfWork, user_data: SUserRegister
    ) -> User:
        """Регистрирует нового пользователя."""
        async with uow_session.start():

            if await self.auth_repo.find_by_email(email=user_data.email):
                raise UserAlreadyExists()

            hashed_password = get_password_hash(user_data.password)

            user = User(
                email=user_data.email,
                hashed_password=hashed_password,
                role=user_data.role,
            )

            await self.user_repo.add(user)

    async def login(self, *, username: str, password: str, uow_session: UnitOfWork):
        async with uow_session.start():
            user = await uow_session.auth.get_user(username)
            if not user or user.password != password:
                raise InvalidCredentials()

            if user.disabled:
                raise InactiveUser()

            await uow_session.auth.set_disabled(username, False)

            return user

    async def logout(
        self,
        *,
        username: str,
        uow_session: UnitOfWork,
    ) -> None:

        async with uow_session.start():
            await uow_session.auth.set_disabled(username, True)
