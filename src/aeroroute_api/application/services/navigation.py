from __future__ import annotations

import asyncio
import math

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    DataQualityFlag,
    OptimizationResponse,
    WaypointDetail,
)
from aeroroute_api.application.services.airway_graph import (
    AirwayPathPoint,
    find_airway_path,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracFix,
    AiracNavigationClient,
    AiracProviderError,
)


async def enrich_winner_with_airac(
    response: OptimizationResponse,
    client: AiracNavigationClient,
) -> OptimizationResponse:
    winner = response.winner
    if winner is None or len(winner.waypoints) < 2:
        return response
    internal = winner.waypoints[1:-1]
    try:
        airway_path = await _discover_corridor_path(winner, client)
    except AiracProviderError:
        airway_path = ()
    if airway_path:
        return _response_with_connected_path(response, airway_path)
    try:
        candidate_layers = await asyncio.gather(
            *(
                client.nearby_fixes(
                    point.latitude_deg, point.longitude_deg, limit=5
                )
                for point in internal
            )
        )
        identifiers = {
            fix.identifier for layer in candidate_layers for fix in layer
        }
        memberships = dict(
            zip(
                identifiers,
                await asyncio.gather(
                    *(
                        client.airways_for_fix(identifier)
                        for identifier in identifiers
                    )
                ),
                strict=True,
            )
        )
        fixes = _select_connected_fixes(candidate_layers, memberships)
    except AiracProviderError:
        return response.model_copy(
            update={
                "data_quality": [
                    *response.data_quality,
                    DataQualityFlag(
                        code="NAVIGATION_FALLBACK",
                        severity="warning",
                        message=(
                            "AIRAC navigation fixes were unavailable; solver "
                            "nodes are shown instead."
                        ),
                    ),
                ]
            }
        )

    origin_name = (
        response.request.origin_icao if response.request else winner.path[0]
    )
    destination_name = (
        response.request.destination_icao
        if response.request
        else winner.path[-1]
    )
    points = [
        winner.waypoints[0].model_copy(
            update={"kind": "airport", "display_name": origin_name}
        )
    ]
    cycles: set[str] = set()
    for point, fix in zip(internal, fixes, strict=True):
        if fix is None:
            points.append(
                point.model_copy(
                    update={
                        "kind": "oceanic_coordinate",
                        "display_name": _coordinate_name(
                            point.latitude_deg, point.longitude_deg
                        ),
                        "navigation_source": "coordinate",
                    }
                )
            )
            continue
        if fix.cycle:
            cycles.add(fix.cycle)
        points.append(
            point.model_copy(
                update={
                    "kind": "navigation_fix",
                    "display_name": fix.identifier,
                    "latitude_deg": fix.latitude_deg,
                    "longitude_deg": fix.longitude_deg,
                    "navigation_source": "airac.net",
                    "airac_cycle": fix.cycle,
                    "airac_region": fix.region,
                    "snap_distance_nm": fix.distance_nm,
                }
            )
        )
    points.append(
        winner.waypoints[-1].model_copy(
            update={"kind": "airport", "display_name": destination_name}
        )
    )
    validated_segments = 0
    navigation_indexes = [
        index
        for index, point in enumerate(points)
        if point.kind == "navigation_fix"
    ]
    for previous_index, current_index in zip(
        navigation_indexes, navigation_indexes[1:]
    ):
        previous = points[previous_index]
        current = points[current_index]
        try:
            airways = await client.airway_route(
                previous.display_name, current.display_name
            )
        except AiracProviderError:
            airways = ()
        if airways:
            validated_segments += 1
            points[current_index] = current.model_copy(
                update={
                    "inbound_via": "/".join(airways),
                    "airway_validated": True,
                }
            )
        else:
            points[current_index] = current.model_copy(
                update={"inbound_via": "DCT", "airway_validated": False}
            )
    enriched = winner.model_copy(update={"waypoints": points})
    cycle_text = ", ".join(sorted(cycles)) if cycles else "current"
    return response.model_copy(
        update={
            "winner": CandidateResponse.model_validate(enriched),
            "data_quality": [
                *response.data_quality,
                DataQualityFlag(
                    code="NAVIGATION_AIRAC",
                    severity="info",
                    message=(
                        f"Navigation references use AIRAC.net cycle {cycle_text}; "
                        f"{validated_segments} internal segments have confirmed "
                        "airway connectivity and remaining segments are DCT."
                    ),
                ),
            ],
        }
    )


def _coordinate_name(latitude_deg: float, longitude_deg: float) -> str:
    latitude = (
        f"{abs(round(latitude_deg)):02d}{'N' if latitude_deg >= 0 else 'S'}"
    )
    longitude = (
        f"{abs(round(longitude_deg)):03d}{'E' if longitude_deg >= 0 else 'W'}"
    )
    return f"{latitude}{longitude}"


async def _discover_corridor_path(
    winner: CandidateResponse,
    client: AiracNavigationClient,
) -> tuple[AirwayPathPoint, ...]:
    origin = winner.geometry[0]
    destination = winner.geometry[-1]
    longitude_delta = (
        (destination.longitude_deg - origin.longitude_deg + 180) % 360
    ) - 180
    samples = tuple(
        (
            origin.latitude_deg
            + (destination.latitude_deg - origin.latitude_deg) * index / 13,
            ((origin.longitude_deg + longitude_delta * index / 13 + 180) % 360)
            - 180,
        )
        for index in range(14)
    )
    candidate_layers = await asyncio.gather(
        *(
            client.nearby_fixes(latitude, longitude, radius_nm=120, limit=12)
            for latitude, longitude in samples
        )
    )
    identifiers = {
        fix.identifier for layer in candidate_layers for fix in layer
    }
    memberships = dict(
        zip(
            identifiers,
            await asyncio.gather(
                *(
                    client.airways_for_fix(identifier)
                    for identifier in identifiers
                )
            ),
            strict=True,
        )
    )
    routed_layers = [
        tuple(fix for fix in layer if memberships.get(fix.identifier))[:5]
        for layer in candidate_layers
    ]
    nonempty_layers = [layer for layer in routed_layers if layer]
    if len(nonempty_layers) < 2:
        return ()
    airway_identifiers = {
        airway
        for layer in nonempty_layers
        for fix in layer
        for airway in memberships[fix.identifier]
    }
    routes = await asyncio.gather(
        *(client.airway_points(identifier) for identifier in airway_identifiers)
    )
    return find_airway_path(
        tuple(routes),
        {fix.identifier for fix in nonempty_layers[0]},
        {fix.identifier for fix in nonempty_layers[-1]},
    )


def _response_with_connected_path(
    response: OptimizationResponse,
    airway_path: tuple[AirwayPathPoint, ...],
) -> OptimizationResponse:
    winner = response.winner
    assert winner is not None
    origin_name = (
        response.request.origin_icao if response.request else winner.path[0]
    )
    destination_name = (
        response.request.destination_icao
        if response.request
        else winner.path[-1]
    )
    coordinates = [
        (winner.waypoints[0].latitude_deg, winner.waypoints[0].longitude_deg),
        *(
            (item.point.latitude_deg, item.point.longitude_deg)
            for item in airway_path
        ),
        (winner.waypoints[-1].latitude_deg, winner.waypoints[-1].longitude_deg),
    ]
    segment_distances = [
        _distance_m(first, second)
        for first, second in zip(coordinates, coordinates[1:])
    ]
    total_distance = sum(segment_distances)
    cumulative = 0.0
    cruise_levels = [
        point.flight_level
        for point in winner.waypoints[1:-1]
        if point.flight_level > 0
    ]
    cruise_level = round(sum(cruise_levels) / len(cruise_levels))
    points = [
        winner.waypoints[0].model_copy(
            update={"kind": "airport", "display_name": origin_name}
        )
    ]
    cycles: set[str] = set()
    for index, item in enumerate(airway_path, start=1):
        cumulative += segment_distances[index - 1]
        fraction = cumulative / total_distance if total_distance else 0.0
        if item.point.cycle:
            cycles.add(item.point.cycle)
        nearest_solver = winner.waypoints[
            min(
                round(fraction * (len(winner.waypoints) - 1)),
                len(winner.waypoints) - 1,
            )
        ]
        points.append(
            WaypointDetail(
                node_id=f"AIRAC:{item.point.identifier}:{index}",
                display_name=item.point.identifier,
                kind="navigation_fix",
                latitude_deg=item.point.latitude_deg,
                longitude_deg=item.point.longitude_deg,
                flight_level=cruise_level,
                elapsed_time_s=winner.time_s * fraction,
                cumulative_distance_m=winner.distance_m * fraction,
                cumulative_fuel_kg=winner.fuel_kg * fraction,
                estimated_mass_kg=(
                    winner.waypoints[0].estimated_mass_kg
                    + (
                        winner.waypoints[-1].estimated_mass_kg
                        - winner.waypoints[0].estimated_mass_kg
                    )
                    * fraction
                ),
                wind_component_kt=nearest_solver.wind_component_kt,
                navigation_source="airac.net",
                airac_cycle=item.point.cycle,
                inbound_via=item.inbound_airway or "DCT",
                airway_validated=item.inbound_airway is not None,
            )
        )
    points.append(
        winner.waypoints[-1].model_copy(
            update={
                "kind": "airport",
                "display_name": destination_name,
                "inbound_via": "DCT",
                "airway_validated": False,
            }
        )
    )
    enriched = winner.model_copy(update={"waypoints": points})
    cycle_text = ", ".join(sorted(cycles)) if cycles else "current"
    return response.model_copy(
        update={
            "winner": CandidateResponse.model_validate(enriched),
            "data_quality": [
                *response.data_quality,
                DataQualityFlag(
                    code="NAVIGATION_AIRWAY_GRAPH",
                    severity="info",
                    message=(
                        f"AIRAC.net cycle {cycle_text} produced a connected "
                        f"{len(airway_path)}-fix en-route path; airport joins remain DCT."
                    ),
                ),
            ],
        }
    )


def _distance_m(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    first_latitude = math.radians(first[0])
    second_latitude = math.radians(second[0])
    latitude_delta = second_latitude - first_latitude
    longitude_delta = math.radians(second[1] - first[1])
    value = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(first_latitude)
        * math.cos(second_latitude)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 2 * 6_371_008.8 * math.asin(min(1.0, math.sqrt(value)))


def _select_connected_fixes(
    candidate_layers: list[tuple[AiracFix, ...]]
    | tuple[tuple[AiracFix, ...], ...],
    memberships: dict[str, tuple[str, ...]],
) -> tuple[AiracFix | None, ...]:
    if not candidate_layers:
        return ()
    if any(not layer for layer in candidate_layers):
        return tuple(layer[0] if layer else None for layer in candidate_layers)

    states: dict[AiracFix, tuple[float, tuple[AiracFix, ...]]] = {
        fix: (fix.distance_nm, (fix,)) for fix in candidate_layers[0]
    }
    for layer in candidate_layers[1:]:
        next_states: dict[AiracFix, tuple[float, tuple[AiracFix, ...]]] = {}
        for current in layer:
            best: tuple[float, tuple[AiracFix, ...]] | None = None
            current_airways = set(memberships.get(current.identifier, ()))
            for previous, (cost, path) in states.items():
                shared = current_airways.intersection(
                    memberships.get(previous.identifier, ())
                )
                transition_penalty = 0.0 if shared else 120.0
                option = (
                    cost + current.distance_nm + transition_penalty,
                    path + (current,),
                )
                if best is None or option[0] < best[0]:
                    best = option
            if best is not None:
                next_states[current] = best
        states = next_states
    return min(states.values(), key=lambda state: state[0])[1]
