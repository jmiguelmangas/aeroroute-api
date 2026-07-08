from fastapi.testclient import TestClient

from aeroroute_api.main import app


def test_operational_readiness_defaults_to_simulator_only() -> None:
    response = TestClient(app).get("/api/v1/operational-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_mode"] == "simulator"
    assert payload["requested_mode"] == "simulator"
    assert payload["operational_use_enabled"] is False
    assert payload["status"] == "simulator_only"
    assert "not ICAO-fileable" in payload["disclaimer"]
    assert {gap["severity"] for gap in payload["gaps"]} == {"blocking"}
    assert {
        "operator_profile_missing",
        "licensed_operational_data_missing",
        "safety_case_missing",
        "requirements_traceability_missing",
        "manual_acceptance_missing",
    } <= {gap["code"] for gap in payload["gaps"]}


def test_operational_readiness_blocks_requested_operational_mode(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPS_MODE", "approved_operator_build")

    response = TestClient(app).get("/api/v1/operational-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_mode"] == "simulator"
    assert payload["requested_mode"] == "approved_operator_build"
    assert payload["operational_use_enabled"] is False
    assert payload["status"] == "blocked"
