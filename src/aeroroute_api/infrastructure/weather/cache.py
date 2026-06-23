"""Bounded in-process cache with explicit stale-data fallback."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from time import monotonic

from aeroroute_api.domain.ports import (
    WeatherPort,
    WindSample,
    WindSampleRequest,
)


@dataclass(frozen=True, slots=True)
class _CachedSample:
    sample: WindSample
    cached_at_s: float


class CachedWeatherPort:
    def __init__(
        self,
        delegate: WeatherPort,
        fresh_ttl_s: float = 300.0,
        stale_ttl_s: float = 3_600.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if not 0 < fresh_ttl_s <= stale_ttl_s:
            raise ValueError("cache TTLs must be positive and ordered")
        self._delegate = delegate
        self._fresh_ttl_s = fresh_ttl_s
        self._stale_ttl_s = stale_ttl_s
        self._clock = clock
        self._cache: dict[WindSampleRequest, _CachedSample] = {}

    async def winds_for(
        self, requests: Sequence[WindSampleRequest]
    ) -> tuple[WindSample, ...]:
        now = self._clock()
        fresh = [self._cache.get(request) for request in requests]
        if all(
            item is not None and now - item.cached_at_s <= self._fresh_ttl_s
            for item in fresh
        ):
            return tuple(item.sample for item in fresh if item is not None)
        try:
            samples = await self._delegate.winds_for(requests)
        except Exception:
            stale = [self._cache.get(request) for request in requests]
            if all(
                item is not None and now - item.cached_at_s <= self._stale_ttl_s
                for item in stale
            ):
                return tuple(
                    replace(item.sample, stale=True)
                    for item in stale
                    if item is not None
                )
            raise
        if len(samples) != len(requests):
            raise ValueError(
                "weather provider returned samples in a different order"
            )
        for request, sample in zip(requests, samples, strict=True):
            self._cache[request] = _CachedSample(sample, now)
        return samples
