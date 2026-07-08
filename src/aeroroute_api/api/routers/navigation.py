from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.navigation import (
    ProcedureOptionsResponse,
    RouteSupportResponse,
    RunwayOptionsResponse,
)
from aeroroute_api.application.services.route_support import (
    assess_route_support,
)
from aeroroute_api.application.services.terminal_options import (
    procedure_options,
    runway_options,
)
from aeroroute_api.config import settings
from aeroroute_api.infrastructure.datasets.active_catalogue import (
    active_airport_snapshot_id,
)
from aeroroute_api.infrastructure.db.models import Airport
from aeroroute_api.infrastructure.navigation.airac import (
    AiracNavigationClient,
    AiracProviderError,
)
from aeroroute_api.infrastructure.weather.open_meteo import (
    OpenMeteoWeatherClient,
    WeatherProviderError,
)

router = APIRouter(prefix="/api/v1/airports", tags=["navigation"])
_settings = settings()
_client = AiracNavigationClient(
    httpx.AsyncClient(timeout=_settings.navigation_timeout_s),
    max_concurrent_requests=_settings.navigation_max_concurrent_requests,
)
_weather = OpenMeteoWeatherClient(httpx.AsyncClient(timeout=8.0))


@router.get("/route-support", response_model=RouteSupportResponse)
async def route_support(
    origin_icao: str = Query(min_length=3, max_length=8),
    destination_icao: str = Query(min_length=3, max_length=8),
    session: AsyncSession = Depends(database_session),
) -> RouteSupportResponse:
    airport_codes = (origin_icao.upper(), destination_icao.upper())
    airports = (
        await session.scalars(
            select(Airport).where(
                Airport.snapshot_id == active_airport_snapshot_id(),
                or_(
                    func.upper(Airport.icao_code) == airport_codes[0],
                    func.upper(Airport.icao_code) == airport_codes[1],
                ),
            )
        )
    ).all()
    return await assess_route_support(
        airport_codes[0], airport_codes[1], list(airports), _client
    )


@router.get("/{icao}/runways", response_model=RunwayOptionsResponse)
async def list_runways(
    icao: str,
    procedure_type: Literal["SID", "STAR"] = Query(...),
    at_utc: datetime | None = Query(default=None),
) -> RunwayOptionsResponse:
    try:
        surface_wind = None
        if at_utc is not None:
            try:
                latitude, longitude = await _client.airport_position(icao)
                surface_wind = await _weather.surface_wind(
                    latitude, longitude, at_utc
                )
            except (AiracProviderError, WeatherProviderError):
                surface_wind = None
        return await runway_options(_client, icao, procedure_type, surface_wind)
    except AiracProviderError as error:
        raise HTTPException(
            status_code=503, detail="AIRAC runway data unavailable"
        ) from error


@router.get("/{icao}/procedures", response_model=ProcedureOptionsResponse)
async def list_procedures(
    icao: str,
    procedure_type: Literal["SID", "STAR"] = Query(..., alias="type"),
    runway: str | None = Query(default=None),
) -> ProcedureOptionsResponse:
    try:
        return await procedure_options(_client, icao, procedure_type, runway)
    except AiracProviderError as error:
        raise HTTPException(
            status_code=503, detail="AIRAC procedure data unavailable"
        ) from error
