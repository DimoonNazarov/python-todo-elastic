import logging
from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.engine import CursorResult
from datetime import datetime, timezone

from app.models import RefreshToken

logger = logging.getLogger(__name__)


class TokenRepository:
    """Репозиторий для работы с refresh tokens"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_refresh_token(
        self,
        refresh_token: str,
        user_id: int,
        expires_at: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> RefreshToken | None:
        """
        Создать новый refresh token

        Args:
            refresh_token: Строка refresh токена
            user_id: ID пользователя
            expires_at: Время истечения токена
            user_agent: User agent клиента
            ip_address: IP адрес клиента

        Returns:
            Созданный RefreshToken
        """

        try:
            token_record = RefreshToken(
                refresh_token=refresh_token,
                user_id=user_id,
                expires_at=expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
                revoked=False,
            )

            self._session.add(token_record)
            await self._session.flush()

            logger.info(
                "Создан refresh token для пользователя %d с ID %d",
                user_id,
                token_record.id,
            )
            return token_record

        except SQLAlchemyError as e:
            logger.error("Ошибка при создании refresh token: %s", e)

    async def find_by_token(self, refresh_token: str) -> RefreshToken | None:
        """
        Найти refresh token по значению

        Args:
            refresh_token: Строка токена

        Returns:
            RefreshToken или None если не найден
        """
        try:
            query = select(RefreshToken).where(
                RefreshToken.refresh_token == refresh_token
            )
            result = await self._session.execute(query)
            token = result.scalar_one_or_none()

            if token:
                logger.debug("Refresh token найден: ID %s", token.id)
            else:
                logger.debug("Refresh token не найден")

            return token
        except SQLAlchemyError as e:
            logger.error("Ошибка при поиске refresh token: %s", e)
            raise

    async def validate_refresh_token(self, refresh_token: str) -> RefreshToken | None:
        """
        Проверить валидность refresh token

        Args:
            refresh_token: Строка токена

        Returns:
            RefreshToken если валиден, None если невалиден
        """
        token = await self.find_by_token(refresh_token)

        if not token:
            logger.warning("Refresh token не найден в БД")
            return None
        if token.revoked:
            logger.warning("Refresh token %s был отозван", token.id)
            return None
        if token.expires_at < datetime.now(timezone.utc):
            logger.warning("Refresh token %s истек", token.id)
            return None

        logger.debug("Refresh token %s валиден", token.id)
        return token

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """
        Отозвать refresh token

        Args:
            refresh_token: Строка токена

        Returns:
            True если токен отозван, False если не найден
        """
        try:
            token = await self.find_by_token(refresh_token)
            if not token:
                logger.warning("Токен для отзыва не найден")
                return False
            token.revoked = True
            await self._session.flush()

            logger.info("Refresh token %s отозван", token.id)
            return True
        except SQLAlchemyError as e:
            logger.error("Ошибка при отзыве токена: {}".format(e))
            raise

    async def revoke_all_user_tokens(self, user_id: int) -> int:
        """
        Отозвать все refresh токены пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Количество отозванных токенов
        """
        try:
            tokens = await self.get_user_tokens(user_id=user_id, active_only=True)

            count = 0
            for token in tokens:
                count += 1
                token.revoked = True

            await self._session.flush()
            logger.info("Отозвано %s токенов для пользователя %s", count, user_id)

            return count
        except SQLAlchemyError as e:
            logger.error("Ошибка при отзыве всех токенов пользователя: %s", e)
            raise

    async def get_user_tokens(
        self, user_id: int, active_only: bool
    ) -> list[RefreshToken]:
        """
        Получить все refresh токены пользователя

        Args:
            user_id: ID пользователя
            active_only: Только активные токены (не отозванные и не истекшие)
        """
        try:
            query = select(RefreshToken).where(RefreshToken.user_id == user_id)

            if active_only:
                query = query.where(
                    RefreshToken.revoked == False,
                    RefreshToken.expires_at > datetime.now(timezone.utc),
                )

            result = await self._session.execute(query)
            tokens = result.scalars().all()

            logger.debug("Найдено %s токенов для пользователя %s", len(tokens), user_id)
            return list(tokens)
        except SQLAlchemyError as e:
            logger.error("Ошибка при получении токенов пользователя: %s", e)
            raise

    async def cleanup_expired_tokens(self) -> int:
        """
        Удалить все истекшие refresh токены

        Returns:
            Количество удаленных токенов
        """
        try:
            query = delete(RefreshToken).where(
                RefreshToken.expires_at < datetime.now(timezone.utc)
            )
            result: CursorResult = await self._session.execute(query)
            await self._session.flush()

            deleted_count = result.rowcount
            logger.info("Удалено %s истекших токенов", deleted_count)
            return deleted_count
        except SQLAlchemyError as e:
            logger.error("Ошибка при отзыве токена: %s", e)
            raise

    async def delete_token(self, refresh_token: str) -> bool:
        """
        Удалить refresh token из БД

        Args:
            refresh_token: Строка токена

        Returns:
            True если токен удален, False если не найден
        """
        try:
            query = delete(RefreshToken).filter_by(refresh_token=refresh_token)
            result = await self._session.execute(query)
            await self._session.flush()

            deleted: CursorResult = result.rowcount > 0
            if deleted:
                logger.info("Refresh token удален из БД")
            else:
                logger.warning("Refresh token для удаления не найден")

            return deleted
        except SQLAlchemyError as e:
            logger.error("Ошибка при удалении токена: %s", e)
            raise

    async def delete_all_user_tokens(self, user_id: int) -> int:
        """
        Удалить все refresh токены пользователя из БД.

        Args:
            user_id: ID пользователя

        Returns:
            Количество удаленных токенов
        """
        try:
            query = delete(RefreshToken).where(RefreshToken.user_id == user_id)
            result: CursorResult = await self._session.execute(query)
            await self._session.flush()

            deleted_count = result.rowcount or 0
            logger.info(
                "Удалено %s refresh токенов пользователя %s",
                deleted_count,
                user_id,
            )
            return deleted_count
        except SQLAlchemyError as e:
            logger.error("Ошибка при удалении токенов пользователя: %s", e)
            raise


    async def count_active_user_tokens(self, user_id: int) -> int:
        """
        Подсчитать количество активных токенов пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Количество активных токенов
        """
        tokens = await self.get_user_tokens(user_id=user_id, active_only=True)
        return len(tokens)
