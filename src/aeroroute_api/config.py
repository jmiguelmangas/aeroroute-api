"""Configuration at the application composition boundary."""

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = (
        "postgresql+asyncpg://aeroroute:aeroroute@localhost:55432/aeroroute"
    )
    mlx_service_url: str | None = None
    mlx_timeout_s: float = 10.0
    aircraft_performance_provider: str = "curated"
    weather_provider: str = "still_air"
    optimization_max_concurrent: int = 2
    optimization_queue_timeout_s: float = 0.25
    optimization_deadline_s: float = 15.0
    navigation_timeout_s: float = 5.0
    navigation_max_concurrent_requests: int = 8
    max_request_bytes: int = 1_048_576
    rate_limit_per_minute: int = 120
    cors_allow_origins: tuple[str, ...] = (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )


def settings() -> Settings:
    defaults = Settings()
    configured_origins = os.getenv("CORS_ALLOW_ORIGINS")
    return Settings(
        database_url=os.getenv("DATABASE_URL", defaults.database_url),
        mlx_service_url=os.getenv("MLX_SERVICE_URL", defaults.mlx_service_url),
        mlx_timeout_s=float(os.getenv("MLX_TIMEOUT_S", defaults.mlx_timeout_s)),
        aircraft_performance_provider=os.getenv(
            "AIRCRAFT_PERFORMANCE_PROVIDER",
            defaults.aircraft_performance_provider,
        ).lower(),
        weather_provider=os.getenv(
            "WEATHER_PROVIDER", defaults.weather_provider
        ).lower(),
        optimization_max_concurrent=int(
            os.getenv(
                "OPTIMIZATION_MAX_CONCURRENT",
                defaults.optimization_max_concurrent,
            )
        ),
        optimization_queue_timeout_s=float(
            os.getenv(
                "OPTIMIZATION_QUEUE_TIMEOUT_S",
                defaults.optimization_queue_timeout_s,
            )
        ),
        optimization_deadline_s=float(
            os.getenv(
                "OPTIMIZATION_DEADLINE_S",
                defaults.optimization_deadline_s,
            )
        ),
        navigation_timeout_s=float(
            os.getenv(
                "NAVIGATION_TIMEOUT_S", defaults.navigation_timeout_s
            )
        ),
        navigation_max_concurrent_requests=int(
            os.getenv(
                "NAVIGATION_MAX_CONCURRENT_REQUESTS",
                defaults.navigation_max_concurrent_requests,
            )
        ),
        max_request_bytes=int(
            os.getenv("MAX_REQUEST_BYTES", defaults.max_request_bytes)
        ),
        rate_limit_per_minute=int(
            os.getenv(
                "RATE_LIMIT_PER_MINUTE", defaults.rate_limit_per_minute
            )
        ),
        cors_allow_origins=(
            tuple(
                origin.strip()
                for origin in configured_origins.split(",")
                if origin.strip()
            )
            if configured_origins is not None
            else defaults.cors_allow_origins
        ),
    )
