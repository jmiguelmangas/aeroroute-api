from datetime import UTC, datetime

import httpx
import pytest

from aeroroute_api.domain.ports import WindSampleRequest
from aeroroute_api.infrastructure.weather.open_meteo import (
    OpenMeteoWeatherClient,
    WeatherProviderError,
)


@pytest.mark.anyio
async def test_normalizes_pressure_level_wind_without_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["hourly"] == (
            "wind_speed_250hPa,wind_direction_250hPa,geopotential_height_250hPa"
        )
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-06-23T12:00"],
                    "wind_speed_250hPa": [20.0],
                    "wind_direction_250hPa": [270.0],
                    "geopotential_height_250hPa": [10400.0],
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        result = await OpenMeteoWeatherClient(client).winds_for(
            [
                WindSampleRequest(
                    40.0, -3.0, 250, datetime(2026, 6, 23, 12, tzinfo=UTC)
                )
            ]
        )

    assert result[0].east_mps == pytest.approx(20.0)
    assert result[0].north_mps == pytest.approx(0.0)
    assert result[0].geopotential_height_m == 10400.0


@pytest.mark.anyio
async def test_rejects_provider_contract_change() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"hourly": {}})
        )
    ) as client:
        with pytest.raises(WeatherProviderError, match="wind contract"):
            await OpenMeteoWeatherClient(client).winds_for(
                [
                    WindSampleRequest(
                        40.0, -3.0, 250, datetime(2026, 6, 23, 12, tzinfo=UTC)
                    )
                ]
            )
