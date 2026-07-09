"""Bounded in-process cache with explicit stale-data fallback."""

from __future__ import annotations

from collections import OrderedDict
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
        # Distinct WindSampleRequest keys vary by lat/lon/pressure-level/
        # forecast-hour, so diversity grows with route/profile variety
        # rather than with request volume. 2_000 entries is generously
        # large relative to realistic in-flight route diversity (a single
        # optimization run samples a handful of waypoints x pressure
        # levels) while still bounding memory for a long-lived process --
        # matches the FlightPlanSnapshotCache LRU pattern in
        # infrastructure/db/flight_plans.py.
        max_entries: int = 2_000,
    ) -> None:
        if not 0 < fresh_ttl_s <= stale_ttl_s:
            raise ValueError("cache TTLs must be positive and ordered")
        self._delegate = delegate
        self._fresh_ttl_s = fresh_ttl_s
        self._stale_ttl_s = stale_ttl_s
        self._clock = clock
        self._max_entries = max_entries
        self._cache: OrderedDict[WindSampleRequest, _CachedSample] = (
            OrderedDict()
        )
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_stale_fallbacks = 0

    def cache_stats(self) -> dict[str, object]:
        return {
            "cache_entries": len(self._cache),
            "max_entries": self._max_entries,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "cache_stale_fallbacks": self._cache_stale_fallbacks,
        }

    def _get(self, request: WindSampleRequest) -> _CachedSample | None:
        item = self._cache.get(request)
        if item is not None:
            self._cache.move_to_end(request)
        return item

    def _put(
        self, request: WindSampleRequest, sample: WindSample, now: float
    ) -> None:
        self._cache[request] = _CachedSample(sample, now)
        self._cache.move_to_end(request)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

    async def winds_for(
        self, requests: Sequence[WindSampleRequest]
    ) -> tuple[WindSample, ...]:
        now = self._clock()
        fresh = [self._get(request) for request in requests]
        if all(
            item is not None and now - item.cached_at_s <= self._fresh_ttl_s
            for item in fresh
        ):
            self._cache_hits += 1
            return tuple(item.sample for item in fresh if item is not None)
        try:
            samples = await self._delegate.winds_for(requests)
        except Exception:
            stale = [self._get(request) for request in requests]
            if all(
                item is not None and now - item.cached_at_s <= self._stale_ttl_s
                for item in stale
            ):
                self._cache_stale_fallbacks += 1
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
        self._cache_misses += 1
        for request, sample in zip(requests, samples, strict=True):
            self._put(request, sample, now)
        return samples
