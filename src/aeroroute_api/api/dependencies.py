from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.infrastructure.db.session import get_session


async def database_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session():
        yield session
