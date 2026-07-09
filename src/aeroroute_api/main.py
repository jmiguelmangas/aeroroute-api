from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from aeroroute_api.api.routers.airports import router as airports_router
from aeroroute_api.api.routers.data_sources import (
    router as data_sources_router,
)
from aeroroute_api.api.routers.dispatch import router as dispatch_router
from aeroroute_api.api.routers.explanations import router as explanations_router
from aeroroute_api.api.routers.flight_plans import router as flight_plans_router
from aeroroute_api.api.routers.icao_fpl import router as icao_fpl_router
from aeroroute_api.api.routers.navigation import router as navigation_router
from aeroroute_api.api.routers.operational import (
    router as operational_router,
)
from aeroroute_api.api.routers.optimizations import (
    navigation_provider_health,
    router as optimizations_router,
)
from aeroroute_api.api.routers.weather import router as weather_router
from aeroroute_api.api.errors import install_error_handlers
from aeroroute_api.api.observability import (
    FixedWindowRateLimiter,
    RequestMetrics,
    log_request,
)
from aeroroute_api.config import settings

app = FastAPI(title="AeroRoute MLX API", version="0.11.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings().cors_allow_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
install_error_handlers(app)
_settings = settings()
_metrics = RequestMetrics()
_rate_limiter = FixedWindowRateLimiter(_settings.rate_limit_per_minute)
app.include_router(airports_router)
app.include_router(data_sources_router)
app.include_router(dispatch_router)
app.include_router(explanations_router)
app.include_router(flight_plans_router)
app.include_router(icao_fpl_router)
app.include_router(navigation_router)
app.include_router(operational_router)
app.include_router(optimizations_router)
app.include_router(weather_router)


@app.middleware("http")
async def request_id(request: Request, call_next) -> Response:
    started_at = monotonic()
    identifier = request.headers.get("X-Request-ID", str(uuid4()))
    client = request.client.host if request.client else "unknown"
    exempt = request.url.path in {"/health", "/health/providers", "/metrics"}
    content_length = int(request.headers.get("content-length", "0"))
    if content_length > _settings.max_request_bytes:
        response: Response = JSONResponse(
            status_code=413,
            content={
                "code": "request_too_large",
                "message": "Request body exceeds the configured limit.",
            },
        )
    elif not exempt and not _rate_limiter.allow(client):
        response = JSONResponse(
            status_code=429,
            content={
                "code": "rate_limit_exceeded",
                "message": "Request rate exceeds the configured limit.",
            },
        )
        response.headers["Retry-After"] = "60"
    else:
        response = await call_next(request)
    route_object = request.scope.get("route")
    route = getattr(route_object, "path", request.url.path)
    duration_s = monotonic() - started_at
    _metrics.record(request.method, route, response.status_code, duration_s)
    log_request(
        request_id=identifier,
        method=request.method,
        route=route,
        status_code=response.status_code,
        duration_s=duration_s,
    )
    response.headers["X-Request-ID"] = identifier
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aeroroute-api"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(
        content=_metrics.render(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/health/providers")
def provider_health() -> dict[str, object]:
    configured = settings()
    return {
        "weather": {
            "status": "configured",
            "provider": configured.weather_provider,
        },
        "navigation": navigation_provider_health(),
        "explanations": {
            "status": "configured",
            "provider": ("mlx" if configured.mlx_service_url else "template"),
        },
    }
