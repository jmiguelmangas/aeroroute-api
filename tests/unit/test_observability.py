from fastapi.testclient import TestClient

from aeroroute_api.api.observability import (
    FixedWindowRateLimiter,
    RequestMetrics,
)
from aeroroute_api.main import app


def test_rate_limiter_resets_after_window() -> None:
    now = [100.0]
    limiter = FixedWindowRateLimiter(2, clock=lambda: now[0])

    assert limiter.allow("client")
    assert limiter.allow("client")
    assert not limiter.allow("client")
    now[0] = 160.0
    assert limiter.allow("client")


def test_metrics_use_route_templates_and_status() -> None:
    metrics = RequestMetrics()
    metrics.record("GET", "/api/v1/flight-plans/{flight_plan_id}", 200, 0.25)

    output = metrics.render()

    assert 'route="/api/v1/flight-plans/{flight_plan_id}"' in output
    assert 'status="200"' in output
    assert "0.250000" in output


def test_http_middleware_adds_security_headers_and_metrics() -> None:
    client = TestClient(app)

    response = client.get("/health", headers={"X-Request-ID": "test-request"})
    metrics = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "aeroroute_http_requests_total" in metrics.text


def test_http_middleware_rejects_large_declared_body() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/flight-plans",
        content=b"{}",
        headers={"Content-Length": "1048577"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
