"""Application use case which delegates all route physics to the optimizer."""

from aeroroute_optimizer import public as optimizer

from aeroroute_api.application.dto.optimization import (
    CandidateResponse,
    OptimizationResponse,
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
    return OptimizationResponse(
        status=result.status,
        algorithm_version=problem.algorithm_version,
        winner=_candidate_response(result.winner),
        alternatives=[
            response
            for candidate in result.alternatives
            if (response := _candidate_response(candidate)) is not None
        ],
        solver_termination_reason=result.diagnostics.termination_reason,
    )


def _candidate_response(
    candidate: optimizer.CandidateTrajectory | None,
) -> CandidateResponse | None:
    if candidate is None:
        return None
    return CandidateResponse(
        path=list(candidate.path),
        distance_m=candidate.distance_m,
        time_s=candidate.time_s,
        fuel_kg=candidate.fuel_kg,
        score=candidate.score,
    )
