from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from elasticsearch import AsyncElasticsearch

from app.repository.todo_repository import TodoRepository
from app.repository.auth_repository import AuthRepository
from app.repository.elastic_repository import ElasticRepository
from app.repository.token_repository import TokenRepository


class UnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        es_client: AsyncElasticsearch | None = None,
    ):
        self.session_factory = session_factory
        self._session: AsyncSession | None = None
        self.es_client: AsyncElasticsearch | None = es_client

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
    def elastic(self) -> ElasticRepository:
        if self.es_client is None:
            raise RuntimeError(
                "Elasticsearch client is not configured for this UnitOfWork"
            )
        return ElasticRepository(self.es_client)

    @property
    def auth(self) -> AuthRepository:
        return AuthRepository(self._session)

    @property
    def token(self) -> TokenRepository:
        return TokenRepository(self._session)
