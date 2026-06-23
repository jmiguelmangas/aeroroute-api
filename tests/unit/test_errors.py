from fastapi.testclient import TestClient

from aeroroute_api.main import app


def test_validation_errors_use_stable_public_envelope() -> None:
    response = TestClient(app).post("/api/v1/optimizations", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "Request validation failed."
