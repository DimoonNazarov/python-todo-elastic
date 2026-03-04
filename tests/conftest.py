import asyncio
from typing import AsyncGenerator

import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import get_async_uow_session
from app.models import base
from app.main import app
from app.core.uow import UnitOfWork
from app.config import get_db_url

engine_test = create_async_engine(get_db_url(), poolclass=NullPool)
async_session_maker = async_sessionmaker(engine_test, expire_on_commit=False)
uow = UnitOfWork(async_session_maker)
Base.metadata.bind = engine_test


async def override_get_async_uow_session() -> UnitOfWork:
    async with uow.start() as uow_session:
        yield uow_session


app.dependency_overrides[get_async_uow_session] = override_get_async_uow_session


@pytest.fixture(autouse=True, scope='session')
async def prepare_database():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class CustomEventLoopPolicy(asyncio.DefaultEventLoopPolicy):
    pass


@pytest.fixture(scope="session", autouse=True)
def event_loop_policy(request):
    return CustomEventLoopPolicy()


@pytest.fixture(scope="session")
async def ac() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
