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
async def test_reads_hourly_surface_wind_in_knots() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["hourly"] == (
            "wind_speed_10m,wind_direction_10m"
        )
        assert request.url.params["wind_speed_unit"] == "kn"
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-06-23T12:00"],
                    "wind_speed_10m": [18.0],
                    "wind_direction_10m": [320.0],
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        result = await OpenMeteoWeatherClient(client).surface_wind(
            40.49, -3.57, datetime(2026, 6, 23, 12, tzinfo=UTC)
        )

    assert result.speed_kt == 18
    assert result.direction_from_deg == 320


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


@pytest.mark.anyio
async def test_batches_coordinates_and_preserves_request_order() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.params["latitude"] == "41.0,40.0"
        assert request.url.params["cell_selection"] == "nearest"
        return httpx.Response(
            200,
            json=[
                {
                    "hourly": {
                        "time": ["2026-06-23T12:00"],
                        "wind_speed_250hPa": [30.0],
                        "wind_direction_250hPa": [270.0],
                        "geopotential_height_250hPa": [10_500.0],
                    }
                },
                {
                    "hourly": {
                        "time": ["2026-06-23T12:00"],
                        "wind_speed_250hPa": [10.0],
                        "wind_direction_250hPa": [270.0],
                        "geopotential_height_250hPa": [10_400.0],
                    }
                },
            ],
        )

    at_utc = datetime(2026, 6, 23, 12, tzinfo=UTC)
    requests = [
        WindSampleRequest(41.0, -4.0, 250, at_utc),
        WindSampleRequest(40.0, -3.0, 250, at_utc),
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        result = await OpenMeteoWeatherClient(client).winds_for(requests)

    assert calls == 1
    assert [sample.east_mps for sample in result] == pytest.approx([30, 10])
    assert all(sample.fetched_at_utc is not None for sample in result)


@pytest.mark.anyio
async def test_retries_transient_transport_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("temporary", request=request)
        return httpx.Response(
            200,
            json={
                "hourly": {
                    "time": ["2026-06-23T12:00"],
                    "wind_speed_250hPa": [20.0],
                    "wind_direction_250hPa": [270.0],
                    "geopotential_height_250hPa": [10_400.0],
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as client:
        result = await OpenMeteoWeatherClient(client).winds_for(
            [
                WindSampleRequest(
                    40, -3, 250, datetime(2026, 6, 23, 12, tzinfo=UTC)
                )
            ]
        )

    assert calls == 2
    assert result[0].east_mps == pytest.approx(20)
