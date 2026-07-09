from datetime import UTC, datetime

import httpx
import pytest

from aeroroute_api.application.services.navigation import (
    _attach_degraded_terminal_procedures,
    _compose_navigation_path,
    _matching_star,
    _select_connected_fixes,
    enrich_winner_with_airac,
)
from aeroroute_api.application.services.airway_graph import (
    AirwayPathPoint,
    find_airway_path,
)
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.application.services.terminal_options import (
    IncompatibleRunwayError,
    procedure_options,
    runway_options,
    validate_runway_selection,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracAirwayPoint,
    AiracFix,
    AiracNavigationClient,
    AiracProcedure,
    AiracProcedurePoint,
    AiracProviderError,
    AiracRunway,
)
from aeroroute_api.infrastructure.weather.open_meteo import SurfaceWind


@pytest.mark.anyio
async def test_airac_client_selects_nearest_eligible_fix() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"X-AIRAC-Cycle": "2607"},
            json={
                "status": "success",
                "data": [
                    {
                        "identifier": "D180B",
                        "latitude": 40.45,
                        "longitude": -3.57,
                        "distance_nm": 1,
                        "region": "LE",
                        "type": {"code": "I"},
                    },
                    {
                        "identifier": "BITIS",
                        "latitude": 40.1,
                        "longitude": -4.0,
                        "distance_nm": 12,
                        "region": "LE",
                        "type": {"code": "W"},
                    },
                ],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        result = await AiracNavigationClient(http).nearest_fix(40.47, -3.56)

    assert result is not None
    assert result.identifier == "BITIS"
    assert result.cycle == "2607"


@pytest.mark.anyio
async def test_airac_client_reads_confirmed_airway_route() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["from"] == "ALPOB"
        assert request.url.params["to"] == "SULAF"
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [{"identifier": "L768", "segments": []}],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        result = await AiracNavigationClient(http).airway_route(
            "ALPOB", "SULAF"
        )

    assert result == ("L768",)


@pytest.mark.anyio
async def test_airac_client_caches_airway_route() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": [{"identifier": "L768", "segments": []}],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        client = AiracNavigationClient(http)
        first = await client.airway_route("ALPOB", "SULAF")
        second = await client.airway_route("ALPOB", "SULAF")
        # A different endpoint pair must not share the cache entry.
        await client.airway_route("OTHER", "PAIR")

    assert first == second == ("L768",)
    assert calls == 2
    assert client.manifest()["cache_entries"]["airway_routes"] == 2
    assert client.manifest()["cache_hits"] == 1


@pytest.mark.anyio
async def test_airac_client_caches_nearby_fixes_by_quantized_position() -> (
    None
):
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"X-AIRAC-Cycle": "2607"},
            json={
                "status": "success",
                "data": [
                    {
                        "identifier": "BITIS",
                        "latitude": 40.1,
                        "longitude": -4.0,
                        "distance_nm": 12,
                        "region": "LE",
                        "type": {"code": "W"},
                    }
                ],
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        client = AiracNavigationClient(http)
        first = await client.nearby_fixes(40.4700, -3.5600)
        # Sub-hundredth-of-a-degree jitter (well under the 1.1 km quantization
        # bucket, negligible against a 120 NM search radius) must reuse the
        # same cache entry rather than issuing a second request.
        second = await client.nearby_fixes(40.4701, -3.5599)

    assert first == second
    assert calls == 1
    assert client.manifest()["cache_entries"]["nearby_fixes"] == 1
    assert client.manifest()["cache_hits"] == 1


class _FixClient:
    async def nearest_fix(
        self, latitude_deg: float, longitude_deg: float, radius_nm: float = 120
    ) -> AiracFix:
        return AiracFix(
            identifier="SATAR",
            latitude_deg=latitude_deg + 0.1,
            longitude_deg=longitude_deg + 0.1,
            region="LE",
            fix_type="W",
            distance_nm=8.5,
            cycle="2607",
        )

    async def airway_route(
        self, from_identifier: str, to_identifier: str
    ) -> tuple[str, ...]:
        return ("L768",)

    async def nearby_fixes(
        self,
        latitude_deg: float,
        longitude_deg: float,
        radius_nm: float = 120,
        limit: int = 5,
    ) -> tuple[AiracFix, ...]:
        return (await self.nearest_fix(latitude_deg, longitude_deg),)

    async def airways_for_fix(self, identifier: str) -> tuple[str, ...]:
        return ("L768",)

    async def airway_points(
        self, identifier: str
    ) -> tuple[AiracAirwayPoint, ...]:
        raise AiracProviderError("fixture uses coarse fallback")

    async def procedures(self, airport: str, procedure_type: str) -> tuple:
        return ()


@pytest.mark.anyio
async def test_enrichment_labels_internal_nodes_with_airac_provenance() -> None:
    result = optimize_still_air(
        40.47,
        -3.56,
        40.64,
        -73.78,
        "A320",
        "minimum_fuel",
    )

    enriched = await enrich_winner_with_airac(result, _FixClient())  # type: ignore[arg-type]

    assert enriched.winner is not None
    internal = enriched.winner.waypoints[1:-1]
    assert internal
    assert all(point.kind == "navigation_fix" for point in internal)
    assert all(point.display_name == "SATAR" for point in internal)
    assert all(point.airac_cycle == "2607" for point in internal)
    assert all(point.inbound_via == "L768" for point in internal[1:])
    assert all(point.airway_validated for point in internal[1:])
    assert any(
        flag.code == "NAVIGATION_AIRAC" for flag in enriched.data_quality
    )


def test_selector_prefers_connected_fixes_over_nearest_dct() -> None:
    def fix(identifier: str, distance_nm: float) -> AiracFix:
        return AiracFix(
            identifier,
            40,
            -3,
            "LE",
            "W",
            distance_nm,
            "2607",
        )

    nearest_a = fix("NEARA", 1)
    connected_a = fix("CONNA", 12)
    nearest_b = fix("NEARB", 1)
    connected_b = fix("CONNB", 12)

    selected = _select_connected_fixes(
        ((nearest_a, connected_a), (nearest_b, connected_b)),
        {
            "NEARA": (),
            "NEARB": (),
            "CONNA": ("L768",),
            "CONNB": ("L768",),
        },
    )

    assert [item.identifier for item in selected if item] == ["CONNA", "CONNB"]


def test_airway_graph_crosses_between_airways_at_shared_fix() -> None:
    def point(identifier: str, airway: str) -> AiracAirwayPoint:
        return AiracAirwayPoint(identifier, 40, -3, airway, "2607")

    path = find_airway_path(
        (
            (point("START", "L768"), point("JOIN", "L768")),
            (point("JOIN", "M601"), point("GOAL", "M601")),
        ),
        {"START"},
        {"GOAL"},
    )

    assert [item.point.identifier for item in path] == ["START", "JOIN", "GOAL"]
    assert [item.inbound_airway for item in path] == [None, "L768", "M601"]


@pytest.mark.anyio
async def test_airac_client_parses_runway_procedure_points() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/procedures"):
            return httpx.Response(
                200,
                json={"data": [{"identifier": "SENP2F"}]},
            )
        return httpx.Response(
            200,
            headers={"X-AIRAC-Cycle": "2607"},
            json={
                "data": {
                    "identifier": "SENP2F",
                    "runway_transitions": {
                        "30B": [
                            {
                                "fix_identifier": "DB570",
                                "fix_coordinates": {"lat": 25.29, "lon": 55.29},
                            },
                            {
                                "fix_identifier": "SENPA",
                                "fix_coordinates": {"lat": 25.33, "lon": 54.53},
                            },
                        ]
                    },
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        procedures = await AiracNavigationClient(http).procedures("OMDB", "SID")

    assert procedures[0].identifier == "SENP2F"
    assert procedures[0].runway == "30B"
    assert [point.identifier for point in procedures[0].points] == [
        "DB570",
        "SENPA",
    ]


@pytest.mark.anyio
async def test_airac_client_expands_both_runway_ends() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"X-AIRAC-Cycle": "2607"},
            json={
                "data": {
                    "runways": [
                        {
                            "base_identifier": "14R",
                            "base_bearing": 142,
                            "reciprocal_identifier": "32L",
                            "reciprocal_bearing": 322,
                            "length_ft": 13084,
                            "width_ft": 197,
                            "surface": "asphalt",
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        runways = await AiracNavigationClient(http).runways("LEMD")

    assert [runway.identifier for runway in runways] == ["14R", "32L"]
    assert runways[1].bearing_deg == 322
    assert runways[1].cycle == "2607"


@pytest.mark.anyio
async def test_airac_client_derives_missing_runway_bearing() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": {
                    "runways": [
                        {
                            "base_identifier": "16R",
                            "reciprocal_identifier": "34L",
                            "length_ft": 13123,
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        runways = await AiracNavigationClient(http).runways("RJAA")

    assert [(runway.identifier, runway.bearing_deg) for runway in runways] == [
        ("16R", 160),
        ("34L", 340),
    ]


@pytest.mark.anyio
async def test_airac_cache_expires_and_records_cycle_manifest() -> None:
    calls = 0
    now = [100.0]

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            headers={"X-AIRAC-Cycle": "2607"},
            json={
                "data": {
                    "runways": [
                        {
                            "base_identifier": "16R",
                            "reciprocal_identifier": "34L",
                            "length_ft": 13_123,
                        }
                    ]
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        client = AiracNavigationClient(
            http, cache_ttl_s=60, clock=lambda: now[0]
        )
        await client.runways("RJAA")
        await client.runways("RJAA")
        now[0] = 161.0
        await client.runways("RJAA")

    assert calls == 2
    assert client.manifest() == {
        "source": "airac.net",
        "base_url": "https://airac.net/api/v1",
        "observed_cycles": ["2607"],
        "cache_ttl_s": 60,
        "cache_entries": {
            "airports": 1,
            "airways": 0,
            "memberships": 0,
            "procedures": 0,
            "runways": 1,
            "nearby_fixes": 0,
            "airway_routes": 0,
        },
        "cache_hits": 1,
        "cache_misses": 4,
        "loading": "on_demand",
    }


@pytest.mark.anyio
async def test_airac_client_parses_runway_independent_star() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/procedures"):
            return httpx.Response(
                200, json={"data": [{"identifier": "CAMRN5"}]}
            )
        return httpx.Response(
            200,
            headers={"X-AIRAC-Cycle": "2607"},
            json={
                "data": {
                    "identifier": "CAMRN5",
                    "runway_transitions": [],
                    "transitions": {
                        "ALL": [
                            {
                                "fix_identifier": "SIE",
                                "fix_coordinates": {"lat": 39.1, "lon": -74.8},
                            },
                            {
                                "fix_identifier": "CAMRN",
                                "fix_coordinates": {
                                    "lat": 40.02,
                                    "lon": -73.86,
                                },
                            },
                        ]
                    },
                }
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler)
    ) as http:
        procedures = await AiracNavigationClient(http).procedures(
            "KJFK", "STAR"
        )

    assert procedures[0].runway == "ALL"
    assert [point.identifier for point in procedures[0].points] == [
        "SIE",
        "CAMRN",
    ]


class _TerminalClient:
    def __init__(self) -> None:
        self._runways = (
            AiracRunway("30L", 300, 12000, 200, "asphalt", "2607"),
            AiracRunway("12R", 120, 13000, 200, "asphalt", "2607"),
        )
        self._procedures = (
            AiracProcedure(
                "SENP2F",
                "SID",
                "30B",
                (
                    AiracProcedurePoint("DB570", 25.29, 55.29),
                    AiracProcedurePoint("SENPA", 25.33, 54.53),
                ),
                "2607",
            ),
        )

    async def runways(self, _airport: str):
        return self._runways

    async def procedures(self, _airport: str, _procedure_type: str):
        return self._procedures


@pytest.mark.anyio
async def test_runway_options_recommend_compatible_runway() -> None:
    client = _TerminalClient()

    result = await runway_options(client, "OMDB", "SID")  # type: ignore[arg-type]
    procedures = await procedure_options(  # type: ignore[arg-type]
        client, "OMDB", "SID", "30L"
    )

    assert result.suggested_runway == "30L"
    assert result.items[0].compatible_procedures == 1
    assert [item.identifier for item in procedures.items] == ["SENP2F"]


@pytest.mark.anyio
async def test_runway_options_prefer_headwind_over_longer_runway() -> None:
    client = _TerminalClient()
    client._procedures = (
        *client._procedures,
        AiracProcedure(
            "ANVI5G",
            "SID",
            "12B",
            (
                AiracProcedurePoint("DB600", 25.2, 55.3),
                AiracProcedurePoint("ANVIX", 25.4, 55.6),
            ),
            "2607",
        ),
    )

    result = await runway_options(  # type: ignore[arg-type]
        client,
        "OMDB",
        "SID",
        SurfaceWind(
            speed_kt=20,
            direction_from_deg=300,
            valid_at_utc=datetime(2026, 6, 28, 12, tzinfo=UTC),
        ),
    )

    assert result.suggested_runway == "30L"
    selected = next(item for item in result.items if item.suggested)
    assert selected.headwind_component_kt == pytest.approx(20)
    assert result.surface_wind_source == "open-meteo"


@pytest.mark.anyio
async def test_explicit_runway_without_procedure_is_rejected() -> None:
    with pytest.raises(IncompatibleRunwayError):
        await validate_runway_selection(  # type: ignore[arg-type]
            _TerminalClient(), "OMDB", "SID", "12R"
        )


def test_navigation_path_connects_sid_airway_and_star() -> None:
    sid = AiracProcedure(
        "SENP2F",
        "SID",
        "30B",
        (
            AiracProcedurePoint("DB570", 25.29, 55.29),
            AiracProcedurePoint("SENPA", 25.33, 54.53),
        ),
        "2607",
    )
    star = AiracProcedure(
        "PRAD4D",
        "STAR",
        "32B",
        (
            AiracProcedurePoint("PRADO", 40.15, -2.01),
            AiracProcedurePoint("RUDBI", 40.26, -3.14),
        ),
        "2607",
    )
    airway_path = (
        AirwayPathPoint(
            AiracAirwayPoint("SENPA", 25.33, 54.53, "N571", "2607"), None
        ),
        AirwayPathPoint(
            AiracAirwayPoint("VARUT", 39.2, -0.8, "Z224", "2607"), "N571"
        ),
        AirwayPathPoint(
            AiracAirwayPoint("PRADO", 40.15, -2.01, "Z224", "2607"),
            "Z224",
        ),
    )

    selected_star = _matching_star((star,), airway_path)
    route = _compose_navigation_path(airway_path, sid, selected_star)

    assert [point.identifier for point in route] == [
        "DB570",
        "SENPA",
        "VARUT",
        "PRADO",
        "RUDBI",
    ]
    assert route[0].procedure_type == "SID"
    assert route[-1].procedure_type == "STAR"


def test_degraded_oceanic_route_retains_terminal_procedures_and_dct() -> None:
    result = optimize_still_air(
        40.47,
        -3.56,
        40.64,
        -73.78,
        "A320",
        "minimum_fuel",
    )
    assert result.winner is not None
    sid = AiracProcedure(
        "VAST2N",
        "SID",
        "36B",
        (
            AiracProcedurePoint("MD100", 40.6, -3.5),
            AiracProcedurePoint("VASTO", 41.0, -4.0),
        ),
        "2606",
    )
    star = AiracProcedure(
        "CAMRN5",
        "STAR",
        "ALL",
        (
            AiracProcedurePoint("SIE", 39.1, -74.8),
            AiracProcedurePoint("CAMRN", 40.02, -73.86),
        ),
        "2606",
    )

    route_points = list(result.winner.waypoints)
    route_points[0] = route_points[0].model_copy(update={"kind": "airport"})
    route_points[-1] = route_points[-1].model_copy(update={"kind": "airport"})
    points = _attach_degraded_terminal_procedures(
        result.winner, route_points, sid, star
    )

    assert points[1].procedure_identifier == "VAST2N"
    first_enroute = next(
        point
        for point in points
        if point.procedure_type is None and point.kind != "airport"
    )
    assert first_enroute.inbound_via == "DCT"
    assert not first_enroute.airway_validated
    first_star = next(
        point for point in points if point.procedure_type == "STAR"
    )
    assert first_star.inbound_via == "DCT"
    assert points[-1].inbound_via == "CAMRN5"
    assert points[-1].cumulative_fuel_kg == pytest.approx(result.winner.fuel_kg)
