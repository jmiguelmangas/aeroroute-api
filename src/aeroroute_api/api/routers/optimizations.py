from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.optimization import (
    OptimizationRequest,
    OptimizationResponse,
)
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.db.models import Airport

router = APIRouter(prefix="/api/v1/optimizations", tags=["optimizations"])


@router.post(
    "", response_model=OptimizationResponse, status_code=status.HTTP_200_OK
)
async def create_optimization(
    request: OptimizationRequest,
    session: AsyncSession = Depends(database_session),
) -> OptimizationResponse:
    airport_codes = (
        request.origin_icao.upper(),
        request.destination_icao.upper(),
    )
    airports = (
        await session.scalars(
            select(Airport).where(
                or_(
                    func.upper(Airport.icao_code) == airport_codes[0],
                    func.upper(Airport.icao_code) == airport_codes[1],
                )
            )
        )
    ).all()
    by_code = {airport.icao_code.upper(): airport for airport in airports}
    if airport_codes[0] not in by_code or airport_codes[1] not in by_code:
        raise HTTPException(
            status_code=404, detail="origin or destination airport not found"
        )
    origin = by_code[airport_codes[0]]
    destination = by_code[airport_codes[1]]
    return optimize_still_air(
        origin.latitude_deg,
        origin.longitude_deg,
        destination.latitude_deg,
        destination.longitude_deg,
        request.aircraft_type,
        request.profile,
    )
