from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    DataQualityFlag,
    OptimizationResponse,
    TerminalSelection,
    WaypointDetail,
)
from aeroroute_api.application.services.terminal_options import (
    procedures_for_runway,
    runway_options,
)
from aeroroute_api.application.services.airway_graph import (
    AirwayPathPoint,
    find_airway_path,
)
from aeroroute_api.infrastructure.navigation.airac import (
    AiracFix,
    AiracNavigationClient,
    AiracProviderError,
    AiracProcedure,
)


@dataclass(frozen=True, slots=True)
class _NavigationPathPoint:
    identifier: str
    latitude_deg: float
    longitude_deg: float
    inbound_via: str
    cycle: str | None
    procedure_type: str | None = None
    runway: str | None = None


async def enrich_winner_with_airac(
    response: OptimizationResponse,
    client: AiracNavigationClient,
) -> OptimizationResponse:
    winner = response.winner
    if winner is None or len(winner.waypoints) < 2:
        return response
    internal = winner.waypoints[1:-1]
    sid_procedures: tuple[AiracProcedure, ...] = ()
    star_procedures: tuple[AiracProcedure, ...] = ()
    departure_runway: str | None = None
    arrival_runway: str | None = None
    rationale: list[str] = []
    option_cycles: set[str] = set()
    if response.request is not None:
        departure_runway = response.request.departure_runway
        arrival_runway = response.request.arrival_runway
        if departure_runway is None:
            try:
                options = await runway_options(
                    client, response.request.origin_icao, "SID"
                )
                departure_runway = options.suggested_runway
                rationale.extend(options.recommendation_basis)
                if options.airac_cycle:
                    option_cycles.add(options.airac_cycle)
            except AiracProviderError:
                pass
        if arrival_runway is None:
            try:
                options = await runway_options(
                    client, response.request.destination_icao, "STAR"
                )
                arrival_runway = options.suggested_runway
                rationale.extend(options.recommendation_basis)
                if options.airac_cycle:
                    option_cycles.add(options.airac_cycle)
            except AiracProviderError:
                pass
        try:
            sid_procedures = procedures_for_runway(
                await client.procedures(response.request.origin_icao, "SID"),
                departure_runway,
            )
        except AiracProviderError:
            pass
        try:
            star_procedures = procedures_for_runway(
                await client.procedures(
                    response.request.destination_icao, "STAR"
                ),
                arrival_runway,
            )
        except AiracProviderError:
            pass
    terminal_selection = TerminalSelection(
        departure_runway=departure_runway,
        departure_runway_suggested=bool(
            response.request and response.request.departure_runway is None
        ),
        arrival_runway=arrival_runway,
        arrival_runway_suggested=bool(
            response.request and response.request.arrival_runway is None
        ),
        airac_cycle=(
            ", ".join(sorted(option_cycles)) if option_cycles else None
        ),
        rationale=list(dict.fromkeys(rationale)),
    )
    try:
        airway_path = await _discover_corridor_path(
            winner, client, sid_procedures, star_procedures
        )
    except AiracProviderError:
        airway_path = ()
    if airway_path:
        sid = _matching_sid(sid_procedures, airway_path)
        star = _matching_star(star_procedures, airway_path)
        return _response_with_connected_path(
            response,
            airway_path,
            sid,
            star,
            departure_runway,
            arrival_runway,
            rationale,
        )
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
                "terminal_selection": terminal_selection,
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
                ],
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
    sid = _nearest_terminal_procedure(sid_procedures, points[1], use_exit=True)
    star = _nearest_terminal_procedure(
        star_procedures, points[-2], use_exit=False
    )
    if sid or star:
        points = _attach_degraded_terminal_procedures(winner, points, sid, star)
        terminal_selection = terminal_selection.model_copy(
            update={
                "sid_identifier": sid.identifier if sid else None,
                "star_identifier": star.identifier if star else None,
                "rationale": [
                    *terminal_selection.rationale,
                    "Runway-compatible terminal procedures are retained; unconnected terminal-to-enroute joins are explicit DCT legs.",
                ],
            }
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
        if previous.procedure_type or current.procedure_type:
            continue
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
            "terminal_selection": terminal_selection,
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
                DataQualityFlag(
                    code="TERMINAL_ROUTE_DISCONNECTED",
                    severity="warning",
                    message=(
                        "Runway-compatible SID/STAR are retained where available, "
                        "but could not both be connected through one bounded AIRAC "
                        "graph; terminal-to-enroute joins remain explicit DCT legs."
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
    sid_procedures: tuple[AiracProcedure, ...] = (),
    star_procedures: tuple[AiracProcedure, ...] = (),
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
    sid_exits = {
        procedure.points[-1].identifier for procedure in sid_procedures
    }
    star_entries = {
        procedure.points[0].identifier for procedure in star_procedures
    }
    identifiers.update(sid_exits)
    identifiers.update(star_entries)
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
    airway_identifiers.update(
        airway
        for identifier in sid_exits
        for airway in memberships.get(identifier, ())
    )
    airway_identifiers.update(
        airway
        for identifier in star_entries
        for airway in memberships.get(identifier, ())
    )
    routes = await asyncio.gather(
        *(client.airway_points(identifier) for identifier in airway_identifiers)
    )
    connected_sid_exits = {
        identifier for identifier in sid_exits if memberships.get(identifier)
    }
    connected_star_entries = {
        identifier for identifier in star_entries if memberships.get(identifier)
    }
    return find_airway_path(
        tuple(routes),
        connected_sid_exits or {fix.identifier for fix in nonempty_layers[0]},
        connected_star_entries
        or {fix.identifier for fix in nonempty_layers[-1]},
    )


def _response_with_connected_path(
    response: OptimizationResponse,
    airway_path: tuple[AirwayPathPoint, ...],
    sid: AiracProcedure | None,
    star: AiracProcedure | None,
    departure_runway: str | None,
    arrival_runway: str | None,
    rationale: list[str],
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
    navigation_path = _compose_navigation_path(airway_path, sid, star)
    coordinates = [
        (winner.waypoints[0].latitude_deg, winner.waypoints[0].longitude_deg),
        *((item.latitude_deg, item.longitude_deg) for item in navigation_path),
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
    for index, item in enumerate(navigation_path, start=1):
        cumulative += segment_distances[index - 1]
        fraction = cumulative / total_distance if total_distance else 0.0
        if item.cycle:
            cycles.add(item.cycle)
        nearest_solver = winner.waypoints[
            min(
                round(fraction * (len(winner.waypoints) - 1)),
                len(winner.waypoints) - 1,
            )
        ]
        points.append(
            WaypointDetail(
                node_id=f"AIRAC:{item.identifier}:{index}",
                display_name=item.identifier,
                kind="navigation_fix",
                latitude_deg=item.latitude_deg,
                longitude_deg=item.longitude_deg,
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
                airac_cycle=item.cycle,
                inbound_via=item.inbound_via,
                airway_validated=True,
                procedure_type=item.procedure_type,
                procedure_identifier=(
                    item.inbound_via if item.procedure_type else None
                ),
                runway=item.runway,
            )
        )
    points.append(
        winner.waypoints[-1].model_copy(
            update={
                "kind": "airport",
                "display_name": destination_name,
                "inbound_via": star.identifier if star else "DCT",
                "airway_validated": bool(star),
            }
        )
    )
    enriched = winner.model_copy(update={"waypoints": points})
    cycle_text = ", ".join(sorted(cycles)) if cycles else "current"
    return response.model_copy(
        update={
            "winner": CandidateResponse.model_validate(enriched),
            "terminal_selection": TerminalSelection(
                departure_runway=departure_runway,
                departure_runway_suggested=bool(
                    response.request
                    and response.request.departure_runway is None
                ),
                sid_identifier=sid.identifier if sid else None,
                arrival_runway=arrival_runway,
                arrival_runway_suggested=bool(
                    response.request and response.request.arrival_runway is None
                ),
                star_identifier=star.identifier if star else None,
                airac_cycle=cycle_text,
                rationale=list(dict.fromkeys(rationale)),
            ),
            "data_quality": [
                *response.data_quality,
                DataQualityFlag(
                    code="NAVIGATION_AIRWAY_GRAPH",
                    severity="info",
                    message=(
                        f"AIRAC.net cycle {cycle_text} produced a connected "
                        f"{len(navigation_path)}-fix path; "
                        + (
                            f"SID {sid.identifier} and STAR {star.identifier} "
                            "are connected to the airway graph."
                            if sid and star
                            else "one or both airport joins remain DCT."
                        )
                    ),
                ),
            ],
        }
    )


def _matching_sid(
    procedures: tuple[AiracProcedure, ...],
    airway_path: tuple[AirwayPathPoint, ...],
) -> AiracProcedure | None:
    positions = {
        item.point.identifier: index for index, item in enumerate(airway_path)
    }
    matches = [
        procedure
        for procedure in procedures
        if procedure.points[-1].identifier in positions
    ]
    if not matches:
        return None
    return min(
        matches,
        key=lambda procedure: (
            positions[procedure.points[-1].identifier],
            len(procedure.points),
        ),
    )


def _matching_star(
    procedures: tuple[AiracProcedure, ...],
    airway_path: tuple[AirwayPathPoint, ...],
) -> AiracProcedure | None:
    positions = {
        item.point.identifier: index for index, item in enumerate(airway_path)
    }
    matches = [
        procedure
        for procedure in procedures
        if procedure.points[0].identifier in positions
    ]
    if not matches:
        return None
    return max(
        matches,
        key=lambda procedure: (
            positions[procedure.points[0].identifier],
            -len(procedure.points),
        ),
    )


def _nearest_terminal_procedure(
    procedures: tuple[AiracProcedure, ...],
    target: WaypointDetail,
    *,
    use_exit: bool,
) -> AiracProcedure | None:
    if not procedures:
        return None
    return min(
        procedures,
        key=lambda procedure: (
            _distance_m(
                (
                    procedure.points[-1 if use_exit else 0].latitude_deg,
                    procedure.points[-1 if use_exit else 0].longitude_deg,
                ),
                (target.latitude_deg, target.longitude_deg),
            ),
            procedure.identifier,
        ),
    )


def _attach_degraded_terminal_procedures(
    winner: CandidateResponse,
    route_points: list[WaypointDetail],
    sid: AiracProcedure | None,
    star: AiracProcedure | None,
) -> list[WaypointDetail]:
    internal = list(route_points[1:-1])
    if internal and sid:
        internal[0] = internal[0].model_copy(
            update={"inbound_via": "DCT", "airway_validated": False}
        )
    departure = _procedure_waypoints(sid, "SID") if sid else []
    arrival = _procedure_waypoints(star, "STAR") if star else []
    if arrival:
        arrival[0] = arrival[0].model_copy(
            update={"inbound_via": "DCT", "airway_validated": False}
        )
    combined = [
        route_points[0],
        *departure,
        *internal,
        *arrival,
        route_points[-1],
    ]
    deduplicated = [combined[0]]
    for point in combined[1:]:
        previous = deduplicated[-1]
        if (
            point.display_name == previous.display_name
            and point.latitude_deg == previous.latitude_deg
            and point.longitude_deg == previous.longitude_deg
        ):
            continue
        deduplicated.append(point)
    coordinates = [
        (point.latitude_deg, point.longitude_deg) for point in deduplicated
    ]
    distances = [
        _distance_m(first, second)
        for first, second in zip(coordinates, coordinates[1:])
    ]
    total = sum(distances)
    cumulative = 0.0
    output: list[WaypointDetail] = []
    for index, point in enumerate(deduplicated):
        if index:
            cumulative += distances[index - 1]
        fraction = cumulative / total if total else 0.0
        nearest_solver = winner.waypoints[
            min(
                round(fraction * (len(winner.waypoints) - 1)),
                len(winner.waypoints) - 1,
            )
        ]
        output.append(
            point.model_copy(
                update={
                    "elapsed_time_s": winner.time_s * fraction,
                    "cumulative_distance_m": winner.distance_m * fraction,
                    "cumulative_fuel_kg": winner.fuel_kg * fraction,
                    "estimated_mass_kg": (
                        winner.waypoints[0].estimated_mass_kg
                        + (
                            winner.waypoints[-1].estimated_mass_kg
                            - winner.waypoints[0].estimated_mass_kg
                        )
                        * fraction
                    ),
                    "wind_component_kt": nearest_solver.wind_component_kt,
                }
            )
        )
    if star:
        output[-1] = output[-1].model_copy(
            update={
                "inbound_via": star.identifier,
                "airway_validated": True,
            }
        )
    return output


def _procedure_waypoints(
    procedure: AiracProcedure, procedure_type: str
) -> list[WaypointDetail]:
    return [
        WaypointDetail(
            node_id=f"AIRAC:{procedure_type}:{procedure.identifier}:{index}",
            display_name=point.identifier,
            kind="navigation_fix",
            latitude_deg=point.latitude_deg,
            longitude_deg=point.longitude_deg,
            flight_level=0,
            elapsed_time_s=0,
            cumulative_distance_m=0,
            cumulative_fuel_kg=0,
            estimated_mass_kg=0,
            navigation_source="airac.net",
            airac_cycle=procedure.cycle,
            inbound_via=procedure.identifier,
            airway_validated=True,
            procedure_type=procedure_type,
            procedure_identifier=procedure.identifier,
            runway=procedure.runway,
        )
        for index, point in enumerate(procedure.points, start=1)
    ]


def _compose_navigation_path(
    airway_path: tuple[AirwayPathPoint, ...],
    sid: AiracProcedure | None,
    star: AiracProcedure | None,
) -> tuple[_NavigationPathPoint, ...]:
    airway_start = 0
    departure_points: tuple[_NavigationPathPoint, ...] = ()
    if sid is not None:
        exit_identifier = sid.points[-1].identifier
        airway_start = (
            next(
                index
                for index, item in enumerate(airway_path)
                if item.point.identifier == exit_identifier
            )
            + 1
        )
        departure_points = tuple(
            _NavigationPathPoint(
                point.identifier,
                point.latitude_deg,
                point.longitude_deg,
                sid.identifier,
                sid.cycle,
                "SID",
                sid.runway,
            )
            for point in sid.points
        )
    airway_end = len(airway_path)
    arrival_points: tuple[_NavigationPathPoint, ...] = ()
    if star is not None:
        entry_identifier = star.points[0].identifier
        airway_end = next(
            index
            for index, item in enumerate(airway_path)
            if item.point.identifier == entry_identifier
        )
        arrival_points = tuple(
            _NavigationPathPoint(
                point.identifier,
                point.latitude_deg,
                point.longitude_deg,
                star.identifier,
                star.cycle,
                "STAR",
                star.runway,
            )
            for point in star.points
        )
    enroute_points = tuple(
        _NavigationPathPoint(
            item.point.identifier,
            item.point.latitude_deg,
            item.point.longitude_deg,
            item.inbound_airway or "DCT",
            item.point.cycle,
        )
        for item in airway_path[airway_start:airway_end]
    )
    return (*departure_points, *enroute_points, *arrival_points)


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
