"""Educational fuel, destination-alternate and diversion planning."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol, Sequence

from aeroroute_optimizer import public as optimizer

from aeroroute_api.application.dto.optimization import (
    DataQualityFlag,
    DestinationAlternate,
    EnrouteDiversion,
    FuelPlanResponse,
    OptimizationResponse,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracNavigationClient,
    AiracProviderError,
    AiracRunway,
)

METERS_PER_NM = 1_852.0


class AirportRecord(Protocol):
    icao_code: str
    name: str
    airport_type: str
    latitude_deg: float
    longitude_deg: float


@dataclass(frozen=True, slots=True)
class _RunwayAudit:
    compatible: bool
    longest_ft: float | None
    cycle: str | None
    available: bool


async def add_preoperational_planning(
    response: OptimizationResponse,
    airports: Sequence[AirportRecord],
    navigation: AiracNavigationClient,
    *,
    include_diversions: bool = True,
) -> OptimizationResponse:
    """Compute the destination alternate, fuel plan, and (optionally)
    en-route diversions for a candidate result.

    ``include_diversions=False`` skips the diversion-candidate AIRAC audits
    entirely. Diversions never feed the mass/fuel convergence loop that
    calls this function repeatedly while narrowing reserve_mass_kg -- only
    fuel_plan does, via takeoff_fuel_kg/trip_fuel_kg -- so computing them on
    every iteration was pure waste: whatever this function returns mid-loop
    is discarded once the loop converges and calls it one final time with
    include_diversions=True (the default) for the response actually served.
    """
    request = response.request
    winner = response.winner
    if request is None or winner is None or len(winner.geometry) < 2:
        return response

    planning = optimizer.fuel_planning_assumptions(request.aircraft_type)
    origin_code = request.origin_icao.upper()
    destination_code = request.destination_icao.upper()
    supported_types = {"large_airport", "medium_airport"}
    unique_candidates = {
        airport.icao_code.upper(): airport
        for airport in airports
        if airport.airport_type in supported_types
        and airport.icao_code.upper() not in {origin_code, destination_code}
    }
    candidates = list(unique_candidates.values())
    by_code = {airport.icao_code.upper(): airport for airport in candidates}
    destination = optimizer.GeoPoint(
        winner.geometry[-1].latitude_deg,
        winner.geometry[-1].longitude_deg,
    )
    ranked_alternates = sorted(
        candidates,
        key=lambda airport: _distance_nm(destination, _airport_point(airport)),
    )
    requested_code = (
        request.destination_alternate_icao.upper()
        if request.destination_alternate_icao
        else None
    )
    if requested_code is not None:
        selected_pool = (
            [by_code[requested_code]] if requested_code in by_code else []
        )
    else:
        selected_pool = [
            airport
            for airport in ranked_alternates
            if 25.0
            <= _distance_nm(destination, _airport_point(airport))
            <= 800.0
        ][:8]

    alternate, alternate_audit = await _select_alternate(
        selected_pool,
        navigation,
        planning.minimum_runway_length_ft,
        require_compatible=requested_code is None,
    )
    quality = list(response.data_quality)
    if requested_code and alternate is None:
        quality.append(
            DataQualityFlag(
                code="ALTERNATE_NOT_SUPPORTED",
                severity="warning",
                message=(
                    f"Requested alternate {requested_code} is not a supported "
                    "supported airport distinct from origin and destination."
                ),
            )
        )
    if alternate is None and requested_code is None:
        quality.append(
            DataQualityFlag(
                code="ALTERNATE_UNAVAILABLE",
                severity="warning",
                message="No runway-compatible destination alternate was found.",
            )
        )

    alternate_response = None
    alternate_fuel_kg = 0.0
    if alternate is not None and alternate_audit is not None:
        alternate_distance_nm = _distance_nm(
            destination, _airport_point(alternate)
        )
        alternate_fuel_kg = _estimate_alternate_fuel(
            winner.fuel_kg,
            winner.distance_m,
            alternate_distance_nm * METERS_PER_NM,
            planning.holding_fuel_flow_kg_s,
        )
        average_ground_speed_mps = winner.distance_m / winner.time_s
        alternate_response = DestinationAlternate(
            icao_code=alternate.icao_code.upper(),
            name=alternate.name,
            distance_from_destination_nm=round(alternate_distance_nm, 1),
            estimated_flight_time_minutes=round(
                alternate_distance_nm
                * METERS_PER_NM
                / average_ground_speed_mps
                / 60.0,
                1,
            ),
            estimated_fuel_kg=round(alternate_fuel_kg, 1),
            longest_published_runway_ft=alternate_audit.longest_ft,
            runway_compatible=alternate_audit.compatible,
            selection="requested" if requested_code else "suggested",
            navigation_source=(
                "airac.net" if alternate_audit.available else None
            ),
            airac_cycle=alternate_audit.cycle,
            rationale=[
                (
                    "Requested destination alternate retained for review."
                    if requested_code
                    else "Nearest supported destination alternate with a published runway meeting the aircraft planning threshold."
                ),
                "Weather minima, NOTAM, airport status and operational approval are not evaluated.",
            ],
        )
        if not alternate_audit.compatible:
            quality.append(
                DataQualityFlag(
                    code="ALTERNATE_RUNWAY_INCOMPATIBLE",
                    severity="warning",
                    message=(
                        f"Alternate {alternate.icao_code.upper()} has no "
                        "published runway meeting the planning threshold."
                    ),
                )
            )

    mass = optimizer.aircraft_mass_assumptions(request.aircraft_type)
    empty_and_payload_mass_kg = (
        planning.operating_empty_mass_kg + request.payload_mass_kg
        if request.payload_mass_kg is not None
        else mass.empty_and_payload_mass_kg
    )
    contingency_percent = (
        request.contingency_percent
        if request.contingency_percent is not None
        else 5.0
    )
    final_reserve_minutes = (
        request.final_reserve_minutes
        if request.final_reserve_minutes is not None
        else 30.0
    )
    extra_fuel_kg = (
        request.extra_fuel_kg if request.extra_fuel_kg is not None else 0.0
    )
    policy = optimizer.FuelPolicy(
        contingency_percent=contingency_percent,
        final_reserve_minutes=final_reserve_minutes,
    )
    calculated = optimizer.build_fuel_plan(
        empty_and_payload_mass_kg=empty_and_payload_mass_kg,
        trip_fuel_kg=winner.fuel_kg,
        alternate_fuel_kg=alternate_fuel_kg,
        holding_fuel_flow_kg_s=planning.holding_fuel_flow_kg_s,
        taxi_fuel_kg=planning.taxi_fuel_kg,
        extra_fuel_kg=extra_fuel_kg,
        policy=policy,
    )
    fuel_plan = FuelPlanResponse(
        **{
            field: getattr(calculated, field)
            for field in calculated.__dataclass_fields__
        },
        assumptions=[
            f"Contingency is {contingency_percent:g}% of modeled trip fuel.",
            f"Final reserve is {final_reserve_minutes:g} minutes at the curated holding-flow assumption.",
            "Alternate fuel scales modeled trip burn by still-air great-circle distance with a 15-minute holding-flow floor.",
            "Taxi and holding flows are curated aircraft-type approximations.",
            (
                f"Operating empty mass plus requested payload: "
                f"{empty_and_payload_mass_kg:,.0f} kg."
                if request.payload_mass_kg is not None
                else "Default combined empty-and-payload mass assumption used."
            ),
        ],
    )
    diversions: list[EnrouteDiversion] = []
    if include_diversions:
        diversions = await _select_diversions(
            candidates,
            winner.geometry,
            navigation,
            planning.minimum_runway_length_ft,
            excluded={
                origin_code,
                destination_code,
                alternate.icao_code.upper() if alternate is not None else "",
            },
        )
        if not diversions:
            quality.append(
                DataQualityFlag(
                    code="ENROUTE_DIVERSIONS_UNAVAILABLE",
                    severity="warning",
                    message=(
                        "No runway-compatible en-route diversion candidate "
                        "was found within 750 NM of the modeled route."
                    ),
                )
            )
    return response.model_copy(
        update={
            "fuel_plan": fuel_plan,
            "destination_alternate": alternate_response,
            "enroute_diversions": diversions,
            "data_quality": quality,
        }
    )


async def _select_alternate(
    airports: Sequence[AirportRecord],
    navigation: AiracNavigationClient,
    minimum_runway_ft: float,
    *,
    require_compatible: bool,
) -> tuple[AirportRecord | None, _RunwayAudit | None]:
    audits = await asyncio.gather(
        *(
            _audit_runways(navigation, airport.icao_code, minimum_runway_ft)
            for airport in airports
        )
    )
    for airport, audit in zip(airports, audits, strict=True):
        if audit.compatible or not require_compatible:
            return airport, audit
    return None, None


async def _select_diversions(
    airports: Sequence[AirportRecord],
    geometry: Sequence[object],
    navigation: AiracNavigationClient,
    minimum_runway_ft: float,
    excluded: set[str],
) -> list[EnrouteDiversion]:
    route = [
        optimizer.GeoPoint(point.latitude_deg, point.longitude_deg)
        for point in geometry
    ]
    ranked: list[tuple[float, float, AirportRecord]] = []
    for airport in airports:
        if airport.icao_code.upper() in excluded:
            continue
        distances = [
            _distance_nm(_airport_point(airport), point) for point in route
        ]
        nearest_index = min(range(len(distances)), key=distances.__getitem__)
        fraction = nearest_index / max(len(route) - 1, 1)
        if 0.1 <= fraction <= 0.9 and distances[nearest_index] <= 750.0:
            ranked.append((distances[nearest_index], fraction, airport))
    ranked.sort(key=lambda item: item[0])
    shortlist = ranked[:12]
    audits = await asyncio.gather(
        *(
            _audit_runways(navigation, item[2].icao_code, minimum_runway_ft)
            for item in shortlist
        )
    )
    results: list[EnrouteDiversion] = []
    for (distance, fraction, airport), audit in zip(
        shortlist, audits, strict=True
    ):
        if not audit.compatible:
            continue
        results.append(
            EnrouteDiversion(
                icao_code=airport.icao_code.upper(),
                name=airport.name,
                distance_to_route_nm=round(distance, 1),
                nearest_route_fraction=round(fraction, 3),
                longest_published_runway_ft=audit.longest_ft,
                runway_compatible=True,
                navigation_source="airac.net",
                airac_cycle=audit.cycle,
                rationale=[
                    "Airport near the modeled route with a published runway meeting the aircraft planning threshold.",
                    "Weather, NOTAM, airport status and ETOPS/EDTO suitability are not evaluated.",
                ],
            )
        )
        if len(results) == 3:
            break
    return results


async def _audit_runways(
    navigation: AiracNavigationClient,
    airport_code: str,
    minimum_runway_ft: float,
) -> _RunwayAudit:
    try:
        runways = await navigation.runways(airport_code)
    except AiracProviderError:
        return _RunwayAudit(False, None, None, False)
    longest = max((runway.length_ft for runway in runways), default=None)
    cycle = _latest_cycle(runways)
    return _RunwayAudit(
        compatible=bool(longest is not None and longest >= minimum_runway_ft),
        longest_ft=longest,
        cycle=cycle,
        available=True,
    )


def _latest_cycle(runways: Sequence[AiracRunway]) -> str | None:
    cycles = sorted({runway.cycle for runway in runways if runway.cycle})
    return cycles[-1] if cycles else None


def _estimate_alternate_fuel(
    trip_fuel_kg: float,
    trip_distance_m: float,
    alternate_distance_m: float,
    holding_fuel_flow_kg_s: float,
) -> float:
    distance_scaled = trip_fuel_kg * alternate_distance_m / trip_distance_m
    return max(distance_scaled, holding_fuel_flow_kg_s * 15.0 * 60.0)


def _airport_point(airport: AirportRecord) -> optimizer.GeoPoint:
    return optimizer.GeoPoint(airport.latitude_deg, airport.longitude_deg)


def _distance_nm(left: optimizer.GeoPoint, right: optimizer.GeoPoint) -> float:
    return optimizer.distance_m(left, right) / METERS_PER_NM
