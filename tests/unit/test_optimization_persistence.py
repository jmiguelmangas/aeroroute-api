from copy import deepcopy
from uuid import uuid4

import pytest

from aeroroute_api.application.dto.optimization import (
    OptimizationRequest,
    TerminalSelection,
)
from aeroroute_api.application.services.optimization import optimize_still_air
from aeroroute_api.infrastructure.db.models import (
    NavigationSnapshot,
    OptimizationRun,
)
from aeroroute_api.infrastructure.db.optimization_runs import (
    complete_optimization_run,
    fail_optimization_run,
    reserve_optimization_run,
    optimization_request_hash,
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


def test_request_hash_changes_with_terminal_selection() -> None:
    base, _ = _request_and_response()
    selected = base.model_copy(
        update={"departure_runway": "32L", "arrival_runway": "13R"}
    )

    assert optimization_request_hash(base) != optimization_request_hash(
        selected
    )


@pytest.mark.anyio
async def test_completed_run_persists_navigation_snapshot() -> None:
    request, response = _request_and_response()
    assert response.winner is not None
    waypoints = list(response.winner.waypoints)
    waypoints[1] = waypoints[1].model_copy(
        update={
            "display_name": "PRADO",
            "kind": "navigation_fix",
            "navigation_source": "airac.net",
            "airac_cycle": "2606",
            "inbound_via": "Z224",
            "airway_validated": True,
        }
    )
    response = response.model_copy(
        update={
            "winner": response.winner.model_copy(
                update={"waypoints": waypoints}
            ),
            "terminal_selection": TerminalSelection(
                departure_runway="32L",
                sid_identifier="VAST2N",
                arrival_runway="13R",
                star_identifier="CAMRN5",
                airac_cycle="2606",
            ),
        }
    )
    session = _Session()
    reservation = await reserve_optimization_run(session, request)  # type: ignore[arg-type]

    await complete_optimization_run(  # type: ignore[arg-type]
        session, reservation.run.id, response
    )

    snapshots = [
        item for item in session.added if isinstance(item, NavigationSnapshot)
    ]
    assert len(snapshots) == 1
    assert snapshots[0].airac_cycle == "2606"
    terminal = snapshots[0].payload_json["terminal_selection"]
    assert isinstance(terminal, dict)
    assert terminal["sid_identifier"] == "VAST2N"


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
