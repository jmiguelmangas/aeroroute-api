"""Small dependency-free HTTP telemetry and protection primitives."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
import logging
from threading import Lock
from time import monotonic
from typing import Callable

logger = logging.getLogger("aeroroute.http")
logger.setLevel(logging.INFO)
logger.propagate = False
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)


@dataclass(slots=True)
class _Window:
    started_at: float
    count: int


class FixedWindowRateLimiter:
    def __init__(
        self,
        requests_per_minute: int,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("rate limit must be positive")
        self._limit = requests_per_minute
        self._clock = clock
        self._windows: dict[str, _Window] = {}
        self._lock = Lock()

    def allow(self, client: str) -> bool:
        now = self._clock()
        with self._lock:
            window = self._windows.get(client)
            if window is None or now - window.started_at >= 60.0:
                self._windows[client] = _Window(now, 1)
                return True
            if window.count >= self._limit:
                return False
            window.count += 1
            return True


class RequestMetrics:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(float)
        self._lock = Lock()

    def record(
        self, method: str, route: str, status_code: int, duration_s: float
    ) -> None:
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            self._duration_seconds[(method, route)] += duration_s

    def render(self) -> str:
        lines = [
            "# HELP aeroroute_http_requests_total HTTP requests by route and status.",
            "# TYPE aeroroute_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status), value in sorted(
                self._requests.items()
            ):
                labels = _labels(method=method, route=route, status=str(status))
                lines.append(f"aeroroute_http_requests_total{{{labels}}} {value}")
            lines.extend(
                [
                    "# HELP aeroroute_http_request_duration_seconds_sum Total request duration.",
                    "# TYPE aeroroute_http_request_duration_seconds_sum counter",
                ]
            )
            for (method, route), value in sorted(
                self._duration_seconds.items()
            ):
                labels = _labels(method=method, route=route)
                lines.append(
                    "aeroroute_http_request_duration_seconds_sum"
                    f"{{{labels}}} {value:.6f}"
                )
        return "\n".join(lines) + "\n"


def log_request(
    *,
    request_id: str,
    method: str,
    route: str,
    status_code: int,
    duration_s: float,
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id,
                "method": method,
                "route": route,
                "status_code": status_code,
                "duration_ms": round(duration_s * 1000, 2),
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _labels(**values: str) -> str:
    return ",".join(
        f'{key}="{value.replace(chr(34), chr(39))}"'
        for key, value in values.items()
    )
