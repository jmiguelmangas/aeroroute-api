import asyncio
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.api.errors import PublicAPIError
from aeroroute_api.application.dto.optimization import (
    OptimizationHistoryItem,
    OptimizationRequest,
    OptimizationResponse,
)
from aeroroute_api.application.services.optimization import (
    optimize_still_air,
    optimize_with_weather,
)
from aeroroute_api.application.services.navigation import (
    enrich_winner_with_airac,
)
from aeroroute_api.application.services.terminal_options import (
    IncompatibleRunwayError,
    validate_runway_selection,
)
from aeroroute_api.application.services.execution_guard import (
    OptimizationCapacityExceeded,
    OptimizationDeadlineExceeded,
    OptimizationExecutionGuard,
)
from aeroroute_api.config import settings
from aeroroute_api.infrastructure.db.models import Airport, OptimizationRun
from aeroroute_api.infrastructure.db.optimization_runs import (
    complete_optimization_run,
    fail_optimization_run,
    reserve_optimization_run,
)
from aeroroute_api.infrastructure.weather.cache import CachedWeatherPort
from aeroroute_api.infrastructure.weather.open_meteo import (
    OpenMeteoWeatherClient,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracNavigationClient,
    AiracProviderError,
)

router = APIRouter(prefix="/api/v1/optimizations", tags=["optimizations"])
_weather_client = httpx.AsyncClient(timeout=5.0)
_weather = CachedWeatherPort(OpenMeteoWeatherClient(_weather_client))
_navigation_client = AiracNavigationClient(httpx.AsyncClient(timeout=5.0))
_limits = settings()
_execution_guard = OptimizationExecutionGuard(
    max_concurrent=_limits.optimization_max_concurrent,
    queue_timeout_s=_limits.optimization_queue_timeout_s,
    execution_timeout_s=_limits.optimization_deadline_s,
)


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
    try:
        if request.departure_runway:
            await validate_runway_selection(
                _navigation_client,
                airport_codes[0],
                "SID",
                request.departure_runway,
            )
        if request.arrival_runway:
            await validate_runway_selection(
                _navigation_client,
                airport_codes[1],
                "STAR",
                request.arrival_runway,
            )
    except IncompatibleRunwayError as error:
        raise PublicAPIError(
            422,
            "runway_procedure_incompatible",
            str(error),
        ) from error
    except AiracProviderError as error:
        raise PublicAPIError(
            503,
            "navigation_provider_unavailable",
            "AIRAC runway and procedure data are unavailable.",
        ) from error
    configured = settings()
    reservation = await reserve_optimization_run(session, request)
    run = reservation.run
    if not reservation.should_execute:
        if run.status == "completed" and run.output_json is not None:
            stored = OptimizationResponse.model_validate(run.output_json)
            return stored.model_copy(update={"run_id": str(run.id)})
        raise PublicAPIError(
            409,
            "optimization_in_progress",
            "An identical optimization is already running.",
        )

    async def execute() -> OptimizationResponse:
        if (
            configured.weather_provider == "open_meteo"
            and request.departure_time_utc is not None
        ):
            return await optimize_with_weather(
                origin.latitude_deg,
                origin.longitude_deg,
                destination.latitude_deg,
                destination.longitude_deg,
                request.aircraft_type,
                request.profile,
                request.departure_time_utc,
                _weather,
                configured.aircraft_performance_provider,
            )
        return optimize_still_air(
            origin.latitude_deg,
            origin.longitude_deg,
            destination.latitude_deg,
            destination.longitude_deg,
            request.aircraft_type,
            request.profile,
            configured.aircraft_performance_provider,
        )

    try:
        response = await _execution_guard.run(execute)
        response = response.model_copy(update={"request": request})
        response = await enrich_winner_with_airac(response, _navigation_client)
    except OptimizationCapacityExceeded as error:
        await fail_optimization_run(session, run.id, "capacity_exceeded")
        raise PublicAPIError(
            429,
            "optimization_capacity_exceeded",
            "Optimization capacity is temporarily exhausted.",
        ) from error
    except OptimizationDeadlineExceeded as error:
        await fail_optimization_run(session, run.id, "deadline_exceeded")
        raise PublicAPIError(
            504,
            "optimization_deadline_exceeded",
            "The optimization exceeded its execution deadline.",
        ) from error
    except asyncio.CancelledError:
        await fail_optimization_run(session, run.id, "request_cancelled")
        raise
    except Exception as error:
        await fail_optimization_run(session, run.id, "optimization_failed")
        raise PublicAPIError(
            503,
            "optimization_failed",
            "The optimization could not be completed.",
        ) from error
    completed = await complete_optimization_run(session, run.id, response)
    return response.model_copy(update={"run_id": str(completed.id)})
