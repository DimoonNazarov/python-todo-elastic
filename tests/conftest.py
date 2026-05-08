import asyncio
import os
from typing import AsyncGenerator
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from elasticsearch import AsyncElasticsearch

from app.core import get_async_uow_session, UnitOfWork
from app.models import Base
from app.main import app
from app.config import get_db_url
from app.services import TodoClassificationService

engine_test = create_async_engine(get_db_url(), poolclass=NullPool)
async_session_maker = async_sessionmaker(engine_test, expire_on_commit=False)

Base.metadata.bind = engine_test
ES_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9201")


async def override_get_async_uow_session():
    es = AsyncElasticsearch(hosts=[ES_HOST])
    uow = UnitOfWork(async_session_maker, es)
    yield uow


app.dependency_overrides[get_async_uow_session] = override_get_async_uow_session


@pytest.fixture(scope="session")
def es_client():
    return AsyncElasticsearch(hosts=[ES_HOST])


# Fixture для сервиса классификации
@pytest.fixture(scope="session")
def classification_service() -> TodoClassificationService:
    """Возвращает экземпляр TodoClassificationService для тестов."""
    return TodoClassificationService()  # Fixture для сервиса классификации


@pytest.fixture(autouse=True, scope="session")
async def prepare_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# Очистка таблиц между тестами
@pytest.fixture(autouse=True)
async def clean_tables():
    yield
    async with engine_test.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
async def ac() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://l") as ac:
        yield ac
