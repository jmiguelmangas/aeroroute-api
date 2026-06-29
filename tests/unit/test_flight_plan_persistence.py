from aeroroute_api.application.dto.flight_plan import FlightPlanRequest
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.db.flight_plans import (
    DISCLAIMER,
    coded_route,
    flight_plan_request_hash,
)


def request(**updates: object) -> FlightPlanRequest:
    values: dict[str, object] = {
        "origin_icao": "LEMD",
        "destination_icao": "KJFK",
        "aircraft_type": "B77W",
        "profile": "minimum_fuel",
        "payload_mass_kg": 42_000,
        "callsign": "ARX101",
    }
    values.update(updates)
    return FlightPlanRequest.model_validate(values)


def test_flight_plan_hash_is_canonical_and_includes_callsign() -> None:
    assert flight_plan_request_hash(request()) == flight_plan_request_hash(
        request()
    )
    assert flight_plan_request_hash(request()) != flight_plan_request_hash(
        request(callsign="ARX102")
    )


def test_coded_route_retains_explicit_solver_nodes() -> None:
    plan_request = request()
    optimization = optimize_still_air(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        "B77W",
        "minimum_fuel",
    )

    route = coded_route(plan_request, optimization)

    assert route.startswith("LEMD SYN-02")
    assert route.endswith("KJFK")
    assert "DCT" not in route


def test_mandatory_disclaimer_rejects_operational_claims() -> None:
    assert "not an ICAO-fileable flight plan" in DISCLAIMER
    assert "not suitable for operational" in DISCLAIMER
