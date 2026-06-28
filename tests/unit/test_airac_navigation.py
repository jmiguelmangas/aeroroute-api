import httpx
import pytest

from aeroroute_api.application.services.navigation import (
    _select_connected_fixes,
    enrich_winner_with_airac,
)
from aeroroute_api.application.services.airway_graph import find_airway_path
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.navigation.airac import (
    AiracAirwayPoint,
    AiracFix,
    AiracNavigationClient,
    AiracProviderError,
)


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
