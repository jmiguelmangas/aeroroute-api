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
    assert payload["evidence_contract_version"] == "1.0.0"
    assert (
        payload["evidence_baseline"]
        == "operational-readiness-evidence-2026-07-08"
    )
    assert payload["hazard_log_baseline"] == "operational-hazard-log-2026-07-08"
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


def test_operational_data_sources_fail_closed_for_ops_candidate(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPS_MODE", "ops_candidate")

    response = TestClient(app).get("/api/v1/operational-data-sources")

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_mode"] == "simulator"
    assert payload["requested_mode"] == "ops_candidate"
    assert payload["operational_use_enabled"] is False
    assert payload["status"] == "blocked"
    assert payload["data_baseline"] == "operational-data-sources-2026-07-09"
    assert "notam" in payload["blocking_domains"]
    assert "aircraft_performance" in payload["blocking_domains"]
    assert all(
        source["operational_ready"] is False for source in payload["sources"]
    )
    assert {
        "navdata",
        "weather",
        "notam",
        "airspace_restrictions",
        "airport_status",
        "terrain_obstacle",
        "aircraft_performance",
        "filing",
    } == {source["domain"] for source in payload["sources"]}
