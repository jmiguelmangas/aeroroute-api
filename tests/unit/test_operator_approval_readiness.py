from fastapi.testclient import TestClient

from aeroroute_api.main import app


def test_operator_approval_readiness_blocks_rollout() -> None:
    response = TestClient(app).get("/api/v1/operator-approval-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"] == "operator-approval-readiness-2026-07-09"
    assert payload["operational_use_enabled"] is False
    assert payload["operator_approval_enabled"] is False
    assert payload["rollout_state"] == "blocked"
    assert payload["ops_mode"] == "simulator"
    assert {gate["status"] for gate in payload["gates"]} == {"missing"}
    assert {gate["id"] for gate in payload["gates"]} == {
        "operator_acceptance",
        "regulator_submission_pack",
        "manuals_training",
        "parallel_run_campaign",
        "go_no_go_decision",
    }
