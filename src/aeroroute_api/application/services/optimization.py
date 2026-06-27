"""Application use case which delegates all route physics to the optimizer."""

from aeroroute_optimizer import public as optimizer

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    DataQualityFlag,
    FuelBreakdown,
    FuelIterationSummary,
    GeoJsonGeometry,
    ObjectiveBreakdown,
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
    performance_provider: str = "curated",
) -> OptimizationResponse:
    performance = aircraft_performance(performance_provider)
    optimization = optimizer.optimize_still_air_with_mass_iteration(
        optimizer.GeoPoint(origin_latitude_deg, origin_longitude_deg),
        optimizer.GeoPoint(destination_latitude_deg, destination_longitude_deg),
        performance,
        aircraft_type,
        (10_000.0, 11_000.0),
        profile=optimizer.OptimizationProfile(profile),
    )
    problem = optimization.problem
    result = optimization.solver_result
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
        objective_breakdown=optimizer.score_breakdown(
            problem,
            problem.baseline_distance_m,
            problem.baseline_time_s,
            problem.baseline_fuel_kg,
        ),
    )
    quality_flags = [
        DataQualityFlag(
            code="WEATHER_STILL_AIR",
            severity="warning",
            message="Live weather is not included in this result.",
        ),
        DataQualityFlag(
            code=f"PERFORMANCE_{performance.provenance.provider.upper()}",
            severity="info",
            message=(
                "Aircraft performance uses "
                f"{performance.provenance.provider} "
                f"{performance.provenance.version}."
            ),
        ),
    ]
    if optimization.fuel_iteration.warning_code:
        quality_flags.append(
            DataQualityFlag(
                code=optimization.fuel_iteration.warning_code.upper(),
                severity="warning",
                message="The bounded mass/fuel iteration did not converge.",
            )
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
            "Still-air deterministic route model",
            f"Aircraft performance provider: "
            f"{performance.provenance.provider} "
            f"{performance.provenance.version}",
            "Initial mass includes payload, modeled trip fuel, and a fixed "
            "3,000 kg reserve used only as a mass assumption",
            "Cruise levels restricted to FL328 and FL361",
            "Synthetic corridor with 100 km lateral offsets",
            "Climb and descent use fixed estimates and are not optimized",
        ],
        data_quality=quality_flags,
        fuel_iteration=FuelIterationSummary(
            initial_mass_kg=optimization.fuel_iteration.initial_mass_kg,
            trip_fuel_kg=optimization.fuel_iteration.trip_fuel_kg,
            iterations=optimization.fuel_iteration.iterations,
            converged=optimization.fuel_iteration.converged,
            warning_code=optimization.fuel_iteration.warning_code,
        ),
    )


def aircraft_performance(
    provider: str,
) -> optimizer.AircraftPerformancePort:
    normalized = provider.lower()
    if normalized == "curated":
        return optimizer.CuratedPerformance()
    if normalized == "openap":
        return optimizer.OpenAPPerformance()
    raise ValueError(f"unsupported aircraft performance provider: {provider}")


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
                estimated_mass_kg=(problem.initial_mass_kg or 65_000.0)
                - cumulative_fuel_kg,
            )
        )
    objective = candidate.objective_breakdown
    return CandidateResponse(
        path=list(candidate.path),
        geometry=geometry,
        distance_m=candidate.distance_m,
        time_s=candidate.time_s,
        fuel_kg=candidate.fuel_kg,
        score=candidate.score,
        display_geojson=_display_geojson(geometry),
        waypoints=waypoints,
        fuel_breakdown=FuelBreakdown(
            modeled_trip_fuel_kg=candidate.fuel_kg,
            cruise_fuel_kg=max(
                0.0, candidate.fuel_kg - problem.fixed_phase_fuel_kg
            ),
            fixed_climb_descent_fuel_kg=problem.fixed_phase_fuel_kg,
            mass_assumption_fuel_kg=problem.mass_assumption_fuel_kg,
        ),
        objective_breakdown=(
            ObjectiveBreakdown(
                fuel_delta=objective.fuel_delta,
                time_delta=objective.time_delta,
                route_extension=objective.route_extension,
                fuel_weight=objective.fuel_weight,
                time_weight=objective.time_weight,
                extension_weight=objective.extension_weight,
                fuel_component=objective.fuel_component,
                time_component=objective.time_component,
                extension_component=objective.extension_component,
                total_score=objective.total_score,
            )
            if objective is not None
            else None
        ),
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
