"""Benchmark proving AIRAC enrichment fans out independent awaits.

``enrich_winner_with_airac`` (and the ``runway_options`` helper it calls)
made several independent AIRAC lookups sequentially on a cold cache. This
test builds a synthetic "large" route (~30 internal navigation segments,
matching HLD S11.2's 20-100 layer sampling for long routes) against a fake
AIRAC client with an injectable artificial per-call latency, and asserts
that wall-clock time for enrichment stays close to a small constant
multiple of that latency rather than scaling with the number of segments.
It must fail against the pre-fix sequential implementation and pass
against the concurrent one (verified via a stash/restore drill).
"""

import asyncio
import time

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    GeoJsonGeometry,
    OptimizationRequest,
    OptimizationResponse,
    RoutePoint,
    WaypointDetail,
)
from aeroroute_api.application.services.navigation import (
    enrich_winner_with_airac,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracAirwayPoint,
    AiracFix,
    AiracProcedure,
    AiracRunway,
)

SEGMENT_COUNT = 30
LATENCY_S = 0.03


class LatencyAirac:
    """Duck-typed async AIRAC client double with injectable per-call latency.

    Every network-shaped method sleeps for ``latency_s`` before returning,
    so wall-clock time directly reflects how many *rounds* of calls the
    caller schedules (sequential rounds add up; concurrent calls within a
    round do not).
    """

    cycle = "2607"

    def __init__(self, latency_s: float) -> None:
        self._latency_s = latency_s
        self.call_count = 0

    async def runways(self, airport: str) -> tuple[AiracRunway, ...]:
        await asyncio.sleep(self._latency_s)
        self.call_count += 1
        return (
            AiracRunway(
                identifier="09",
                bearing_deg=90.0,
                length_ft=10_000.0,
                width_ft=150.0,
                surface="ASPH",
                cycle=self.cycle,
            ),
        )

    async def procedures(
        self, airport: str, procedure_type: str
    ) -> tuple[AiracProcedure, ...]:
        await asyncio.sleep(self._latency_s)
        self.call_count += 1
        # Empty on purpose: keeps the enriched route free of SID/STAR
        # procedure_type tags so every internal fix stays eligible for the
        # airway-validation loop under test (fix #3).
        return ()

    async def nearby_fixes(
        self,
        latitude_deg: float,
        longitude_deg: float,
        radius_nm: float = 120.0,
        limit: int = 5,
    ) -> tuple[AiracFix, ...]:
        await asyncio.sleep(self._latency_s)
        self.call_count += 1
        identifier = f"NAV{round(latitude_deg * 10_000)}_{round(longitude_deg * 10_000)}"
        return (
            AiracFix(
                identifier=identifier,
                latitude_deg=latitude_deg,
                longitude_deg=longitude_deg,
                region="ZZ",
                fix_type="W",
                distance_nm=1.0,
                cycle=self.cycle,
            ),
        )

    async def airways_for_fix(self, identifier: str) -> tuple[str, ...]:
        await asyncio.sleep(self._latency_s)
        self.call_count += 1
        # Always empty: forces _discover_corridor_path to bail out (fewer
        # than two connected layers) so enrichment falls through to the
        # nearby-fixes fallback path that contains the segment loop.
        return ()

    async def airway_points(
        self, identifier: str
    ) -> tuple[AiracAirwayPoint, ...]:
        await asyncio.sleep(self._latency_s)
        self.call_count += 1
        return ()

    async def airway_route(
        self, from_identifier: str, to_identifier: str
    ) -> tuple[str, ...]:
        await asyncio.sleep(self._latency_s)
        self.call_count += 1
        return ("UT900",)


def _build_large_winner(segment_count: int) -> CandidateResponse:
    origin_lat, origin_lon = 40.0, -3.0
    destination_lat, destination_lon = 41.0, 4.0
    waypoints = [
        WaypointDetail(
            node_id="origin",
            display_name="LEMD",
            kind="airport",
            latitude_deg=origin_lat,
            longitude_deg=origin_lon,
            flight_level=0,
            elapsed_time_s=0.0,
            cumulative_distance_m=0.0,
            cumulative_fuel_kg=0.0,
            estimated_mass_kg=70_000.0,
        )
    ]
    for index in range(segment_count):
        fraction = (index + 1) / (segment_count + 1)
        waypoints.append(
            WaypointDetail(
                node_id=f"node{index}",
                display_name=f"WP{index}",
                kind="synthetic",
                latitude_deg=origin_lat
                + (destination_lat - origin_lat) * fraction,
                longitude_deg=origin_lon
                + (destination_lon - origin_lon) * fraction,
                flight_level=360,
                elapsed_time_s=0.0,
                cumulative_distance_m=0.0,
                cumulative_fuel_kg=0.0,
                estimated_mass_kg=70_000.0,
            )
        )
    waypoints.append(
        WaypointDetail(
            node_id="destination",
            display_name="LFPG",
            kind="airport",
            latitude_deg=destination_lat,
            longitude_deg=destination_lon,
            flight_level=0,
            elapsed_time_s=0.0,
            cumulative_distance_m=0.0,
            cumulative_fuel_kg=0.0,
            estimated_mass_kg=68_000.0,
        )
    )
    geometry = [
        RoutePoint(latitude_deg=point.latitude_deg, longitude_deg=point.longitude_deg)
        for point in waypoints
    ]
    return CandidateResponse(
        path=[point.display_name for point in waypoints],
        geometry=geometry,
        distance_m=1_000_000.0,
        time_s=10_000.0,
        fuel_kg=20_000.0,
        score=0.0,
        display_geojson=GeoJsonGeometry(
            type="LineString",
            coordinates=[
                [point.longitude_deg, point.latitude_deg] for point in waypoints
            ],
        ),
        waypoints=waypoints,
    )


def test_enrichment_fans_out_independent_airac_calls_concurrently() -> None:
    winner = _build_large_winner(SEGMENT_COUNT)
    request = OptimizationRequest(
        origin_icao="LEMD",
        destination_icao="LFPG",
        aircraft_type="A320",
        profile="balanced",
    )
    response = OptimizationResponse(
        status="optimal",
        algorithm_version="test",
        winner=winner,
        alternatives=[],
        solver_termination_reason="converged",
        request=request,
    )
    client = LatencyAirac(LATENCY_S)

    start = time.perf_counter()
    enriched = asyncio.run(
        enrich_winner_with_airac(response, client)  # type: ignore[arg-type]
    )
    elapsed_s = time.perf_counter() - start

    # Sanity: the segment-validation loop (fix #3) really did run over the
    # full "large graph" -- otherwise this benchmark would prove nothing.
    assert enriched.winner is not None
    navigation_fixes = [
        point
        for point in enriched.winner.waypoints
        if point.kind == "navigation_fix"
    ]
    assert len(navigation_fixes) >= SEGMENT_COUNT
    segment_pairs = len(navigation_fixes) - 1
    assert segment_pairs >= SEGMENT_COUNT - 1

    sequential_equivalent_s = segment_pairs * LATENCY_S

    # Concurrent fan-out should land close to a small constant multiple of
    # one round-trip latency, not scale with the number of segments. A
    # purely sequential implementation of the segment loop alone would take
    # >= sequential_equivalent_s (~0.87s here); we require staying well
    # under half of that, which the sequential code cannot satisfy.
    assert elapsed_s < sequential_equivalent_s / 2, (
        f"enrichment took {elapsed_s:.3f}s across {segment_pairs} segments "
        f"(sequential-equivalent {sequential_equivalent_s:.3f}s at "
        f"{LATENCY_S}s/call) -- looks sequential, not fanned out"
    )
    assert elapsed_s < 10 * LATENCY_S
