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
                result = True
            elif window.count >= self._limit:
                result = False
            else:
                window.count += 1
                result = True
            self._evict_expired(now, skip=client)
            return result

    def _evict_expired(self, now: float, *, skip: str) -> None:
        # Opportunistic sweep so `_windows` doesn't grow unboundedly with
        # one entry per distinct client ever seen -- every call to allow()
        # also reaps other clients whose 60s window has elapsed. `skip`'s
        # entry was just written above and is always fresh, so it's never a
        # candidate for eviction here.
        expired = [
            other
            for other, window in self._windows.items()
            if other != skip and now - window.started_at >= 60.0
        ]
        for other in expired:
            del self._windows[other]


class RequestMetrics:
    def __init__(self) -> None:
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration_seconds: dict[tuple[str, str], float] = defaultdict(
            float
        )
        # HLD SS20.2: optimization-duration metric. Keyed by outcome
        # (success/capacity_exceeded/deadline_exceeded/failed/cancelled/...)
        # so slow-but-successful runs are distinguishable from runs that
        # errored out quickly. Sum+count (not a true histogram) matches the
        # sum-based convention already used for HTTP request duration above.
        self._optimization_count: dict[str, int] = defaultdict(int)
        self._optimization_duration_seconds: dict[str, float] = defaultdict(
            float
        )
        self._lock = Lock()

    def record(
        self, method: str, route: str, status_code: int, duration_s: float
    ) -> None:
        with self._lock:
            self._requests[(method, route, status_code)] += 1
            self._duration_seconds[(method, route)] += duration_s

    def record_optimization_duration(
        self, outcome: str, duration_s: float
    ) -> None:
        with self._lock:
            self._optimization_count[outcome] += 1
            self._optimization_duration_seconds[outcome] += duration_s

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
                lines.append(
                    f"aeroroute_http_requests_total{{{labels}}} {value}"
                )
            lines.extend(
                [
                    "# HELP aeroroute_http_request_duration_seconds_sum Total request duration.",
                    "# TYPE aeroroute_http_request_duration_seconds_sum counter",
                ]
            )
            for (method, route), duration in sorted(
                self._duration_seconds.items()
            ):
                labels = _labels(method=method, route=route)
                lines.append(
                    "aeroroute_http_request_duration_seconds_sum"
                    f"{{{labels}}} {duration:.6f}"
                )
            lines.extend(
                [
                    "# HELP aeroroute_optimization_duration_seconds_sum Total optimization execution duration by outcome.",
                    "# TYPE aeroroute_optimization_duration_seconds_sum counter",
                ]
            )
            for outcome, duration in sorted(
                self._optimization_duration_seconds.items()
            ):
                labels = _labels(outcome=outcome)
                lines.append(
                    "aeroroute_optimization_duration_seconds_sum"
                    f"{{{labels}}} {duration:.6f}"
                )
            lines.extend(
                [
                    "# HELP aeroroute_optimization_duration_seconds_count Optimization executions by outcome.",
                    "# TYPE aeroroute_optimization_duration_seconds_count counter",
                ]
            )
            for outcome, count in sorted(self._optimization_count.items()):
                labels = _labels(outcome=outcome)
                lines.append(
                    "aeroroute_optimization_duration_seconds_count"
                    f"{{{labels}}} {count}"
                )
        return "\n".join(lines) + "\n"


# Process-lifetime singleton shared between the HTTP middleware (main.py)
# and any router that wants to record additional application-level metrics
# (e.g. optimizations.py's optimization-duration recording) without a
# circular import back to main.py.
metrics = RequestMetrics()


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
