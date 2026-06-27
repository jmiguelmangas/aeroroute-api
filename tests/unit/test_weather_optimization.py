from datetime import UTC, datetime

import pytest

from aeroroute_api.application.services.optimization import (
    optimize_with_weather,
)
from aeroroute_api.domain.ports import WindSample


class _ForecastFixture:
    def __init__(self, fails: bool = False, stale: bool = False) -> None:
        self.fails = fails
        self.stale = stale

    async def winds_for(self, requests):
        if self.fails:
            raise RuntimeError("forecast unavailable")
        heights = {300: 9_200.0, 250: 10_400.0, 200: 11_800.0}
        return tuple(
            WindSample(
                east_mps=25.0,
                north_mps=5.0,
                geopotential_height_m=heights[request.pressure_hpa],
                valid_at_utc=request.at_utc,
                source="forecast-fixture",
                stale=self.stale,
                fetched_at_utc=datetime(2026, 6, 27, tzinfo=UTC),
                model="fixture-v1",
            )
            for request in requests
        )


@pytest.mark.anyio
async def test_forecast_snapshot_reaches_solver_and_waypoints() -> None:
    result = await optimize_with_weather(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        "A320",
        "minimum_fuel",
        datetime(2026, 6, 27, 12, 30, tzinfo=UTC),
        _ForecastFixture(),  # type: ignore[arg-type]
    )

    assert result.winner is not None
    assert {flag.code for flag in result.data_quality} == {
        "PERFORMANCE_CURATED",
        "WEATHER_FORECAST",
    }
    components = [
        point.wind_component_kt
        for point in result.winner.waypoints[1:]
    ]
    assert all(component is not None for component in components)
    assert any(abs(component or 0) > 0 for component in components)


@pytest.mark.anyio
async def test_forecast_failure_degrades_to_explicit_still_air() -> None:
    result = await optimize_with_weather(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        "A320",
        "minimum_fuel",
        datetime(2026, 6, 27, 12, tzinfo=UTC),
        _ForecastFixture(fails=True),  # type: ignore[arg-type]
    )

    assert result.winner is not None
    assert {flag.code for flag in result.data_quality} == {
        "PERFORMANCE_CURATED",
        "WEATHER_FALLBACK",
    }
