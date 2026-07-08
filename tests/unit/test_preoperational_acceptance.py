import asyncio
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from aeroroute_api.application.dto.optimization import OptimizationRequest
from aeroroute_api.application.services.flight_planning import (
    add_preoperational_planning,
)
from aeroroute_api.application.services.navigation import enrich_winner_with_airac
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.navigation.airac import (
    AiracAirwayPoint,
    AiracFix,
    AiracProcedure,
    AiracProcedurePoint,
    AiracRunway,
)


@dataclass(frozen=True, slots=True)
class Scenario:
    origin: str
    destination: str
    origin_latitude: float
    origin_longitude: float
    destination_latitude: float
    destination_longitude: float
    departure_runway: str
    arrival_runway: str
    alternate: str
    diversions: tuple[str, ...]


SCENARIOS = (
    Scenario("LEMD", "KJFK", 40.4722, -3.5608, 40.6413, -73.7781, "36L", "04L", "KPHL", ("CYQX", "KBGR")),
    Scenario("KJFK", "LEMD", 40.6413, -73.7781, 40.4722, -3.5608, "04L", "32L", "LEBL", ("CYQX", "LPPT")),
    Scenario("OMDB", "LEMD", 25.2532, 55.3657, 40.4722, -3.5608, "30R", "32L", "LEBL", ("LIRF", "LGAV")),
    Scenario("RJAA", "KSFO", 35.7647, 140.3864, 37.6213, -122.3790, "34L", "28L", "KOAK", ("PANC", "PHNL")),
)


class FrozenAirac:
    cycle = "2607"

    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.sid_exit = f"{scenario.origin[-2:]}XIT"
        self.star_entry = f"{scenario.destination[-2:]}ENT"
        self.airway = "UT900"
        self._points = self._airway_points()

    async def runways(self, airport: str) -> tuple[AiracRunway, ...]:
        airport = airport.upper()
        if airport == self.scenario.origin:
            runway = self.scenario.departure_runway
        elif airport == self.scenario.destination:
            runway = self.scenario.arrival_runway
        else:
            runway = "09"
        return (
            AiracRunway(
                identifier=runway,
                bearing_deg=90.0,
                length_ft=12_000.0,
                width_ft=150.0,
                surface="ASPH",
                cycle=self.cycle,
            ),
        )

    async def procedures(
        self, airport: str, procedure_type: str
    ) -> tuple[AiracProcedure, ...]:
        airport = airport.upper()
        if airport == self.scenario.origin and procedure_type == "SID":
            return (
                AiracProcedure(
                    identifier=f"{airport[-2:]}1A",
                    procedure_type="SID",
                    runway=self.scenario.departure_runway,
                    points=(
                        self._procedure_point(
                            f"{airport[-2:]}RWY",
                            self.scenario.origin_latitude,
                            self.scenario.origin_longitude,
                        ),
                        self._procedure_point(
                            self.sid_exit,
                            self._points[0].latitude_deg,
                            self._points[0].longitude_deg,
                        ),
                    ),
                    cycle=self.cycle,
                ),
            )
        if airport == self.scenario.destination and procedure_type == "STAR":
            return (
                AiracProcedure(
                    identifier=f"{airport[-2:]}2B",
                    procedure_type="STAR",
                    runway=self.scenario.arrival_runway,
                    points=(
                        self._procedure_point(
                            self.star_entry,
                            self._points[-1].latitude_deg,
                            self._points[-1].longitude_deg,
                        ),
                        self._procedure_point(
                            f"{airport[-2:]}RWY",
                            self.scenario.destination_latitude,
                            self.scenario.destination_longitude,
                        ),
                    ),
                    cycle=self.cycle,
                ),
            )
        return ()

    async def nearby_fixes(
        self,
        latitude_deg: float,
        longitude_deg: float,
        radius_nm: float = 120.0,
        limit: int = 5,
    ) -> tuple[AiracFix, ...]:
        ranked = sorted(
            self._points,
            key=lambda point: (
                point.latitude_deg - latitude_deg
            ) ** 2
            + (point.longitude_deg - longitude_deg) ** 2,
        )
        return tuple(
            AiracFix(
                identifier=point.identifier,
                latitude_deg=point.latitude_deg,
                longitude_deg=point.longitude_deg,
                region="ZZ",
                fix_type="W",
                distance_nm=float(index + 1),
                cycle=self.cycle,
            )
            for index, point in enumerate(ranked[:limit])
        )

    async def airways_for_fix(self, identifier: str) -> tuple[str, ...]:
        return (self.airway,) if identifier in self._airway_identifiers() else ()

    async def airway_points(
        self, identifier: str
    ) -> tuple[AiracAirwayPoint, ...]:
        return self._points if identifier == self.airway else ()

    def _airway_points(self) -> tuple[AiracAirwayPoint, ...]:
        return tuple(
            AiracAirwayPoint(
                identifier=identifier,
                latitude_deg=self.scenario.origin_latitude
                + (
                    self.scenario.destination_latitude
                    - self.scenario.origin_latitude
                )
                * fraction,
                longitude_deg=_interpolated_longitude(self.scenario, fraction),
                airway=self.airway,
                cycle=self.cycle,
            )
            for identifier, fraction in (
                (self.sid_exit, 0.18),
                (f"{self.scenario.origin[-2:]}M01", 0.36),
                (f"{self.scenario.destination[-2:]}M02", 0.62),
                (self.star_entry, 0.82),
            )
        )

    def _airway_identifiers(self) -> set[str]:
        return {point.identifier for point in self._points}

    def _procedure_point(
        self, identifier: str, latitude: float, longitude: float
    ) -> AiracProcedurePoint:
        return AiracProcedurePoint(
            identifier=identifier,
            latitude_deg=latitude,
            longitude_deg=longitude,
        )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_reference_scenarios_produce_traceable_preoperational_ofp(
    scenario: Scenario,
) -> None:
    request = OptimizationRequest(
        origin_icao=scenario.origin,
        destination_icao=scenario.destination,
        aircraft_type="B77W",
        profile="balanced",
    )
    optimized = optimize_still_air(
        scenario.origin_latitude,
        scenario.origin_longitude,
        scenario.destination_latitude,
        scenario.destination_longitude,
        request.aircraft_type,
        request.profile,
    ).model_copy(update={"request": request})
    navigation = FrozenAirac(scenario)
    enriched = asyncio.run(
        enrich_winner_with_airac(optimized, navigation)  # type: ignore[arg-type]
    )
    planned = asyncio.run(
        add_preoperational_planning(
            enriched,
            _airport_catalogue(scenario),
            navigation,  # type: ignore[arg-type]
        )
    )

    assert planned.terminal_selection is not None
    assert planned.terminal_selection.departure_runway == scenario.departure_runway
    assert planned.terminal_selection.arrival_runway == scenario.arrival_runway
    assert planned.terminal_selection.sid_identifier is not None
    assert planned.terminal_selection.star_identifier is not None
    assert planned.destination_alternate is not None
    assert planned.destination_alternate.icao_code == scenario.alternate
    assert planned.fuel_plan is not None
    assert not planned.fuel_plan.operationally_approved
    assert planned.fuel_plan.block_fuel_kg > planned.fuel_plan.trip_fuel_kg
    assert {item.icao_code for item in planned.enroute_diversions}
    assert planned.winner is not None
    route_fixes = planned.winner.waypoints
    assert any(point.procedure_type == "SID" for point in route_fixes)
    assert any(point.procedure_type == "STAR" for point in route_fixes)
    assert all(
        point.navigation_source == "airac.net"
        for point in route_fixes
        if point.kind == "navigation_fix"
    )
    assert any(flag.code == "NAVIGATION_AIRWAY_GRAPH" for flag in planned.data_quality)


def _airport_catalogue(scenario: Scenario) -> list[SimpleNamespace]:
    route_diversions = [
        _airport(code, code, scenario, fraction)
        for code, fraction in zip(scenario.diversions, (0.35, 0.65), strict=True)
    ]
    return [
        _airport(scenario.alternate, scenario.alternate, scenario, 0.96),
        *route_diversions,
    ]


def _airport(
    code: str, name: str, scenario: Scenario, fraction: float
) -> SimpleNamespace:
    return SimpleNamespace(
        icao_code=code,
        name=name,
        airport_type="large_airport",
        latitude_deg=scenario.origin_latitude
        + (scenario.destination_latitude - scenario.origin_latitude) * fraction,
        longitude_deg=_interpolated_longitude(scenario, fraction),
    )


def _interpolated_longitude(scenario: Scenario, fraction: float) -> float:
    delta = (
        (scenario.destination_longitude - scenario.origin_longitude + 180.0)
        % 360.0
    ) - 180.0
    return ((scenario.origin_longitude + delta * fraction + 180.0) % 360.0) - 180.0
