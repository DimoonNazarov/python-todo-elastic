import asyncio
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
from app.config import get_db_url, settings
from app.repository.elastic_repository import ElasticRepository, INDEX_NAME
from app.services import TodoClassificationService

engine_test = create_async_engine(get_db_url(), poolclass=NullPool)
async_session_maker = async_sessionmaker(engine_test, expire_on_commit=False)

Base.metadata.bind = engine_test


def _build_es_host() -> str:
    # CI передаёт ELASTICSEARCH_HOST уже как полный URL (http://localhost:9200),
    # а локальный .env.test — как голый хост (elasticsearch_test) + отдельный порт.
    host = settings.ELASTICSEARCH_HOST
    if host.startswith(("http://", "https://")):
        return host
    return f"http://{host}:{settings.ELASTICSEARCH_PORT}"


ES_HOST = _build_es_host()


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


@pytest.fixture(autouse=True, scope="session")
async def prepare_elasticsearch():
    """Создаёт индекс с маппингом до тестов.

    В приложении это делает lifespan, но httpx ASGITransport его не запускает,
    поэтому индекс нужно создать здесь явно (иначе ES-зависимые тесты падают).
    """
    es = AsyncElasticsearch(hosts=[ES_HOST])
    repo = ElasticRepository(es)
    # Чистый старт на случай оставшегося индекса от прошлого прогона.
    await es.options(ignore_status=[404]).indices.delete(index=INDEX_NAME)
    await repo.ensure_index_exists()
    await repo.ensure_file_content_field()
    yield
    await es.options(ignore_status=[404]).indices.delete(index=INDEX_NAME)
    await es.close()


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
