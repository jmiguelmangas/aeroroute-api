from __future__ import annotations

import asyncio

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    DataQualityFlag,
    OptimizationResponse,
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
