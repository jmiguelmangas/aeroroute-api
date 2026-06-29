from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.airports import AirportPage, AirportResponse
from aeroroute_api.infrastructure.db.models import Airport
from aeroroute_api.infrastructure.datasets.active_catalogue import (
    active_airport_snapshot_id,
)

router = APIRouter(prefix="/api/v1/airports", tags=["airports"])


@router.get("", response_model=AirportPage)
async def search_airports(
    query: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(database_session),
) -> AirportPage:
    escaped = query.replace("%", r"\%").replace("_", r"\_")
    pattern = f"%{escaped}%"
    statement: Select[tuple[Airport]] = (
        select(Airport)
        .where(
            Airport.snapshot_id == active_airport_snapshot_id(),
            or_(
                Airport.icao_code.ilike(pattern, escape="\\"),
                Airport.iata_code.ilike(pattern, escape="\\"),
                Airport.name.ilike(pattern, escape="\\"),
                Airport.municipality.ilike(pattern, escape="\\"),
            )
        )
        .order_by(Airport.icao_code)
        .limit(limit)
        .offset(offset)
    )
    airports = (await session.scalars(statement)).all()
    return AirportPage(
        items=[
            AirportResponse.model_validate(airport, from_attributes=True)
            for airport in airports
        ],
        limit=limit,
        offset=offset,
    )
