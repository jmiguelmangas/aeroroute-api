"""Configuration at the application composition boundary."""

from dataclasses import dataclass
import os


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str = (
        "postgresql+asyncpg://aeroroute:aeroroute@localhost:55432/aeroroute"
    )


def settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings().database_url)
    )
