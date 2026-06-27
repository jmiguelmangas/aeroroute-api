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

    def __init__(
        self, client: httpx.AsyncClient, max_attempts: int = 3
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max attempts must be positive")
        self._client = client
        self._max_attempts = max_attempts

    async def winds_for(
        self, requests: Sequence[WindSampleRequest]
    ) -> tuple[WindSample, ...]:
        if not requests:
            return ()
        by_date: dict[str, list[WindSampleRequest]] = {}
        for request in requests:
            date = request.at_utc.astimezone(UTC).date().isoformat()
            by_date.setdefault(date, []).append(request)
        samples: dict[WindSampleRequest, WindSample] = {}
        for date, date_requests in by_date.items():
            samples.update(await self._winds_for_date(date, date_requests))
        return tuple(samples[request] for request in requests)

    async def _winds_for_date(
        self, date: str, requests: Sequence[WindSampleRequest]
    ) -> dict[WindSampleRequest, WindSample]:
        coordinates = list(
            dict.fromkeys(
                (request.latitude_deg, request.longitude_deg)
                for request in requests
            )
        )
        pressures = sorted({request.pressure_hpa for request in requests})
        hourly = ",".join(
            variable
            for pressure_hpa in pressures
            for variable in (
                f"wind_speed_{pressure_hpa}hPa",
                f"wind_direction_{pressure_hpa}hPa",
                f"geopotential_height_{pressure_hpa}hPa",
            )
        )
        response = await self._get_with_retries(
            {
                "latitude": ",".join(str(item[0]) for item in coordinates),
                "longitude": ",".join(str(item[1]) for item in coordinates),
                "hourly": hourly,
                "wind_speed_unit": "ms",
                "timezone": "GMT",
                "cell_selection": "nearest",
                "start_date": date,
                "end_date": date,
            }
        )
        try:
            response.raise_for_status()
            document = response.json()
            documents = document if isinstance(document, list) else [document]
            if len(documents) != len(coordinates):
                raise ValueError("location count changed")
            fetched_at = datetime.now(UTC)
            result: dict[WindSampleRequest, WindSample] = {}
            for request in requests:
                coordinate_index = coordinates.index(
                    (request.latitude_deg, request.longitude_deg)
                )
                payload = documents[coordinate_index]["hourly"]
                result[request] = self._parse_sample(
                    request, payload, fetched_at
                )
            return result
        except (
            KeyError,
            ValueError,
            IndexError,
            TypeError,
            httpx.HTTPStatusError,
        ) as error:
            raise WeatherProviderError(
                "Open-Meteo response did not satisfy wind contract"
            ) from error

    async def _get_with_retries(
        self, params: dict[str, str]
    ) -> httpx.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(
                    self.base_url, params=params
                )
                if response.status_code < 500:
                    return response
            except (httpx.TimeoutException, httpx.TransportError) as error:
                if attempt == self._max_attempts:
                    raise WeatherProviderError(
                        "Open-Meteo request failed after retries"
                    ) from error
            if attempt == self._max_attempts:
                raise WeatherProviderError(
                    "Open-Meteo request failed after retries"
                )
        raise AssertionError("unreachable")

    def _parse_sample(
        self,
        request: WindSampleRequest,
        payload: dict[str, object],
        fetched_at: datetime,
    ) -> WindSample:
        pressure = f"{request.pressure_hpa}hPa"
        try:
            requested_time = request.at_utc.astimezone(UTC).strftime(
                "%Y-%m-%dT%H:00"
            )
            times = payload["time"]
            if not isinstance(times, list):
                raise TypeError("time is not a list")
            index = times.index(requested_time)
            speed = float(_series_value(payload, f"wind_speed_{pressure}", index))
            direction = float(
                _series_value(payload, f"wind_direction_{pressure}", index)
            )
            height = float(
                _series_value(
                    payload, f"geopotential_height_{pressure}", index
                )
            )
        except (KeyError, ValueError, IndexError, TypeError) as error:
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
            fetched_at_utc=fetched_at,
            model="best_match",
        )


def _series_value(
    payload: dict[str, object], key: str, index: int
) -> object:
    values = payload[key]
    if not isinstance(values, list):
        raise TypeError(f"{key} is not a list")
    return values[index]
