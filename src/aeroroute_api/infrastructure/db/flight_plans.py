"""Immutable flight-plan snapshot persistence."""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.application.dto.flight_plan import (
    FlightPlanRequest,
    FlightPlanResponse,
)
from aeroroute_api.application.dto.optimization import OptimizationResponse
from aeroroute_api.infrastructure.db.models import FlightPlanRecord

DISCLAIMER = (
    "AeroRoute MLX generates an educational pre-operational flight-plan "
    "simulation. Results are approximate, may use incomplete public data, "
    "are not an ICAO-fileable flight plan, and are not suitable for "
    "operational or safety-critical decisions."
)
FLIGHT_PLAN_HASH_VERSION = "flight-plan-v1"


class FlightPlanSnapshotCache:
    def __init__(self, max_entries: int = 128) -> None:
        self._max_entries = max_entries
        self._items: OrderedDict[UUID, FlightPlanResponse] = OrderedDict()

    def get(self, flight_plan_id: UUID) -> FlightPlanResponse | None:
        value = self._items.get(flight_plan_id)
        if value is not None:
            self._items.move_to_end(flight_plan_id)
        return value

    def put(self, value: FlightPlanResponse) -> None:
        identifier = UUID(value.flight_plan_id)
        self._items[identifier] = value
        self._items.move_to_end(identifier)
        while len(self._items) > self._max_entries:
            self._items.popitem(last=False)


def flight_plan_request_hash(request: FlightPlanRequest) -> str:
    canonical = json.dumps(
        {
            "version": FLIGHT_PLAN_HASH_VERSION,
            "request": request.model_dump(mode="json"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def store_flight_plan(
    session: AsyncSession,
    request: FlightPlanRequest,
    optimization: OptimizationResponse,
) -> FlightPlanRecord:
    if optimization.run_id is None:
        raise ValueError("flight plan requires a persisted optimization run")
    request_hash = flight_plan_request_hash(request)
    existing = await session.scalar(
        select(FlightPlanRecord).where(
            FlightPlanRecord.request_hash == request_hash
        )
    )
    if existing is not None:
        return existing
    record = FlightPlanRecord(
        optimization_run_id=UUID(optimization.run_id),
        request_hash=request_hash,
        input_json=request.model_dump(mode="json"),
        output_json={
            "coded_route": coded_route(request, optimization),
            "optimization": optimization.model_dump(mode="json"),
            "disclaimer": DISCLAIMER,
        },
    )
    session.add(record)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        concurrent = await session.scalar(
            select(FlightPlanRecord).where(
                FlightPlanRecord.request_hash == request_hash
            )
        )
        if concurrent is None:
            raise
        return concurrent
    await session.refresh(record)
    return record


def flight_plan_response(record: FlightPlanRecord) -> FlightPlanResponse:
    return FlightPlanResponse(
        flight_plan_id=str(record.id),
        optimization_run_id=str(record.optimization_run_id),
        created_at=record.created_at,
        coded_route=str(record.output_json["coded_route"]),
        request=FlightPlanRequest.model_validate(record.input_json),
        optimization=OptimizationResponse.model_validate(
            record.output_json["optimization"]
        ),
        disclaimer=str(record.output_json["disclaimer"]),
    )


def coded_route(
    request: FlightPlanRequest, optimization: OptimizationResponse
) -> str:
    winner = optimization.winner
    if winner is None:
        return f"{request.origin_icao.upper()} {request.destination_icao.upper()}"
    tokens = [request.origin_icao.upper()]
    previous_via: str | None = None
    for point in winner.waypoints[1:-1]:
        via = point.inbound_via
        if via and via != previous_via:
            tokens.append(via)
            previous_via = via
        name = point.display_name.upper()
        if name and name != tokens[-1]:
            tokens.append(name)
    final_via = winner.waypoints[-1].inbound_via if winner.waypoints else None
    if final_via and final_via != previous_via:
        tokens.append(final_via)
    tokens.append(request.destination_icao.upper())
    return " ".join(tokens)
