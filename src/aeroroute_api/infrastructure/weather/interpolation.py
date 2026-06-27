"""Interpolation of normalized wind vectors across time and geopotential height."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime

from aeroroute_api.domain.ports import WindSample


@dataclass(frozen=True, slots=True)
class HeightWindSample:
    geopotential_height_m: float
    sample: WindSample


def interpolate_time(
    earlier: WindSample, later: WindSample, target_utc: datetime
) -> WindSample:
    """Linearly interpolate vectors, never meteorological direction angles."""
    start = earlier.valid_at_utc.timestamp()
    end = later.valid_at_utc.timestamp()
    target = target_utc.timestamp()
    if end <= start or not start <= target <= end:
        raise ValueError("target time must be between distinct weather samples")
    ratio = (target - start) / (end - start)
    return WindSample(
        east_mps=_lerp(earlier.east_mps, later.east_mps, ratio),
        north_mps=_lerp(earlier.north_mps, later.north_mps, ratio),
        geopotential_height_m=_lerp(
            earlier.geopotential_height_m, later.geopotential_height_m, ratio
        ),
        valid_at_utc=target_utc,
        source=f"interpolated:{earlier.source}",
        stale=earlier.stale or later.stale,
        fetched_at_utc=earlier.fetched_at_utc,
        model=earlier.model,
    )


def interpolate_height(
    lower: HeightWindSample, upper: HeightWindSample, target_height_m: float
) -> WindSample:
    """Interpolate wind vectors between pressure levels using actual height."""
    start = lower.geopotential_height_m
    end = upper.geopotential_height_m
    if not all(math.isfinite(value) for value in (start, end, target_height_m)):
        raise ValueError("interpolation heights must be finite")
    if end <= start or not start <= target_height_m <= end:
        raise ValueError(
            "target height must be between distinct pressure levels"
        )
    ratio = (target_height_m - start) / (end - start)
    return WindSample(
        east_mps=_lerp(lower.sample.east_mps, upper.sample.east_mps, ratio),
        north_mps=_lerp(lower.sample.north_mps, upper.sample.north_mps, ratio),
        geopotential_height_m=target_height_m,
        valid_at_utc=lower.sample.valid_at_utc,
        source=f"interpolated:{lower.sample.source}",
        stale=lower.sample.stale or upper.sample.stale,
        fetched_at_utc=lower.sample.fetched_at_utc,
        model=lower.sample.model,
    )


def _lerp(start: float, end: float, ratio: float) -> float:
    return start + (end - start) * ratio
