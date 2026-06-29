from datetime import datetime
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from aeroroute_api.application.dto.navigation import (
    ProcedureOptionsResponse,
    RunwayOptionsResponse,
)
from aeroroute_api.application.services.terminal_options import (
    procedure_options,
    runway_options,
)
from aeroroute_api.config import settings
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
