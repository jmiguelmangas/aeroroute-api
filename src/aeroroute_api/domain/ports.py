"""Ports for persistence, weather, performance, and explanation adapters."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class WindSampleRequest:
    latitude_deg: float
    longitude_deg: float
    pressure_hpa: int
    at_utc: datetime


@dataclass(frozen=True, slots=True)
class WindSample:
    east_mps: float
    north_mps: float
    geopotential_height_m: float
    valid_at_utc: datetime
    source: str
    stale: bool = False
    fetched_at_utc: datetime | None = None
    model: str | None = None


class WeatherPort(Protocol):
    async def winds_for(
        self, requests: Sequence[WindSampleRequest]
    ) -> tuple[WindSample, ...]: ...
