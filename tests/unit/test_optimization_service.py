import pytest

from aeroroute_api.application.dto.optimization import RoutePoint
from aeroroute_api.application.services.optimization import (
    _display_geojson,
    aircraft_performance,
    optimize_still_air,
)


def test_optimizer_use_case_delegates_to_versioned_package() -> None:
    result = optimize_still_air(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        "A320",
        "minimum_fuel",
    )

    assert result.status == "optimal"
    assert result.algorithm_version == "0.1.0"
    assert result.winner is not None
    assert result.winner.path[0].startswith("0:")
    assert result.winner.path[-1].startswith("6:")
    assert result.winner.geometry[0].latitude_deg == pytest.approx(40.4722)
    assert result.baseline is not None
    assert result.winner.display_geojson.type == "LineString"
    assert result.winner.waypoints[-1].cumulative_fuel_kg == pytest.approx(
        result.winner.fuel_kg
    )
    assert result.assumptions
    assert {flag.code for flag in result.data_quality} == {
        "PERFORMANCE_CURATED",
        "WEATHER_STILL_AIR",
    }


def test_display_geojson_splits_at_antimeridian() -> None:
    geometry = _display_geojson(
        [
            RoutePoint(latitude_deg=35.0, longitude_deg=179.0),
            RoutePoint(latitude_deg=36.0, longitude_deg=-179.0),
        ]
    )

    assert geometry.type == "MultiLineString"
    assert len(geometry.coordinates) == 2


def test_performance_provider_selection_is_explicit() -> None:
    assert aircraft_performance("CURATED").provenance.provider == "curated"

    with pytest.raises(ValueError, match="unsupported aircraft performance"):
        aircraft_performance("automatic")
