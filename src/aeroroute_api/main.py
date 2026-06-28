from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from aeroroute_api.api.routers.airports import router as airports_router
from aeroroute_api.api.routers.explanations import router as explanations_router
from aeroroute_api.api.routers.navigation import router as navigation_router
from aeroroute_api.api.routers.optimizations import (
    router as optimizations_router,
)
from aeroroute_api.api.routers.weather import router as weather_router
from aeroroute_api.api.errors import install_error_handlers
from aeroroute_api.config import settings

app = FastAPI(title="AeroRoute MLX API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings().cors_allow_origins),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)
install_error_handlers(app)
app.include_router(airports_router)
app.include_router(explanations_router)
app.include_router(navigation_router)
app.include_router(optimizations_router)
app.include_router(weather_router)


@app.middleware("http")
async def request_id(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.headers.get(
        "X-Request-ID", str(uuid4())
    )
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "aeroroute-api"}


@app.get("/health/providers")
def provider_health() -> dict[str, str]:
    configured = settings()
    return {
        "weather": configured.weather_provider,
        "explanations": "mlx" if configured.mlx_service_url else "template",
    }
