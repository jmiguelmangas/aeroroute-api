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


def test_rate_limiter_evicts_expired_windows_for_other_clients() -> None:
    # Each distinct client IP that has ever made a request must not live
    # forever in `_windows` -- once a client's 60s window has elapsed, its
    # entry should be reaped by subsequent calls from *other* clients so
    # memory doesn't grow unboundedly with the number of distinct clients
    # ever seen over the process lifetime.
    now = [0.0]
    limiter = FixedWindowRateLimiter(5, clock=lambda: now[0])

    for index in range(50):
        assert limiter.allow(f"client-{index}")
        now[0] += 61.0

    assert len(limiter._windows) == 1


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


def test_metrics_render_exposes_optimization_duration_by_outcome() -> None:
    metrics = RequestMetrics()
    metrics.record_optimization_duration("success", 1.5)
    metrics.record_optimization_duration("success", 0.5)
    metrics.record_optimization_duration("deadline_exceeded", 3.0)

    output = metrics.render()

    assert "aeroroute_optimization_duration_seconds_sum" in output
    assert "aeroroute_optimization_duration_seconds_count" in output
    assert 'outcome="success"' in output
    assert (
        'aeroroute_optimization_duration_seconds_sum{outcome="success"} 2.000000'
        in (output)
    )
    assert (
        'aeroroute_optimization_duration_seconds_count{outcome="success"} 2'
        in output
    )


def test_http_middleware_rejects_large_declared_body() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/flight-plans",
        content=b"{}",
        headers={"Content-Length": "1048577"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "request_too_large"
