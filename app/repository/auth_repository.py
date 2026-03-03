from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from sqlalchemy import update
from app.models import User
from app.schemas import SUserFilter


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
        """ Получить всех активных пользователей """
        filter_dict = {"is_active": True}
        return await self.find_all(filter_dict=filter_dict)

    # async def update(self, filters: SUserFilter, update_data: SUserUpdate) -> int:
    #     """
    #     Обновить пользователей по фильтрам
    #
    #     Args:
    #         filters: Фильтры для выбора пользователей
    #         update_data: Данные для обновления
    #
    #     Returns:
    #         Количество обновленных записей
    #     """
    #     filter_dict = filters.model_dump(exclude_unset=True)
    #     update_dict = update_data.model_dump(exclude_unset=True)
    #
    #     if not update_dict:
    #         logger.warning("Нет данных для обновления")
    #         return 0
    #     try:
    #         query = (
    #             update(User)
    #             .where(*[getattr(User, k) == v for k, v in filter_dict.items()])
    #             .values(**update_dict)
    #             .execution_options(synchronize_session="fetch")
    #         )
    #         result = await self._session.execute(query)
    #
    #         logger.info(f"Обновлено {result.rowcount} пользователей")
    #         await self._session.flush()
    #
    #         return result.rowcount
    #     except SQLAlchemyError as e:
    #         logger.error(f"Ошибка при обновлении пользователей: {e}")
    #         raise

    # async def update_by_id(self, user_id: int, update_data: SUserUpdate) -> bool:
    #     """
    #     Обновить пользователя по ID
    #
    #     Args:
    #         user_id: ID пользователя
    #         update_data: Данные для обновления
    #
    #     Returns:
    #         True если пользователь обновлен, False если не найден
    #     """
    #     update_dict = update_data.model_dump(exclude_unset=True)
    #
    #     if not update_dict:
    #         logger.warning("Нет данных для обновления")
    #         return False
    #
    #     logger.debug(
    #         f"Обновление пользователя с ID {user_id} с параметрами: {update_dict}"
    #     )
    #
    #     try:
    #         query = (
    #             update(User)
    #             .where(User.id == user_id)
    #             .values(**update_dict)
    #             .execution_options(synchronize_session="fetch")
    #         )
    #         result = await self._session.execute(query)
    #
    #         updated = result.rowcount > 0
    #         if updated:
    #             logger.info(f"Пользователь с ID {user_id} успешно обновлен")
    #         else:
    #             logger.warning(f"Пользователь с ID {user_id} не найден для обновления")
    #
    #         await self._session.flush()
    #
    #         return updated
    #     except SQLAlchemyError as e:
    #         logger.error(f"Ошибка при обновлении пользователя с ID {user_id}: {e}")
    #         raise
    #
    async def delete(self, filter_dict: dict) -> int:
        """ Удалить пользователей по фильтрам """

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

    # async def count(self, filters: Optional[SUserFilter] = None) -> int:
    #     """
    #     Подсчитать количество пользователей по фильтрам
    #
    #     Args:
    #         filters: Фильтры для подсчета (опционально)
    #
    #     Returns:
    #         Количество пользователей
    #     """
    #     filter_dict = filters.model_dump(exclude_unset=True) if filters else {}
    #     logger.debug(f"Подсчет количества пользователей по фильтру: {filter_dict}")
    #
    #     try:
    #         query = select(func.count(User.id)).filter_by(**filter_dict)
    #         result = await self._session.execute(query)
    #         count = result.scalar()
    #
    #         logger.info(f"Найдено {count} пользователей")
    #
    #         return count
    #     except SQLAlchemyError as e:
    #         logger.error(f"Ошибка при подсчете пользователей: {e}")
    #         raise
    #
    # async def exists(self, filters: SUserFilter) -> bool:
    #     """
    #     Проверить существование пользователя по фильтрам
    #
    #     Args:
    #         filters: Фильтры для проверки
    #
    #     Returns:
    #         True если пользователь существует, False если нет
    #     """
    #     filter_dict = filters.model_dump(exclude_unset=True)
    #     logger.debug(f"Проверка существования пользователя по фильтрам: {filter_dict}")
    #
    #     try:
    #         query = select(User.id).filter_by(**filter_dict).limit(1)
    #         result = await self._session.execute(query)
    #         exists = result.scalar() is not None
    #
    #         if exists:
    #             logger.debug(f"Пользователь существует по фильтрам: {filter_dict}")
    #         else:
    #             logger.debug(f"Пользователь не существует по фильтрам: {filter_dict}")
    #
    #         return exists
    #     except SQLAlchemyError as e:
    #         logger.error(f"Ошибка при проверке существования пользователя: {e}")
    #         raise
    #

    #
    # async def get_users_by_role(self, role: UserRole) -> List["User"]:
    #     """
    #     Получить пользователей по роли
    #
    #     Args:
    #         role: Роль пользователя
    #
    #     Returns:
    #         Список пользователей с указанной ролью
    #     """
    #     logger.debug(f"Получение пользователей с ролью {role}")
    #     return await self.find_all(SUserFilter(role=role))
    #
    # async def deactivate_user(self, user_id: int) -> bool:
    #     """
    #     Деактивировать пользователя по ID
    #
    #     Args:
    #         user_id: ID пользователя
    #
    #     Returns:
    #         True если пользователь деактивирован, False если не найден
    #     """
    #     logger.warning(f"Деактивация пользователя с ID {user_id}")
    #     return await self.update_by_id(user_id, SUserUpdate(is_active=False))
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
