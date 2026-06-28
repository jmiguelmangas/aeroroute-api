from aeroroute_api.api.routers.weather import _pressure_for_flight_level


def test_pressure_level_tracks_cruise_band() -> None:
    assert _pressure_for_flight_level(300) == 300
    assert _pressure_for_flight_level(350) == 250
    assert _pressure_for_flight_level(390) == 200
