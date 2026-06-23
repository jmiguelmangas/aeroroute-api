from datetime import UTC, datetime, timedelta

import pytest

from aeroroute_api.domain.ports import WindSample
from aeroroute_api.infrastructure.weather.interpolation import (
    HeightWindSample,
    interpolate_height,
    interpolate_time,
)


def _sample(
    at_utc: datetime, east: float, north: float, height: float
) -> WindSample:
    return WindSample(east, north, height, at_utc, "fixture")


def test_time_interpolation_uses_vector_components() -> None:
    start = datetime(2026, 6, 23, 12, tzinfo=UTC)
    result = interpolate_time(
        _sample(start, 10, 0, 10_000),
        _sample(start + timedelta(hours=2), -10, 0, 10_200),
        start + timedelta(hours=1),
    )

    assert result.east_mps == pytest.approx(0)
    assert result.geopotential_height_m == pytest.approx(10_100)


def test_height_interpolation_uses_geopotential_not_pressure_number() -> None:
    at_utc = datetime(2026, 6, 23, 12, tzinfo=UTC)
    result = interpolate_height(
        HeightWindSample(9_200, _sample(at_utc, 10, 0, 9_200)),
        HeightWindSample(11_800, _sample(at_utc, 30, 20, 11_800)),
        10_500,
    )

    assert result.east_mps == pytest.approx(20)
    assert result.north_mps == pytest.approx(10)
