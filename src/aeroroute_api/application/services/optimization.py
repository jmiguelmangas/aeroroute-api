"""Application use case which delegates all route physics to the optimizer."""

from aeroroute_optimizer import public as optimizer

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    DataQualityFlag,
    GeoJsonGeometry,
    OptimizationResponse,
    RoutePoint,
    WaypointDetail,
)


def optimize_still_air(
    origin_latitude_deg: float,
    origin_longitude_deg: float,
    destination_latitude_deg: float,
    destination_longitude_deg: float,
    aircraft_type: str,
    profile: str,
) -> OptimizationResponse:
    problem = optimizer.build_still_air_lattice(
        optimizer.GeoPoint(origin_latitude_deg, origin_longitude_deg),
        optimizer.GeoPoint(destination_latitude_deg, destination_longitude_deg),
        optimizer.CuratedPerformance(),
        aircraft_type,
        65_000.0,
        (10_000.0, 11_000.0),
        profile=optimizer.OptimizationProfile(profile),
    )
    result = optimizer.LayeredLabelSettingSolver().solve(
        problem, optimizer.SolverSettings()
    )
    baseline_nodes = tuple(
        node.identifier
        for node in sorted(problem.nodes, key=lambda item: item.layer)
        if node.offset_m == 0.0 and node.altitude_m == 10_000.0
    )
    baseline = optimizer.CandidateTrajectory(
        path=baseline_nodes,
        distance_m=problem.baseline_distance_m,
        time_s=problem.baseline_time_s,
        fuel_kg=problem.baseline_fuel_kg,
        score=0.0,
    )
    return OptimizationResponse(
        status=result.status,
        algorithm_version=problem.algorithm_version,
        winner=_candidate_response(problem, result.winner),
        alternatives=[
            response
            for candidate in result.alternatives
            if (response := _candidate_response(problem, candidate)) is not None
        ],
        solver_termination_reason=result.diagnostics.termination_reason,
        baseline=_candidate_response(problem, baseline),
        assumptions=[
            "Still-air deterministic performance model",
            "Representative initial mass of 65,000 kg",
            "Cruise levels restricted to FL328 and FL361",
            "Synthetic corridor with 100 km lateral offsets",
        ],
        data_quality=[
            DataQualityFlag(
                code="WEATHER_STILL_AIR",
                severity="warning",
                message="Live weather is not included in this result.",
            ),
            DataQualityFlag(
                code="PERFORMANCE_CURATED",
                severity="info",
                message="Aircraft performance uses a curated reference model.",
            ),
        ],
    )


def _candidate_response(
    problem: optimizer.OptimizationProblem,
    candidate: optimizer.CandidateTrajectory | None,
) -> CandidateResponse | None:
    if candidate is None:
        return None
    nodes = problem.nodes_by_id
    geometry = [
        RoutePoint(
            latitude_deg=nodes[node_id].point.latitude_deg,
            longitude_deg=nodes[node_id].point.longitude_deg,
        )
        for node_id in candidate.path
    ]
    transitions = {
        (transition.source_id, transition.target_id): transition
        for transition in problem.transitions
    }
    elapsed_time_s = 0.0
    cumulative_distance_m = 0.0
    cumulative_fuel_kg = 0.0
    waypoints: list[WaypointDetail] = []
    for index, node_id in enumerate(candidate.path):
        if index:
            transition = transitions[(candidate.path[index - 1], node_id)]
            elapsed_time_s += transition.time_s
            cumulative_distance_m += transition.distance_m
            cumulative_fuel_kg += transition.fuel_kg
        node = nodes[node_id]
        waypoints.append(
            WaypointDetail(
                node_id=node_id,
                latitude_deg=node.point.latitude_deg,
                longitude_deg=node.point.longitude_deg,
                flight_level=round(node.altitude_m / 30.48),
                elapsed_time_s=elapsed_time_s,
                cumulative_distance_m=cumulative_distance_m,
                cumulative_fuel_kg=cumulative_fuel_kg,
                estimated_mass_kg=65_000.0 - cumulative_fuel_kg,
            )
        )
    return CandidateResponse(
        path=list(candidate.path),
        geometry=geometry,
        distance_m=candidate.distance_m,
        time_s=candidate.time_s,
        fuel_kg=candidate.fuel_kg,
        score=candidate.score,
        display_geojson=_display_geojson(geometry),
        waypoints=waypoints,
    )


def _display_geojson(points: list[RoutePoint]) -> GeoJsonGeometry:
    if len(points) < 2:
        return GeoJsonGeometry(
            type="LineString",
            coordinates=[
                [point.longitude_deg, point.latitude_deg] for point in points
            ],
        )
    segments: list[list[list[float]]] = [
        [[points[0].longitude_deg, points[0].latitude_deg]]
    ]
    previous = points[0]
    for point in points[1:]:
        delta = point.longitude_deg - previous.longitude_deg
        if abs(delta) <= 180.0:
            segments[-1].append([point.longitude_deg, point.latitude_deg])
            previous = point
            continue
        adjusted_longitude = point.longitude_deg + (
            -360.0 if delta > 0 else 360.0
        )
        boundary = -180.0 if delta > 0 else 180.0
        ratio = (boundary - previous.longitude_deg) / (
            adjusted_longitude - previous.longitude_deg
        )
        crossing_latitude = previous.latitude_deg + ratio * (
            point.latitude_deg - previous.latitude_deg
        )
        segments[-1].append([boundary, crossing_latitude])
        segments.append(
            [
                [-boundary, crossing_latitude],
                [point.longitude_deg, point.latitude_deg],
            ]
        )
        previous = point
    if len(segments) == 1:
        return GeoJsonGeometry(type="LineString", coordinates=segments[0])
    return GeoJsonGeometry(type="MultiLineString", coordinates=segments)
