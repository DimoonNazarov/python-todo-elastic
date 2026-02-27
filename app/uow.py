from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.repository import TodoRepository
from app.repository import AuthRepository


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker):
        self.session_factory = session_factory
        self._session: AsyncSession | None = None

    @asynccontextmanager
    async def start(self):
        self._session = self.session_factory()
        try:
            yield self
            await self._session.commit()
        except Exception as e:
            await self._session.rollback()
            raise e
        finally:
            await self._session.close()

    @property
    def todo(self) -> TodoRepository:
        return TodoRepository(self._session)

    @property
    def auth(self) -> AuthRepository:
        return AuthRepository(self._session)
