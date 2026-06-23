"""Async SQLAlchemy session factory for PostGIS-backed adapters."""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from aeroroute_api.config import settings


@lru_cache
def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings().database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
