from fastapi.testclient import TestClient

from aeroroute_api.main import app


def test_dispatch_readiness_blocks_operational_release() -> None:
    response = TestClient(app).get("/api/v1/dispatch-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"] == "dispatch-readiness-2026-07-09"
    assert payload["operational_use_enabled"] is False
    assert payload["dispatch_release_enabled"] is False
    assert payload["status"] == "blocked"
    assert {gate["id"] for gate in payload["gates"]} == {
        "approved_performance_data",
        "fuel_policy_acceptance",
        "runway_weight_balance_limits",
        "minima_alternate_suitability",
        "dispatcher_signoff",
    }
    assert {gate["status"] for gate in payload["gates"]} == {"missing"}
