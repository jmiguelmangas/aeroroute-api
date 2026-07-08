from types import SimpleNamespace

import pytest

from aeroroute_api.application.services.route_support import (
    assess_route_support,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracProcedure,
    AiracProcedurePoint,
    AiracProviderError,
    AiracRunway,
)


class FakeNavigation:
    def __init__(
        self, *, fail: bool = False, missing_procedures: bool = False
    ) -> None:
        self.fail = fail
        self.missing_procedures = missing_procedures

    async def runways(self, airport: str) -> tuple[AiracRunway, ...]:
        if self.fail:
            raise AiracProviderError("offline")
        if self.missing_procedures:
            return ()
        return (
            AiracRunway(
                identifier="32L" if airport.upper() == "LEMD" else "04L",
                bearing_deg=320.0,
                length_ft=12_000.0,
                width_ft=200.0,
                surface="asphalt",
                cycle="2607",
            ),
        )

    async def procedures(
        self, airport: str, procedure_type: str
    ) -> tuple[AiracProcedure, ...]:
        if self.fail:
            raise AiracProviderError("offline")
        return (
            AiracProcedure(
                identifier="DEP1A" if procedure_type == "SID" else "ARR2B",
                procedure_type=procedure_type,
                runway="32" if airport.upper() == "LEMD" else "04",
                points=(
                    AiracProcedurePoint("FIXA", 40.0, -3.0),
                    AiracProcedurePoint("FIXB", 41.0, -4.0),
                ),
                cycle="2607",
            ),
        )

    def manifest(self) -> dict[str, object]:
        return {
            "source": "airac.net",
            "base_url": "https://airac.net/api/v1",
            "observed_cycles": ["2607"] if not self.fail else [],
            "cache_ttl_s": 3600,
            "cache_entries": {
                "airports": 0,
                "airways": 0,
                "memberships": 0,
                "procedures": 0,
                "runways": 0,
            },
            "cache_hits": 0,
            "cache_misses": 0,
            "loading": "on_demand",
        }


def airport(code: str) -> SimpleNamespace:
    return SimpleNamespace(icao_code=code)


@pytest.mark.anyio
async def test_route_support_accepts_airports_with_terminal_airac_coverage() -> None:
    result = await assess_route_support(
        "LEMD",
        "KJFK",
        [airport("LEMD"), airport("KJFK")],
        FakeNavigation(),  # type: ignore[arg-type]
    )

    assert result.supported
    assert result.status == "supported"
    assert result.airac_cycle == "2607"
    assert result.problems == []
    assert [item.procedure_type for item in result.airports] == ["SID", "STAR"]


@pytest.mark.anyio
async def test_route_support_rejects_airport_missing_from_active_snapshot() -> None:
    result = await assess_route_support(
        "LEMD",
        "ZZZZ",
        [airport("LEMD")],
        FakeNavigation(),  # type: ignore[arg-type]
    )

    assert not result.supported
    assert result.status == "unsupported"
    assert result.problems[0].code == "airport_not_supported"
    assert result.problems[0].airport_icao == "ZZZZ"


@pytest.mark.anyio
async def test_route_support_returns_stable_provider_unavailable_problem() -> None:
    result = await assess_route_support(
        "LEMD",
        "KJFK",
        [airport("LEMD"), airport("KJFK")],
        FakeNavigation(fail=True),  # type: ignore[arg-type]
    )

    assert not result.supported
    assert result.status == "unavailable"
    assert result.problems[0].code == "navigation_provider_unavailable"


@pytest.mark.anyio
async def test_route_support_reports_missing_terminal_coverage() -> None:
    result = await assess_route_support(
        "LEMD",
        "KJFK",
        [airport("LEMD"), airport("KJFK")],
        FakeNavigation(missing_procedures=True),  # type: ignore[arg-type]
    )

    assert not result.supported
    assert result.status == "unsupported"
    assert {problem.code for problem in result.problems} == {
        "runway_procedure_coverage_missing"
    }
    assert {problem.airport_icao for problem in result.problems} == {
        "LEMD",
        "KJFK",
    }
