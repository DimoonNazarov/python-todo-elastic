"""Database for todo"""

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from typing import AsyncGenerator

from elasticsearch import AsyncElasticsearch

from app.config import get_db_url, settings
from app.core.uow import UnitOfWork

_es_client: AsyncElasticsearch | None = None


def get_es_client() -> AsyncElasticsearch:
    global _es_client
    if _es_client is None:
        hosts = [f"http://{settings.ELASTICSEARCH_HOST}:{settings.ELASTICSEARCH_PORT}"]
        _es_client = AsyncElasticsearch(hosts=hosts)
    return _es_client


async def close_es_client():
    global _es_client
    if _es_client is not None:
        await _es_client.close()
        _es_client = None


engine = create_async_engine(get_db_url())
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_uow_session() -> AsyncGenerator[UnitOfWork, None]:
    yield UnitOfWork(async_session_maker, get_es_client())
