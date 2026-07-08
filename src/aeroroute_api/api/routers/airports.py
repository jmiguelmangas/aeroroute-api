from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.airports import AirportPage, AirportResponse
from aeroroute_api.application.services.airport_catalogue import (
    CachedAirportCatalogue,
)

router = APIRouter(prefix="/api/v1/airports", tags=["airports"])
_catalogue = CachedAirportCatalogue()


@router.get("", response_model=AirportPage)
async def search_airports(
    query: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(database_session),
) -> AirportPage:
    airports = await _catalogue.search(session, query, limit, offset)
    return AirportPage(
        items=[
            AirportResponse.model_validate(airport, from_attributes=True)
            for airport in airports
        ],
        limit=limit,
        offset=offset,
    )
