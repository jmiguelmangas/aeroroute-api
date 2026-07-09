from datetime import UTC, datetime

import pytest

from aeroroute_api.domain.ports import WindSample, WindSampleRequest
from aeroroute_api.infrastructure.weather.cache import CachedWeatherPort


class _WeatherFixture:
    def __init__(self) -> None:
        self.calls = 0
        self.fails = False

    async def winds_for(self, requests):
        self.calls += 1
        if self.fails:
            raise RuntimeError("provider unavailable")
        return tuple(
            WindSample(10, 0, 10_400, request.at_utc, "fixture")
            for request in requests
        )


@pytest.mark.anyio
async def test_cache_returns_fresh_then_stale_sample_on_provider_failure() -> (
    None
):
    now = [0.0]
    provider = _WeatherFixture()
    cache = CachedWeatherPort(
        provider, fresh_ttl_s=10, stale_ttl_s=60, clock=lambda: now[0]
    )
    request = WindSampleRequest(
        40, -3, 250, datetime(2026, 6, 23, 12, tzinfo=UTC)
    )

    assert not (await cache.winds_for([request]))[0].stale
    assert provider.calls == 1
    assert not (await cache.winds_for([request]))[0].stale
    assert provider.calls == 1

    now[0] = 20
    provider.fails = True
    assert (await cache.winds_for([request]))[0].stale


def _request(pressure_hpa: int) -> WindSampleRequest:
    return WindSampleRequest(
        40, -3, pressure_hpa, datetime(2026, 6, 23, 12, tzinfo=UTC)
    )


@pytest.mark.anyio
async def test_cache_stays_bounded_across_many_distinct_keys() -> None:
    # Distinct WindSampleRequest keys (varying pressure level here, in
    # practice also lat/lon/forecast-hour) must not accumulate forever --
    # the cache should never exceed max_entries regardless of how many
    # unique requests are made over the process lifetime.
    provider = _WeatherFixture()
    cache = CachedWeatherPort(
        provider, fresh_ttl_s=10, stale_ttl_s=60, max_entries=5
    )

    for pressure in range(50):
        await cache.winds_for([_request(pressure)])
        assert cache.cache_stats()["cache_entries"] <= 5

    assert cache.cache_stats()["cache_entries"] == 5


@pytest.mark.anyio
async def test_cache_evicts_least_recently_used_entry_when_bounded() -> None:
    now = [0.0]
    provider = _WeatherFixture()
    cache = CachedWeatherPort(
        provider,
        fresh_ttl_s=10,
        stale_ttl_s=60,
        clock=lambda: now[0],
        max_entries=3,
    )
    one, two, three = (_request(pressure) for pressure in (100, 200, 300))
    # Insert in order 1, 2, 3 (LRU order: 1 oldest .. 3 newest), then touch
    # 1 so it becomes the most-recently-used and 2 becomes the LRU entry.
    await cache.winds_for([one])
    await cache.winds_for([two])
    await cache.winds_for([three])
    await cache.winds_for([one])
    assert cache.cache_stats()["cache_entries"] == 3

    # A 4th distinct key must evict the LRU entry (2), not the
    # least-recently-inserted one (1), proving eviction is LRU-ordered
    # rather than simple insertion-ordered.
    four = _request(400)
    await cache.winds_for([four])
    assert cache.cache_stats()["cache_entries"] == 3

    provider.calls = 0
    await cache.winds_for([one])
    await cache.winds_for([three])
    await cache.winds_for([four])
    assert provider.calls == 0  # 1, 3, and 4 are all still cached

    provider.calls = 0
    await cache.winds_for([two])
    assert provider.calls == 1  # 2 was evicted -- required a fresh fetch
