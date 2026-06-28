from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from aeroroute_api.infrastructure.navigation.airac import AiracAirwayPoint


@dataclass(frozen=True, slots=True)
class AirwayPathPoint:
    point: AiracAirwayPoint
    inbound_airway: str | None


def find_airway_path(
    airway_routes: tuple[tuple[AiracAirwayPoint, ...], ...],
    starts: set[str],
    goals: set[str],
) -> tuple[AirwayPathPoint, ...]:
    adjacency: dict[str, set[str]] = {}
    edge_airway: dict[tuple[str, str], str] = {}
    points: dict[str, AiracAirwayPoint] = {}
    for route in airway_routes:
        for point in route:
            points[point.identifier] = point
        for first, second in zip(route, route[1:]):
            adjacency.setdefault(first.identifier, set()).add(second.identifier)
            adjacency.setdefault(second.identifier, set()).add(first.identifier)
            edge_airway[_edge(first.identifier, second.identifier)] = (
                first.airway
            )

    queue = deque(
        (identifier, (identifier,))
        for identifier in starts
        if identifier in adjacency
    )
    visited = {identifier for identifier, _ in queue}
    path: tuple[str, ...] | None = None
    while queue:
        identifier, candidate = queue.popleft()
        if identifier in goals:
            path = candidate
            break
        for neighbor in adjacency.get(identifier, ()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append((neighbor, (*candidate, neighbor)))
    if path is None:
        return ()
    return tuple(
        AirwayPathPoint(
            point=points[identifier],
            inbound_airway=(
                None
                if index == 0
                else edge_airway[_edge(path[index - 1], identifier)]
            ),
        )
        for index, identifier in enumerate(path)
    )


def _edge(first: str, second: str) -> tuple[str, str]:
    return (first, second) if first <= second else (second, first)
