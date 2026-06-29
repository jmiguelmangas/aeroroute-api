from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Callable, MutableMapping, TypeVar

import httpx

K = TypeVar("K")
V = TypeVar("V")


class AiracProviderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AiracFix:
    identifier: str
    latitude_deg: float
    longitude_deg: float
    region: str | None
    fix_type: str
    distance_nm: float
    cycle: str | None


@dataclass(frozen=True, slots=True)
class AiracAirwayPoint:
    identifier: str
    latitude_deg: float
    longitude_deg: float
    airway: str
    cycle: str | None


@dataclass(frozen=True, slots=True)
class AiracProcedurePoint:
    identifier: str
    latitude_deg: float
    longitude_deg: float


@dataclass(frozen=True, slots=True)
class AiracProcedure:
    identifier: str
    procedure_type: str
    runway: str
    points: tuple[AiracProcedurePoint, ...]
    cycle: str | None


@dataclass(frozen=True, slots=True)
class AiracRunway:
    identifier: str
    bearing_deg: float
    length_ft: float
    width_ft: float | None
    surface: str | None
    cycle: str | None


class AiracNavigationClient:
    base_url = "https://airac.net/api/v1"

    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        cache_ttl_s: float = 6 * 60 * 60,
        max_concurrent_requests: int = 8,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._client = client
        self._cache_ttl_s = cache_ttl_s
        self._clock = clock
        self._request_slots = asyncio.Semaphore(max_concurrent_requests)
        self._cache_expiry: dict[tuple[str, object], float] = {}
        self._observed_cycles: set[str] = set()
        self._membership_cache: dict[str, tuple[str, ...]] = {}
        self._airway_cache: dict[str, tuple[AiracAirwayPoint, ...]] = {}
        self._procedure_cache: dict[
            tuple[str, str], tuple[AiracProcedure, ...]
        ] = {}
        self._runway_cache: dict[str, tuple[AiracRunway, ...]] = {}
        self._airport_cache: dict[str, dict[str, object]] = {}

    def manifest(self) -> dict[str, object]:
        return {
            "source": "airac.net",
            "base_url": self.base_url,
            "observed_cycles": sorted(self._observed_cycles),
            "cache_ttl_s": self._cache_ttl_s,
            "loading": "on_demand",
        }

    async def airport_position(self, airport: str) -> tuple[float, float]:
        data = await self._airport_data(airport)
        coordinates = data["coordinates"]
        if not isinstance(coordinates, dict):
            raise AiracProviderError("AIRAC airport coordinates are invalid")
        try:
            return float(coordinates["lat"]), float(coordinates["lon"])
        except (KeyError, TypeError, ValueError) as error:
            raise AiracProviderError(
                "AIRAC airport coordinates are invalid"
            ) from error

    async def _airport_data(self, airport: str) -> dict[str, object]:
        airport = airport.upper()
        cached = self._cached("airport", self._airport_cache, airport)
        if cached is not None:
            return cached
        try:
            response = await self._get(
                f"{self.base_url}/airports/{airport}",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            response.raise_for_status()
            data = response.json()["data"]
            if not isinstance(data, dict):
                raise TypeError("AIRAC airport data is not an object")
            data["_airac_cycle"] = self._cycle(response)
            self._store("airport", self._airport_cache, airport, data)
            return data
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError("AIRAC airport lookup failed") from error

    async def runways(self, airport: str) -> tuple[AiracRunway, ...]:
        airport = airport.upper()
        cached = self._cached("runway", self._runway_cache, airport)
        if cached is not None:
            return cached
        try:
            data = await self._airport_data(airport)
            raw_runways = data.get("runways", [])
            runways: list[AiracRunway] = []
            for runway in raw_runways:
                for prefix in ("base", "reciprocal"):
                    identifier = runway.get(f"{prefix}_identifier")
                    bearing = runway.get(f"{prefix}_bearing")
                    if not identifier:
                        continue
                    if bearing is None:
                        bearing = _bearing_from_runway_identifier(
                            str(identifier)
                        )
                    runways.append(
                        AiracRunway(
                            identifier=str(identifier),
                            bearing_deg=float(bearing),
                            length_ft=float(runway["length_ft"]),
                            width_ft=(
                                float(runway["width_ft"])
                                if runway.get("width_ft") is not None
                                else None
                            ),
                            surface=(
                                str(runway["surface"])
                                if runway.get("surface")
                                else None
                            ),
                            cycle=(
                                str(data["_airac_cycle"])
                                if data.get("_airac_cycle")
                                else None
                            ),
                        )
                    )
            output = tuple(sorted(runways, key=lambda item: item.identifier))
            self._store("runway", self._runway_cache, airport, output)
            return output
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError("AIRAC runway lookup failed") from error

    async def nearest_fix(
        self, latitude_deg: float, longitude_deg: float, radius_nm: float = 120
    ) -> AiracFix | None:
        fixes = await self.nearby_fixes(
            latitude_deg, longitude_deg, radius_nm=radius_nm, limit=1
        )
        return fixes[0] if fixes else None

    async def nearby_fixes(
        self,
        latitude_deg: float,
        longitude_deg: float,
        radius_nm: float = 120,
        limit: int = 5,
    ) -> tuple[AiracFix, ...]:
        try:
            response = await self._get(
                f"{self.base_url}/waypoints/nearby",
                params={
                    "latitude": latitude_deg,
                    "longitude": longitude_deg,
                    "radius": radius_nm,
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            response.raise_for_status()
            payload = response.json()
            fixes = payload["data"]
            if not isinstance(fixes, list):
                raise TypeError("AIRAC waypoint data is not a list")
            eligible = [
                item
                for item in fixes
                if item.get("type", {}).get("code") in {"C", "R", "W"}
            ]
            if not eligible:
                return ()
            ordered = sorted(
                eligible, key=lambda value: float(value["distance_nm"])
            )
            return tuple(
                AiracFix(
                    identifier=str(item["identifier"]),
                    latitude_deg=float(item["latitude"]),
                    longitude_deg=float(item["longitude"]),
                    region=(
                        str(item["region"]) if item.get("region") else None
                    ),
                    fix_type=str(item["type"]["code"]),
                    distance_nm=float(item["distance_nm"]),
                    cycle=self._cycle(response),
                )
                for item in ordered[:limit]
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError("AIRAC waypoint lookup failed") from error

    async def airways_for_fix(self, identifier: str) -> tuple[str, ...]:
        cached = self._cached(
            "membership", self._membership_cache, identifier
        )
        if cached is not None:
            return cached
        try:
            response = await self._get(
                f"{self.base_url}/airways",
                params={"fix": identifier},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            response.raise_for_status()
            self._cycle(response)
            payload = response.json()
            routes = payload.get("data", [])
            if not isinstance(routes, list):
                raise TypeError("AIRAC airway membership data is not a list")
            result = tuple(
                str(route["identifier"])
                for route in routes
                if route.get("identifier")
            )
            self._store(
                "membership", self._membership_cache, identifier, result
            )
            return result
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError(
                "AIRAC airway membership failed"
            ) from error

    async def airway_points(
        self, identifier: str
    ) -> tuple[AiracAirwayPoint, ...]:
        cached = self._cached("airway", self._airway_cache, identifier)
        if cached is not None:
            return cached
        try:
            response = await self._get(
                f"{self.base_url}/airways/{identifier}",
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            response.raise_for_status()
            segments = response.json()["data"]["segments"]
            if not isinstance(segments, list):
                raise TypeError("AIRAC airway segments are not a list")
            result = tuple(
                AiracAirwayPoint(
                    identifier=str(segment["fix_identifier"]),
                    latitude_deg=float(segment["fix_coordinates"]["lat"]),
                    longitude_deg=float(segment["fix_coordinates"]["lon"]),
                    airway=identifier,
                    cycle=self._cycle(response),
                )
                for segment in segments
                if segment.get("fix_identifier")
                and segment.get("fix_coordinates")
            )
            self._store("airway", self._airway_cache, identifier, result)
            return result
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError(
                "AIRAC airway detail lookup failed"
            ) from error

    async def airway_route(
        self, from_identifier: str, to_identifier: str
    ) -> tuple[str, ...]:
        try:
            response = await self._get(
                f"{self.base_url}/airways/route",
                params={"from": from_identifier, "to": to_identifier},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            if response.status_code == 404:
                return ()
            response.raise_for_status()
            self._cycle(response)
            payload = response.json()
            if payload.get("status") != "success":
                return ()
            routes = payload.get("data", [])
            if not isinstance(routes, list):
                raise TypeError("AIRAC airway route data is not a list")
            return tuple(
                str(route["identifier"])
                for route in routes
                if route.get("identifier")
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError("AIRAC airway lookup failed") from error

    async def procedures(
        self, airport: str, procedure_type: str
    ) -> tuple[AiracProcedure, ...]:
        cache_key = (airport, procedure_type)
        cached = self._cached(
            "procedure", self._procedure_cache, cache_key
        )
        if cached is not None:
            return cached
        try:
            response = await self._get(
                f"{self.base_url}/procedures",
                params={"airport": airport, "type": procedure_type},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            response.raise_for_status()
            self._cycle(response)
            summaries = response.json()["data"]
            details = await asyncio.gather(
                *(
                    self._get(
                        f"{self.base_url}/procedures/{airport}/{summary['identifier']}",
                        headers={
                            "Accept": "application/json",
                            "User-Agent": "AeroRoute-MLX/0.1 (development)",
                        },
                    )
                    for summary in summaries
                )
            )
            result: list[AiracProcedure] = []
            for detail in details:
                detail.raise_for_status()
                data = detail.json()["data"]
                runway_transitions = data.get("runway_transitions", {})
                transition_groups = (
                    list(runway_transitions.items())
                    if isinstance(runway_transitions, dict)
                    else []
                )
                if not transition_groups:
                    generic_transitions = data.get("transitions", {})
                    if isinstance(generic_transitions, dict):
                        transition_groups = [
                            ("ALL", segments)
                            for segments in generic_transitions.values()
                        ]
                for runway, segments in transition_groups:
                    points = tuple(
                        AiracProcedurePoint(
                            identifier=str(segment["fix_identifier"]),
                            latitude_deg=float(
                                segment["fix_coordinates"]["lat"]
                            ),
                            longitude_deg=float(
                                segment["fix_coordinates"]["lon"]
                            ),
                        )
                        for segment in segments
                        if segment.get("fix_identifier")
                        and segment.get("fix_coordinates")
                    )
                    if points:
                        result.append(
                            AiracProcedure(
                                identifier=str(data["identifier"]),
                                procedure_type=procedure_type,
                                runway=str(runway),
                                points=points,
                                cycle=self._cycle(detail),
                            )
                        )
            output = tuple(result)
            self._store(
                "procedure", self._procedure_cache, cache_key, output
            )
            return output
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError("AIRAC procedure lookup failed") from error

    def _cycle(self, response: httpx.Response) -> str | None:
        cycle = response.headers.get("X-AIRAC-Cycle")
        if cycle:
            self._observed_cycles.add(cycle)
        return cycle

    async def _get(self, url: str, **kwargs: object) -> httpx.Response:
        async with self._request_slots:
            return await self._client.get(url, **kwargs)

    def _cached(
        self,
        namespace: str,
        cache: MutableMapping[K, V],
        key: K,
    ) -> V | None:
        expiry_key = (namespace, key)
        if self._cache_expiry.get(expiry_key, 0.0) > self._clock():
            return cache.get(key)
        cache.pop(key, None)
        self._cache_expiry.pop(expiry_key, None)
        return None

    def _store(
        self,
        namespace: str,
        cache: MutableMapping[K, V],
        key: K,
        value: V,
    ) -> None:
        cache[key] = value
        self._cache_expiry[(namespace, key)] = (
            self._clock() + self._cache_ttl_s
        )


def _bearing_from_runway_identifier(identifier: str) -> float:
    digits = "".join(
        character for character in identifier if character.isdigit()
    )
    if not digits:
        raise ValueError("runway identifier has no magnetic bearing")
    bearing = int(digits[:2]) * 10
    return float(360 if bearing == 0 else bearing)
