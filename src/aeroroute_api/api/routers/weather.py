import math
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Query

from aeroroute_api.api.errors import PublicAPIError
from aeroroute_api.application.dto.weather import (
    WindFieldResponse,
    WindFieldSample,
)
from aeroroute_api.domain.ports import WindSampleRequest
from aeroroute_api.infrastructure.weather.cache import CachedWeatherPort
from aeroroute_api.infrastructure.weather.open_meteo import (
    OpenMeteoWeatherClient,
)

router = APIRouter(prefix="/api/v1/weather", tags=["weather"])
_client = httpx.AsyncClient(timeout=8.0)
_weather = CachedWeatherPort(OpenMeteoWeatherClient(_client))

_LATITUDES = (35.0, 40.0, 45.0, 50.0, 55.0)
_LONGITUDES = (-75.0, -65.0, -55.0, -45.0, -35.0, -25.0, -15.0, -5.0)


@router.get("/wind-field", response_model=WindFieldResponse)
async def get_wind_field(
    at_utc: datetime,
    flight_level: int = Query(default=350, ge=300, le=410),
) -> WindFieldResponse:
    valid_at = at_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    pressure_hpa = _pressure_for_flight_level(flight_level)
    requests = tuple(
        WindSampleRequest(latitude, longitude, pressure_hpa, valid_at)
        for latitude in _LATITUDES
        for longitude in _LONGITUDES
    )
    try:
        samples = await _weather.winds_for(requests)
    except Exception as error:
        raise PublicAPIError(
            503,
            "wind_field_unavailable",
            "The wind field is temporarily unavailable.",
        ) from error
    if len(samples) != len(requests):
        raise PublicAPIError(
            503,
            "wind_field_incomplete",
            "The wind field is incomplete.",
        )
    knots_per_mps = 1.943844
    field_samples = [
        WindFieldSample(
            latitude_deg=request.latitude_deg,
            longitude_deg=request.longitude_deg,
            east_kt=sample.east_mps * knots_per_mps,
            north_kt=sample.north_mps * knots_per_mps,
            speed_kt=math.hypot(sample.east_mps, sample.north_mps)
            * knots_per_mps,
            direction_deg=(
                math.degrees(math.atan2(sample.east_mps, sample.north_mps))
                + 360
            )
            % 360,
        )
        for request, sample in zip(requests, samples, strict=True)
    ]
    return WindFieldResponse(
        valid_at_utc=valid_at,
        flight_level=flight_level,
        pressure_hpa=pressure_hpa,
        source=samples[0].source,
        samples=field_samples,
    )


def _pressure_for_flight_level(flight_level: int) -> int:
    if flight_level <= 320:
        return 300
    if flight_level <= 370:
        return 250
    return 200
