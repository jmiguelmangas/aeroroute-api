"""Configuration at the application composition boundary."""

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = (
        "postgresql+asyncpg://aeroroute:aeroroute@localhost:55432/aeroroute"
    )
    mlx_service_url: str | None = None


def settings() -> Settings:
    defaults = Settings()
    return Settings(
        database_url=os.getenv("DATABASE_URL", defaults.database_url),
        mlx_service_url=os.getenv("MLX_SERVICE_URL", defaults.mlx_service_url),
    )
