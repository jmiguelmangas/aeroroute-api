from fastapi.testclient import TestClient

from aeroroute_api.main import app


def test_health() -> None:
    response = TestClient(app).get(
        "/health", headers={"X-Request-ID": "test-id"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"] == "test-id"


def test_local_frontend_cors_preflight_is_allowed() -> None:
    response = TestClient(app).options(
        "/api/v1/optimizations",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://127.0.0.1:5173"
    )


def test_provider_health_reports_deterministic_fallback_when_mlx_is_unconfigured() -> (
    None
):
    response = TestClient(app).get("/health/providers")

    assert response.status_code == 200
    explanations = response.json()["explanations"]
    assert explanations["status"] == "configured"
    assert explanations["provider"] == "template"
    assert "fallback_used" in explanations
    assert "mlx_used" in explanations
    weather = response.json()["weather"]
    assert weather["status"] == "configured"
    assert weather["provider"] == "still_air"
    assert "cache_hits" in weather
    assert "cache_entries" in weather
    assert response.json()["navigation"]["source"] == "airac.net"
