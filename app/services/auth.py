import logging
from datetime import datetime, UTC, timedelta, timezone

from app.config import settings
from app.schemas import SUserRegister, SUserAuth, SUserInfo, Token, UserRole
from app.core import UnitOfWork
from app.models import User, RefreshToken
from app.exceptions import (
    UserAlreadyExists,
    InactiveUserException,
    IncorrectEmailOrPasswordException,
    InvalidCredentials,
    ForbiddenException,
    NotFoundException,
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

    @staticmethod
    def _resolve_role_for_new_user(
        *,
        users_count: int,
        current_user: SUserInfo | None,
        requested_role: UserRole | None,
    ) -> UserRole:
        if users_count == 0:
            return UserRole.ADMIN

        if current_user and current_user.role == UserRole.ADMIN:
            return requested_role or UserRole.EDITOR

        return UserRole.EDITOR

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
            await uow_session.token.add(RefreshToken(
                refresh_token=refresh_token,
                user_id=user.id,
                expires_at=refresh_token_expires,
                user_agent=user_agent,
                ip_address=ip_address,
                revoked=False,
            ))

            logger.info("Refresh token создан для %s", user.email)

        logger.info("Пользователь %s успешно вошел в систему", user.email)

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def register_user(
        self,
        uow_session: UnitOfWork,
        user_data: SUserRegister,
        current_user: SUserInfo | None = None,
    ) -> User:
        """Регистрирует нового пользователя."""
        async with uow_session.start():
            if await uow_session.auth.find_by_email(email=user_data.email):
                raise UserAlreadyExists()

            users_count = await uow_session.auth.count()
            if users_count > 0 and (
                current_user is None or current_user.role != UserRole.ADMIN
            ):
                raise ForbiddenException("Создавать пользователей может только администратор")

            hashed_password = get_password_hash(user_data.password)
            role = self._resolve_role_for_new_user(
                users_count=users_count,
                current_user=current_user,
                requested_role=user_data.role,
            )

            user = User(
                email=user_data.email,
                hashed_password=hashed_password,
                first_name=user_data.first_name,
                last_name=user_data.last_name,
                role=role,
            )

            await uow_session.auth.add_user(user)
            return user

    async def logout(
        self,
        *,
        refresh_token: str | None,
        uow_session: UnitOfWork,
    ) -> None:
        async with uow_session.start():
            if refresh_token:
                token = await uow_session.token.find_by_token(refresh_token)
                if token:
                    token.revoked = True

    async def logout_all_devices(
        self,
        *,
        user_id: int,
        uow_session: UnitOfWork,
    ) -> None:
        async with uow_session.start():
            tokens = await uow_session.token.get_by_user_id(user_id)
            for token in tokens:
                token.revoked = True

    async def refresh_tokens(
        self,
        *,
        refresh_token: str,
        uow_session: UnitOfWork,
    ) -> Token:
        async with uow_session.start():
            token_record = await uow_session.token.find_by_token(refresh_token)
            if not token_record or token_record.revoked or token_record.expires_at < datetime.now(UTC):
                raise InvalidCredentials("Invalid or expired refresh token")

            user = await uow_session.auth.find_one_or_none_by_id(token_record.user_id)
            if not user or not user.is_active:
                raise InvalidCredentials("User not found or inactive")

            # Ротация — старый отзываем, создаём новый
            token_record.revoked = True

            new_refresh_token = create_refresh_token()
            expires_at = datetime.now(UTC) + timedelta(
                days=settings.REFRESH_TOKEN_EXPIRE_DAYS
            )

            await uow_session.token.add(RefreshToken(
                refresh_token=new_refresh_token,
                user_id=user.id,
                expires_at=expires_at,
                user_agent=token_record.user_agent,
                ip_address=token_record.ip_address,
                revoked=False,
            ))

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

    async def delete_user(
        self,
        *,
        user_id: int,
        current_user: SUserInfo,
        uow_session: UnitOfWork,
    ) -> dict:
        async with uow_session.start():
            user = await uow_session.auth.find_one_or_none_by_id(user_id)
            if not user:
                raise NotFoundException("Пользователь не найден")

            can_delete_user = current_user.role == UserRole.ADMIN or current_user.id == user_id
            if not can_delete_user:
                raise ForbiddenException("Удалять пользователей может только администратор или сам пользователь")

            if user.role == UserRole.ADMIN:
                admin_count = await uow_session.auth.count({"role": UserRole.ADMIN})
                if admin_count <= 1:
                    raise ForbiddenException("Нельзя удалить последнего администратора")

            authored_todos = await uow_session.todo.get_todos_by_author_id(user_id)

            for todo in authored_todos:
                await uow_session.elastic.delete_todo(todo.id)

            await uow_session.todo.clear_updated_by_for_user(user_id)
            await uow_session.todo.delete_by_author_id(user_id)
            await uow_session.token.delete_by_user_id(user_id)
            await uow_session.auth.delete_by_id(user_id)

            return {
                "deleted_user_id": user.id,
                "deleted_user_email": user.email,
                "deleted_user_name": f"{user.first_name} {user.last_name}".strip(),
                "deleted_todos_count": len(authored_todos),
                "deleted_current_user": current_user.id == user_id,
            }

    async def update_user_role(
        self,
        *,
        user_id: int,
        new_role: UserRole,
        current_user: SUserInfo,
        uow_session: UnitOfWork,
    ) -> dict:
        if current_user.role != UserRole.ADMIN:
            raise ForbiddenException("Назначать роли может только администратор")

        async with uow_session.start():
            user = await uow_session.auth.find_one_or_none_by_id(user_id)
            if not user:
                raise NotFoundException("Пользователь не найден")

            if user.role == new_role:
                return {
                    "updated_user_id": user.id,
                    "updated_user_email": user.email,
                    "updated_user_name": f"{user.first_name} {user.last_name}".strip(),
                    "role": user.role.value,
                }

            if user.role == UserRole.ADMIN and new_role != UserRole.ADMIN:
                admin_count = await uow_session.auth.count({"role": UserRole.ADMIN})
                if admin_count <= 1:
                    raise ForbiddenException("Нельзя снять роль у последнего администратора")

            await uow_session.auth.update_by_id(user.id, {"role": new_role})

            return {
                "updated_user_id": user.id,
                "updated_user_email": user.email,
                "updated_user_name": f"{user.first_name} {user.last_name}".strip(),
                "role": new_role.value,
            }
