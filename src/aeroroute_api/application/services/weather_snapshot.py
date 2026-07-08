"""Build normalized, immutable route weather snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from aeroroute_optimizer import public as optimizer

from aeroroute_api.domain.ports import (
    WeatherPort,
    WindSample,
    WindSampleRequest,
)
from aeroroute_api.infrastructure.weather.interpolation import (
    HeightWindSample,
    interpolate_height,
    interpolate_time,
)


class WeatherSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RouteWeatherSnapshot:
    vectors: dict[tuple[int, float], optimizer.WindVector]
    source: str
    fetched_at_utc: datetime | None
    stale: bool

    def wind_at(
        self, _point: optimizer.GeoPoint, altitude_m: float, layer: int
    ) -> optimizer.WindVector:
        return self.vectors[(layer, altitude_m)]


async def build_route_weather_snapshot(
    weather: WeatherPort,
    origin: optimizer.GeoPoint,
    destination: optimizer.GeoPoint,
    departure_time_utc: datetime,
    cruise_levels_m: tuple[float, ...],
    layers: int = 6,
) -> RouteWeatherSnapshot:
    departure = _as_utc(departure_time_utc)
    points = optimizer.sample_baseline(origin, destination, layers)
    requests: list[WindSampleRequest] = []
    targets: dict[int, datetime] = {}
    for layer, point in enumerate(points[:-1]):
        target = departure + timedelta(hours=8 * layer / layers)
        targets[layer] = target
        earlier = target.replace(minute=0, second=0, microsecond=0)
        times = (
            (earlier,)
            if target == earlier
            else (earlier, earlier + timedelta(hours=1))
        )
        for at_utc in times:
            for pressure_hpa in (300, 250, 200):
                requests.append(
                    WindSampleRequest(
                        point.latitude_deg,
                        point.longitude_deg,
                        pressure_hpa,
                        at_utc,
                    )
                )
    try:
        samples = await weather.winds_for(requests)
        if len(samples) != len(requests):
            raise ValueError("weather sample count changed")
        by_request = dict(zip(requests, samples, strict=True))
        vectors: dict[tuple[int, float], optimizer.WindVector] = {}
        for layer, point in enumerate(points[:-1]):
            target = targets[layer]
            pressure_samples = [
                _sample_at_target(
                    by_request,
                    point,
                    pressure_hpa,
                    target,
                )
                for pressure_hpa in (300, 250, 200)
            ]
            ordered = sorted(
                pressure_samples,
                key=lambda sample: sample.geopotential_height_m,
            )
            for altitude_m in cruise_levels_m:
                lower, upper = _height_bracket(ordered, altitude_m)
                sample = interpolate_height(
                    HeightWindSample(lower.geopotential_height_m, lower),
                    HeightWindSample(upper.geopotential_height_m, upper),
                    altitude_m,
                )
                vectors[(layer, altitude_m)] = optimizer.WindVector(
                    sample.east_mps, sample.north_mps
                )
    except Exception as error:
        raise WeatherSnapshotError(
            "route weather snapshot unavailable"
        ) from error
    return RouteWeatherSnapshot(
        vectors=vectors,
        source=samples[0].source,
        fetched_at_utc=samples[0].fetched_at_utc,
        stale=any(sample.stale for sample in samples),
    )


def _sample_at_target(
    samples: dict[WindSampleRequest, WindSample],
    point: optimizer.GeoPoint,
    pressure_hpa: int,
    target: datetime,
) -> WindSample:
    earlier = target.replace(minute=0, second=0, microsecond=0)
    first = samples[
        WindSampleRequest(
            point.latitude_deg,
            point.longitude_deg,
            pressure_hpa,
            earlier,
        )
    ]
    if target == earlier:
        return first
    later_time = earlier + timedelta(hours=1)
    later = samples[
        WindSampleRequest(
            point.latitude_deg,
            point.longitude_deg,
            pressure_hpa,
            later_time,
        )
    ]
    return interpolate_time(first, later, target)


def _height_bracket(
    samples: list[WindSample], target_height_m: float
) -> tuple[WindSample, WindSample]:
    for lower, upper in zip(samples, samples[1:]):
        if (
            lower.geopotential_height_m
            <= target_height_m
            <= upper.geopotential_height_m
        ):
            return lower, upper
    raise ValueError("cruise altitude is outside pressure-level bounds")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
