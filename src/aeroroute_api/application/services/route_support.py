"""Supported-route preflight checks for Phase 13 generalization."""

from __future__ import annotations

from typing import Protocol

from aeroroute_api.application.dto.navigation import (
    RouteSupportAirportCoverage,
    RouteSupportProblem,
    RouteSupportResponse,
)
from aeroroute_api.application.services.terminal_options import runway_options
from aeroroute_api.infrastructure.navigation.airac import (
    AiracNavigationClient,
    AiracProviderError,
)


class CatalogueAirport(Protocol):
    icao_code: str


async def assess_route_support(
    origin_icao: str,
    destination_icao: str,
    airports: list[CatalogueAirport],
    navigation: AiracNavigationClient,
) -> RouteSupportResponse:
    origin = origin_icao.upper()
    destination = destination_icao.upper()
    by_code = {airport.icao_code.upper(): airport for airport in airports}
    problems: list[RouteSupportProblem] = []
    coverage: list[RouteSupportAirportCoverage] = []

    for code in (origin, destination):
        if code not in by_code:
            problems.append(
                RouteSupportProblem(
                    code="airport_not_supported",
                    airport_icao=code,
                    message=(
                        f"{code} is not present in the active airport snapshot."
                    ),
                )
            )

    if problems:
        return _response(
            origin,
            destination,
            navigation,
            coverage,
            problems,
            status="unsupported",
        )

    try:
        origin_coverage = await _airport_coverage(navigation, origin, "SID")
        destination_coverage = await _airport_coverage(
            navigation, destination, "STAR"
        )
    except AiracProviderError:
        return _response(
            origin,
            destination,
            navigation,
            coverage,
            [
                RouteSupportProblem(
                    code="navigation_provider_unavailable",
                    message=(
                        "AIRAC runway/procedure coverage could not be checked."
                    ),
                )
            ],
            status="unavailable",
        )

    coverage = [origin_coverage, destination_coverage]
    for item in coverage:
        if not item.runway_available or not item.procedure_available:
            problems.append(
                RouteSupportProblem(
                    code="runway_procedure_coverage_missing",
                    airport_icao=item.airport_icao,
                    message=(
                        f"{item.airport_icao} has no compatible "
                        f"{item.procedure_type} runway/procedure coverage "
                        "in the current AIRAC source."
                    ),
                )
            )

    return _response(
        origin,
        destination,
        navigation,
        coverage,
        problems,
        status="unsupported" if problems else "supported",
    )


async def _airport_coverage(
    navigation: AiracNavigationClient,
    airport_icao: str,
    procedure_type: str,
) -> RouteSupportAirportCoverage:
    options = await runway_options(
        navigation,
        airport_icao,
        procedure_type,  # type: ignore[arg-type]
    )
    compatible_count = sum(item.compatible_procedures for item in options.items)
    return RouteSupportAirportCoverage(
        airport_icao=airport_icao,
        procedure_type=procedure_type,  # type: ignore[arg-type]
        runway_available=bool(options.items),
        procedure_available=compatible_count > 0,
        suggested_runway=options.suggested_runway,
        compatible_procedure_count=compatible_count,
        airac_cycle=options.airac_cycle,
    )


def _response(
    origin_icao: str,
    destination_icao: str,
    navigation: AiracNavigationClient,
    airports: list[RouteSupportAirportCoverage],
    problems: list[RouteSupportProblem],
    *,
    status: str,
) -> RouteSupportResponse:
    cycles = sorted({item.airac_cycle for item in airports if item.airac_cycle})
    return RouteSupportResponse(
        origin_icao=origin_icao,
        destination_icao=destination_icao,
        supported=status == "supported",
        status=status,  # type: ignore[arg-type]
        airac_cycle=", ".join(cycles) if cycles else None,
        navigation_manifest=navigation.manifest(),
        airports=airports,
        problems=problems,
    )
