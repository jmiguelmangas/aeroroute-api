from types import SimpleNamespace
from uuid import uuid4

import pytest

from aeroroute_api.application.dto.optimization import OptimizationRequest
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.db.models import OptimizationRun
from aeroroute_api.infrastructure.db.optimization_runs import (
    persist_completed_run,
)


class _Session:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.commits = 0

    async def scalar(self, _statement):
        return self.existing

    def add(self, value) -> None:
        if isinstance(value, OptimizationRun) and value.id is None:
            value.id = uuid4()
        self.added.append(value)

    def add_all(self, values) -> None:
        self.added.extend(values)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def _request_and_response():
    request = OptimizationRequest(
        origin_icao="LEMD",
        destination_icao="KJFK",
        aircraft_type="A320",
        profile="minimum_fuel",
    )
    response = optimize_still_air(
        40.4722,
        -3.5608,
        40.6413,
        -73.7781,
        "A320",
        "minimum_fuel",
    ).model_copy(update={"request": request})
    return request, response


@pytest.mark.anyio
async def test_persistence_stores_complete_response_snapshot() -> None:
    request, response = _request_and_response()
    session = _Session()

    run = await persist_completed_run(session, request, response)  # type: ignore[arg-type]

    assert run.output_json is not None
    assert run.output_json["request"]["origin_icao"] == "LEMD"
    assert run.output_json["winner"]["display_geojson"]["type"] == "LineString"
    assert session.commits == 1


@pytest.mark.anyio
async def test_duplicate_legacy_run_is_backfilled() -> None:
    request, response = _request_and_response()
    existing = SimpleNamespace(output_json=None)
    session = _Session(existing)

    run = await persist_completed_run(session, request, response)  # type: ignore[arg-type]

    assert run is existing
    assert existing.output_json["winner"]["waypoints"]
    assert session.commits == 1
