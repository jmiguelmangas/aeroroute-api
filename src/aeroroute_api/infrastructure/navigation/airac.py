from __future__ import annotations

from dataclasses import dataclass

import httpx


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


class AiracNavigationClient:
    base_url = "https://airac.net/api/v1"

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

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
            response = await self._client.get(
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
                    cycle=response.headers.get("X-AIRAC-Cycle"),
                )
                for item in ordered[:limit]
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError("AIRAC waypoint lookup failed") from error

    async def airways_for_fix(self, identifier: str) -> tuple[str, ...]:
        try:
            response = await self._client.get(
                f"{self.base_url}/airways",
                params={"fix": identifier},
                headers={
                    "Accept": "application/json",
                    "User-Agent": "AeroRoute-MLX/0.1 (development)",
                },
            )
            response.raise_for_status()
            payload = response.json()
            routes = payload.get("data", [])
            if not isinstance(routes, list):
                raise TypeError("AIRAC airway membership data is not a list")
            return tuple(
                str(route["identifier"])
                for route in routes
                if route.get("identifier")
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise AiracProviderError(
                "AIRAC airway membership failed"
            ) from error

    async def airway_route(
        self, from_identifier: str, to_identifier: str
    ) -> tuple[str, ...]:
        try:
            response = await self._client.get(
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
