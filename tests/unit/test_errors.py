from fastapi import FastAPI
from fastapi.testclient import TestClient

from aeroroute_api.api.errors import PublicAPIError, install_error_handlers
from aeroroute_api.main import app


def test_validation_errors_use_stable_public_envelope() -> None:
    response = TestClient(app).post("/api/v1/optimizations", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert response.json()["message"] == "Request validation failed."


def test_service_errors_use_stable_public_envelope() -> None:
    test_app = FastAPI()
    install_error_handlers(test_app)

    @test_app.get("/failure")
    async def failure() -> None:
        raise PublicAPIError(503, "provider_unavailable", "Try again later.")

    response = TestClient(test_app).get("/failure")

    assert response.status_code == 503
    assert response.json() == {
        "code": "provider_unavailable",
        "message": "Try again later.",
    }
