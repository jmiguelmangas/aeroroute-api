"""Short-lived read cache for the small active airport catalogue."""

from __future__ import annotations

import asyncio
from time import monotonic
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.infrastructure.datasets.active_catalogue import (
    active_airport_snapshot_id,
)
from aeroroute_api.infrastructure.db.models import Airport


class CachedAirportCatalogue:
    def __init__(
        self,
        ttl_s: float = 30.0,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._ttl_s = ttl_s
        self._clock = clock
        self._expires_at = 0.0
        self._items: tuple[Airport, ...] = ()
        self._lock = asyncio.Lock()

    async def search(
        self,
        session: AsyncSession,
        query: str,
        limit: int,
        offset: int,
    ) -> tuple[Airport, ...]:
        items = await self._catalogue(session)
        needle = query.casefold()
        matches = [
            airport
            for airport in items
            if any(
                needle in value.casefold()
                for value in (
                    airport.icao_code,
                    airport.iata_code or "",
                    airport.name,
                    airport.municipality or "",
                )
            )
        ]
        return tuple(matches[offset : offset + limit])

    async def _catalogue(self, session: AsyncSession) -> tuple[Airport, ...]:
        if self._expires_at > self._clock():
            return self._items
        async with self._lock:
            if self._expires_at > self._clock():
                return self._items
            items = (
                await session.scalars(
                    select(Airport)
                    .where(Airport.snapshot_id == active_airport_snapshot_id())
                    .order_by(Airport.icao_code)
                )
            ).all()
            self._items = tuple(items)
            self._expires_at = self._clock() + self._ttl_s
            return self._items
