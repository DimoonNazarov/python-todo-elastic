from contextlib import asynccontextmanager
from logging import getLogger

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession

from elasticsearch import AsyncElasticsearch

from app.repository import TodoRepository
from app.repository import AuthRepository
from app.repository.elastic_repository import ElasticRepository
from app.repository.token_repository import TokenRepository

logger = getLogger(__name__)

class UnitOfWork:
    def __init__(
        self,
        session_factory: async_sessionmaker,
        es_client: AsyncElasticsearch | None = None,
    ):
        self.session_factory = session_factory
        self._session: AsyncSession | None = None
        self.es_client: AsyncElasticsearch | None = es_client
        self._compensations = []


    @asynccontextmanager
    async def start(self):
        self._session = self.session_factory()
        self._compensations = []
        try:
            yield self
            await self._session.commit()
        except Exception as e:
            await self._session.rollback()
            await self._run_compensations()
            raise e
        finally:
            self._compensations = []
            await self._session.close()

    async def flush(self) -> None:
        await self._session.flush()

    def add_compensation(self, callback, *args, **kwargs) -> None:
        self._compensations.append((callback, args, kwargs))

    async def _run_compensations(self) -> None:
        for callback, args, kwargs in reversed(self._compensations):
            try:
                await callback(*args, **kwargs)
            except Exception as exc:
                logger.error("Compensation failed: %s", exc)

    @property
    def todo(self) -> TodoRepository:
        return TodoRepository(self._session)

    @property
    def elastic(self) -> ElasticRepository:
        if self.es_client is None:
            raise RuntimeError("Elasticsearch client is not configured for this UnitOfWork")
        return ElasticRepository(self.es_client)

    @property
    def auth(self) -> AuthRepository:
        return AuthRepository(self._session)

    @property
    def token(self) -> TokenRepository:
        return TokenRepository(self._session)
