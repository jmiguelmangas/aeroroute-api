from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from aeroroute_api.api.routers.optimizations import get_optimization
from aeroroute_api.application.dto.optimization import OptimizationRequest
from aeroroute_api.application.services.optimization import optimize_still_air


class _Session:
    def __init__(self, run: SimpleNamespace | None) -> None:
        self.run = run

    async def get(self, _model, _run_id):
        return self.run


@pytest.mark.anyio
async def test_get_optimization_rehydrates_complete_snapshot() -> None:
    run_id = uuid4()
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
    session = _Session(
        SimpleNamespace(id=run_id, output_json=response.model_dump(mode="json"))
    )

    restored = await get_optimization(run_id, session=session)  # type: ignore[arg-type]

    assert restored.run_id == str(run_id)
    assert restored.request == request
    assert restored.winner is not None
    assert restored.winner.display_geojson.type == "LineString"


@pytest.mark.anyio
async def test_get_optimization_rejects_legacy_run_without_snapshot() -> None:
    run_id = uuid4()
    session = _Session(SimpleNamespace(id=run_id, output_json=None))

    with pytest.raises(HTTPException) as error:
        await get_optimization(run_id, session=session)  # type: ignore[arg-type]

    assert error.value.status_code == 409


@pytest.mark.anyio
async def test_get_optimization_returns_not_found() -> None:
    with pytest.raises(HTTPException) as error:
        await get_optimization(uuid4(), session=_Session(None))  # type: ignore[arg-type]

    assert error.value.status_code == 404
