"""Open-Meteo pressure-level adapter with a testable HTTP boundary."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime

import httpx

from aeroroute_api.domain.ports import WindSample, WindSampleRequest


class WeatherProviderError(RuntimeError):
    pass


class OpenMeteoWeatherClient:
    base_url = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def winds_for(
        self, requests: Sequence[WindSampleRequest]
    ) -> tuple[WindSample, ...]:
        return tuple([await self._wind_for(request) for request in requests])

    async def _wind_for(self, request: WindSampleRequest) -> WindSample:
        pressure = f"{request.pressure_hpa}hPa"
        hourly = ",".join(
            [
                f"wind_speed_{pressure}",
                f"wind_direction_{pressure}",
                f"geopotential_height_{pressure}",
            ]
        )
        response = await self._client.get(
            self.base_url,
            params={
                "latitude": request.latitude_deg,
                "longitude": request.longitude_deg,
                "hourly": hourly,
                "wind_speed_unit": "ms",
                "timezone": "GMT",
                "start_date": request.at_utc.date().isoformat(),
                "end_date": request.at_utc.date().isoformat(),
            },
        )
        try:
            response.raise_for_status()
            payload = response.json()["hourly"]
            requested_time = request.at_utc.astimezone(UTC).strftime(
                "%Y-%m-%dT%H:00"
            )
            index = payload["time"].index(requested_time)
            speed = float(payload[f"wind_speed_{pressure}"][index])
            direction = float(payload[f"wind_direction_{pressure}"][index])
            height = float(payload[f"geopotential_height_{pressure}"][index])
        except (
            KeyError,
            ValueError,
            IndexError,
            httpx.HTTPStatusError,
        ) as error:
            raise WeatherProviderError(
                "Open-Meteo response did not satisfy wind contract"
            ) from error
        if not all(
            math.isfinite(value) for value in (speed, direction, height)
        ):
            raise WeatherProviderError(
                "Open-Meteo returned non-finite wind data"
            )
        radians = math.radians(direction % 360)
        return WindSample(
            east_mps=-speed * math.sin(radians),
            north_mps=-speed * math.cos(radians),
            geopotential_height_m=height,
            valid_at_utc=datetime.strptime(
                requested_time, "%Y-%m-%dT%H:00"
            ).replace(tzinfo=UTC),
            source="open-meteo",
        )
