"""Database for todo
"""
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_db_url
from app.uow import UnitOfWork

engine = create_async_engine(get_db_url())
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
uow = UnitOfWork(async_session_maker)

async def get_async_uow_session() -> UnitOfWork:
    async with uow.start() as uow_session:
        yield uow_session
