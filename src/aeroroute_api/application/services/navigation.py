from __future__ import annotations

import asyncio

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    DataQualityFlag,
    OptimizationResponse,
)
from aeroroute_api.infrastructure.navigation.airac import (
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
        fixes = await asyncio.gather(
            *(
                client.nearest_fix(point.latitude_deg, point.longitude_deg)
                for point in internal
            )
        )
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
                        "airway connectivity is not yet validated."
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
