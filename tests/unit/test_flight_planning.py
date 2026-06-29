import asyncio
from types import SimpleNamespace

import pytest

from aeroroute_api.application.dto.optimization import OptimizationRequest
from aeroroute_api.application.services.flight_planning import (
    add_preoperational_planning,
)
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.navigation.airac import AiracRunway


class FakeNavigation:
    def __init__(self, lengths: dict[str, float]) -> None:
        self.lengths = lengths

    async def runways(self, airport: str) -> tuple[AiracRunway, ...]:
        length = self.lengths.get(airport.upper())
        if length is None:
            return ()
        return (
            AiracRunway(
                identifier="09",
                bearing_deg=90.0,
                length_ft=length,
                width_ft=150.0,
                surface="ASPH",
                cycle="2606",
            ),
        )


def airport(
    code: str, name: str, latitude: float, longitude: float
) -> SimpleNamespace:
    return SimpleNamespace(
        icao_code=code,
        name=name,
        airport_type="large_airport",
        latitude_deg=latitude,
        longitude_deg=longitude,
    )


def response(request: OptimizationRequest):
    result = optimize_still_air(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        request.aircraft_type,
        request.profile,
    )
    return result.model_copy(update={"request": request})


def test_selects_compatible_alternate_and_builds_fuel_plan() -> None:
    request = OptimizationRequest(
        origin_icao="LEMD",
        destination_icao="KJFK",
        aircraft_type="B77W",
        extra_fuel_kg=1_000,
    )
    catalogue = [
        airport("KBOS", "Boston Logan", 42.3656, -71.0096),
        airport("KPHL", "Philadelphia", 39.8729, -75.2437),
        airport("CYQX", "Gander", 48.9369, -54.5681),
    ]
    navigation = FakeNavigation(
        {"KBOS": 10_083, "KPHL": 9_500, "CYQX": 10_200}
    )

    result = asyncio.run(
        add_preoperational_planning(
            response(request), catalogue, navigation  # type: ignore[arg-type]
        )
    )

    assert result.destination_alternate is not None
    assert result.destination_alternate.icao_code == "KPHL"
    assert result.destination_alternate.runway_compatible
    assert result.destination_alternate.airac_cycle == "2606"
    assert result.fuel_plan is not None
    assert result.fuel_plan.contingency_fuel_kg == pytest.approx(
        result.winner.fuel_kg * 0.05  # type: ignore[union-attr]
    )
    assert result.fuel_plan.block_fuel_kg > result.winner.fuel_kg  # type: ignore[union-attr]
    assert not result.fuel_plan.operationally_approved


def test_retains_requested_incompatible_alternate_as_degraded() -> None:
    request = OptimizationRequest(
        origin_icao="LEMD",
        destination_icao="KJFK",
        destination_alternate_icao="KBOS",
        aircraft_type="B77W",
    )
    catalogue = [airport("KBOS", "Boston Logan", 42.3656, -71.0096)]

    result = asyncio.run(
        add_preoperational_planning(
            response(request),
            catalogue,
            FakeNavigation({"KBOS": 8_000}),  # type: ignore[arg-type]
        )
    )

    assert result.destination_alternate is not None
    assert result.destination_alternate.selection == "requested"
    assert not result.destination_alternate.runway_compatible
    assert "ALTERNATE_RUNWAY_INCOMPATIBLE" in {
        flag.code for flag in result.data_quality
    }
