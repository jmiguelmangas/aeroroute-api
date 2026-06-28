
import httpx
import pytest

from aeroroute_api.application.services.navigation import (
    enrich_winner_with_airac,
)
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.navigation.airac import (
    AiracFix,
    AiracNavigationClient,
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
    assert any(
        flag.code == "NAVIGATION_AIRAC" for flag in enriched.data_quality
    )
