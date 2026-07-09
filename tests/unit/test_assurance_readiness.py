from fastapi.testclient import TestClient

from aeroroute_api.main import app


def test_assurance_readiness_blocks_operational_assurance() -> None:
    response = TestClient(app).get("/api/v1/assurance-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["baseline"] == "assurance-readiness-2026-07-09"
    assert payload["operational_use_enabled"] is False
    assert payload["assurance_enabled"] is False
    assert payload["status"] == "blocked"
    assert {gate["id"] for gate in payload["gates"]} == {
        "requirements_traceability",
        "independent_validation",
        "release_data_cycle_control",
        "audit_slo_observability",
        "security_incident_response",
        "fallback_procedures",
    }
    assert {gate["status"] for gate in payload["gates"]} == {"missing"}
