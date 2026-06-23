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
