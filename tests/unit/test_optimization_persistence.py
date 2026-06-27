from copy import deepcopy
from uuid import uuid4

import pytest

from aeroroute_api.application.dto.optimization import OptimizationRequest
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.db.models import OptimizationRun
from aeroroute_api.infrastructure.db.optimization_runs import (
    complete_optimization_run,
    fail_optimization_run,
    reserve_optimization_run,
)


class _Session:
    def __init__(self, existing=None) -> None:
        self.existing = existing
        self.added: list[object] = []
        self.commits = 0
        self.rollbacks = 0

    async def scalar(self, _statement):
        return self.existing

    async def get(self, _model, _identifier):
        return self.existing

    def add(self, value) -> None:
        if isinstance(value, OptimizationRun) and value.id is None:
            value.id = uuid4()
        self.existing = value
        self.added.append(value)

    def add_all(self, values) -> None:
        self.added.extend(values)

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1


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
async def test_run_commits_running_before_completed_snapshot() -> None:
    request, response = _request_and_response()
    session = _Session()

    reservation = await reserve_optimization_run(session, request)  # type: ignore[arg-type]
    run = reservation.run
    immutable_input = deepcopy(run.input_json)

    assert reservation.should_execute
    assert run.status == "running"
    assert run.output_json is None
    assert session.commits == 1

    completed = await complete_optimization_run(  # type: ignore[arg-type]
        session, run.id, response
    )

    assert completed.status == "completed"
    assert completed.output_json is not None
    assert completed.output_json["winner"]["display_geojson"]["type"] == (
        "LineString"
    )
    assert completed.input_json == immutable_input
    assert completed.completed_at is not None
    assert session.commits == 2


@pytest.mark.anyio
async def test_completed_duplicate_is_idempotent_and_not_reexecuted() -> None:
    request, response = _request_and_response()
    session = _Session()
    first = await reserve_optimization_run(session, request)  # type: ignore[arg-type]
    await complete_optimization_run(  # type: ignore[arg-type]
        session, first.run.id, response
    )

    duplicate = await reserve_optimization_run(session, request)  # type: ignore[arg-type]

    assert duplicate.run is first.run
    assert not duplicate.should_execute
    assert duplicate.run.status == "completed"


@pytest.mark.anyio
async def test_failed_run_is_committed_and_can_be_retried() -> None:
    request, _ = _request_and_response()
    session = _Session()
    reservation = await reserve_optimization_run(session, request)  # type: ignore[arg-type]

    await fail_optimization_run(  # type: ignore[arg-type]
        session, reservation.run.id, "provider_unavailable"
    )

    assert reservation.run.status == "failed"
    assert reservation.run.error_code == "provider_unavailable"
    assert reservation.run.completed_at is not None

    retry = await reserve_optimization_run(session, request)  # type: ignore[arg-type]
    assert retry.should_execute
    assert retry.run.status == "running"
    assert retry.run.error_code is None
