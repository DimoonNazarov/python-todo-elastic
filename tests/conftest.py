import asyncio
import os
from typing import AsyncGenerator
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text
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


@pytest.fixture(scope="session")
def classification_service() -> TodoClassificationService:
    """Возвращает экземпляр TodoClassificationService для тестов."""
    return TodoClassificationService()


@pytest.fixture(autouse=True, scope="session")
async def prepare_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_tables():
    yield
    async with engine_test.begin() as conn:
        table_names = ", ".join(
            f'"{table.name}"' for table in Base.metadata.sorted_tables
        )
        await conn.execute(
            text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE")
        )


@pytest.fixture(scope="session")
def event_loop_policy():
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
async def ac() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://l") as ac:
        yield ac
