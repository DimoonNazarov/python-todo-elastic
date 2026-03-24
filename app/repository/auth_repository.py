from collections.abc import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func

from sqlalchemy import update
from app.models import User


class AuthRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    # async def set_disabled(self, username: str, value: bool):
    #     await self._session.execute(
    #         update(User).where(User.name == username).values(disabled=value)
    #     )

    async def find_by_email(self, email: str) -> User | None:
        """Найти пользователя по email"""
        stmt = select(User).filter_by(email=email)
        result = await self._session.execute(stmt)

        return result.scalar_one_or_none()

    async def find_one_or_none_by_id(self, user_id: int) -> User | None:
        """Найти пользователя по ID"""
        stmt = select(User).filter_by(id=user_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_one_or_none(self, filter_dict: dict) -> User | None:
        """Найти одного пользователя по фильтрам"""
        stmt = select(User).filter_by(**filter_dict)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_all(self, filter_dict: dict = None) -> Sequence[User]:
        """Найти всех пользователей по фильтрам"""
        filter_dict = filter_dict or {}
        stmt = select(User).filter_by(**filter_dict)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add_user(self, user: User) -> None:
        """Добавить нового пользователя"""
        self._session.add(user)

    async def add_many(self, users: list[User]) -> None:
        """Добавить нескольких пользователей"""
        self._session.add(users)

    async def get_active_users(self) -> Sequence[User]:
        """Получить всех активных пользователей"""
        filter_dict = {"is_active": True}
        return await self.find_all(filter_dict=filter_dict)

    async def update(self, filter_dict: dict, update_dict: dict) -> int:
        """
        Обновить пользователей по фильтрам
        Returns:
            Количество обновленных записей
        """

        query = (
            update(User)
            .where(*[getattr(User, k) == v for k, v in filter_dict.items()])
            .values(**update_dict)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(query)
        return result.rowcount

    async def update_by_id(self, user_id: int, update_dict: dict) -> bool:
        """
        Обновить пользователя по ID
        Args:
            user_id: ID пользователя
            update_dict: Данные для обновления
        """
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(**update_dict)
            .execution_options(synchronize_session="fetch")
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def delete(self, filter_dict: dict) -> int:
        """Удалить пользователей по фильтрам"""

        stmt = delete(User).filter_by(**filter_dict)
        result = await self._session.execute(stmt)
        return result.rowcount

    async def delete_by_id(self, user_id: int) -> bool:
        """
        Удалить пользователя по ID

        Returns:
            True если пользователь удален, False если не найден
        """

        stmt = delete(User).filter_by(id=user_id)
        result = await self._session.execute(stmt)

        return result.rowcount > 0

    async def count(self, filter_dict: dict | None = None) -> int:
        """Подсчитать количество пользователей по фильтрам"""
        filter_dict = filter_dict or {}
        stmt = select(func.count(User.id)).filter_by(**filter_dict)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, filter_dict: dict) -> bool:
        """Проверить существование пользователя по фильтрам"""
        stmt = select(User.id).filter_by(**filter_dict).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar() is not None

    async def deactivate_user(self, user_id: int) -> bool:
        """Деактивировать пользователя по ID"""
        update_dict = {"is_active": False}
        return await self.update_by_id(user_id, update_dict=update_dict)

    #
    # async def change_user_role(self, user_id: int, new_role: UserRole) -> bool:
    #     """
    #     Изменить роль пользователя
    #
    #     Args:
    #         user_id: ID пользователя
    #         new_role: Новая роль пользователя
    #
    #     Returns:
    #         True если роль изменена, False если пользователь не найден
    #     """
    #     logger.info(f"Изменение роли пользователя {user_id} на {new_role}")
    #     return await self.update_by_id(user_id, SUserUpdate(role=new_role))
