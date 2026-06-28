import pytest

from aeroroute_api.api.routers.weather import (
    _corridor_coordinates,
    _pressure_for_flight_level,
)


def test_pressure_level_tracks_cruise_band() -> None:
    assert _pressure_for_flight_level(300) == 300
    assert _pressure_for_flight_level(350) == 250
    assert _pressure_for_flight_level(390) == 200


def test_corridor_grid_follows_route_and_keeps_40_samples() -> None:
    coordinates = _corridor_coordinates(25.25, 55.36, 40.47, -3.56)

    assert len(coordinates) == 40
    assert min(longitude for _, longitude in coordinates) == pytest.approx(
        -3.56
    )
    assert max(longitude for _, longitude in coordinates) == pytest.approx(
        55.36
    )
    assert min(latitude for latitude, _ in coordinates) == pytest.approx(17.25)
    assert max(latitude for latitude, _ in coordinates) == pytest.approx(48.47)
