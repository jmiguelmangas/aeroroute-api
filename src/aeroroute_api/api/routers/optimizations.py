from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.optimization import (
    OptimizationHistoryItem,
    OptimizationRequest,
    OptimizationResponse,
)
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.config import settings
from aeroroute_api.infrastructure.db.models import Airport, OptimizationRun
from aeroroute_api.infrastructure.db.optimization_runs import (
    persist_completed_run,
)

router = APIRouter(prefix="/api/v1/optimizations", tags=["optimizations"])


@router.get("", response_model=list[OptimizationHistoryItem])
async def list_optimizations(
    session: AsyncSession = Depends(database_session),
) -> list[OptimizationHistoryItem]:
    from aeroroute_api.infrastructure.db.models import OptimizationRun

    runs = (
        await session.scalars(
            select(OptimizationRun)
            .order_by(OptimizationRun.created_at.desc())
            .limit(20)
        )
    ).all()
    return [
        OptimizationHistoryItem(
            run_id=str(run.id),
            status=run.status,
            origin_icao=str(run.input_json["origin_icao"]),
            destination_icao=str(run.input_json["destination_icao"]),
            aircraft_type=str(run.input_json["aircraft_type"]),
            profile=str(run.input_json["profile"]),
        )
        for run in runs
    ]


@router.get("/{run_id}", response_model=OptimizationResponse)
async def get_optimization(
    run_id: UUID,
    session: AsyncSession = Depends(database_session),
) -> OptimizationResponse:
    run = await session.get(OptimizationRun, run_id)
    if run is None:
        raise HTTPException(
            status_code=404, detail="optimization run not found"
        )
    if run.output_json is None:
        raise HTTPException(
            status_code=409,
            detail="optimization run does not contain a response snapshot",
        )
    response = OptimizationResponse.model_validate(run.output_json)
    return response.model_copy(update={"run_id": str(run.id)})


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
    response = optimize_still_air(
        origin.latitude_deg,
        origin.longitude_deg,
        destination.latitude_deg,
        destination.longitude_deg,
        request.aircraft_type,
        request.profile,
        settings().aircraft_performance_provider,
    )
    response = response.model_copy(update={"request": request})
    run = await persist_completed_run(session, request, response)
    return response.model_copy(update={"run_id": str(run.id)})
