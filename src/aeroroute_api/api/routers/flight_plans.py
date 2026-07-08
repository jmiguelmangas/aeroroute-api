from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.api.routers.optimizations import create_optimization
from aeroroute_api.application.dto.flight_plan import (
    FlightPlanHistoryItem,
    FlightPlanRequest,
    FlightPlanResponse,
)
from aeroroute_api.application.dto.optimization import OptimizationRequest
from aeroroute_api.infrastructure.db.flight_plans import (
    FlightPlanSnapshotCache,
    flight_plan_response,
    store_flight_plan,
)
from aeroroute_api.infrastructure.db.models import FlightPlanRecord
from aeroroute_api.application.services.ofp_pdf import render_flight_plan_pdf

router = APIRouter(prefix="/api/v1/flight-plans", tags=["flight-plans"])
_snapshots = FlightPlanSnapshotCache()


@router.get("", response_model=list[FlightPlanHistoryItem])
async def list_flight_plans(
    session: AsyncSession = Depends(database_session),
) -> list[FlightPlanHistoryItem]:
    records = (
        await session.scalars(
            select(FlightPlanRecord)
            .order_by(FlightPlanRecord.created_at.desc())
            .limit(20)
        )
    ).all()
    return [
        FlightPlanHistoryItem(
            flight_plan_id=str(record.id),
            optimization_run_id=str(record.optimization_run_id),
            created_at=record.created_at,
            origin_icao=str(record.input_json["origin_icao"]),
            destination_icao=str(record.input_json["destination_icao"]),
            aircraft_type=str(record.input_json["aircraft_type"]),
            callsign=(
                str(record.input_json["callsign"])
                if record.input_json.get("callsign")
                else None
            ),
        )
        for record in records
    ]


@router.get("/{flight_plan_id}", response_model=FlightPlanResponse)
async def get_flight_plan(
    flight_plan_id: UUID,
    session: AsyncSession = Depends(database_session),
) -> FlightPlanResponse:
    return await _snapshot(session, flight_plan_id)


@router.get("/{flight_plan_id}/pdf")
async def get_flight_plan_pdf(
    flight_plan_id: UUID,
    session: AsyncSession = Depends(database_session),
) -> Response:
    content = render_flight_plan_pdf(await _snapshot(session, flight_plan_id))
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="aeroroute-ofp-{flight_plan_id}.pdf"'
            )
        },
    )


@router.post(
    "", response_model=FlightPlanResponse, status_code=status.HTTP_201_CREATED
)
async def create_flight_plan(
    request: FlightPlanRequest,
    session: AsyncSession = Depends(database_session),
) -> FlightPlanResponse:
    optimization_request = OptimizationRequest.model_validate(
        request.model_dump(exclude={"callsign"})
    )
    optimization = await create_optimization(optimization_request, session)
    record = await store_flight_plan(session, request, optimization)
    response = flight_plan_response(record)
    _snapshots.put(response)
    return response


async def _snapshot(
    session: AsyncSession, flight_plan_id: UUID
) -> FlightPlanResponse:
    cached = _snapshots.get(flight_plan_id)
    if cached is not None:
        return cached
    record = await session.get(FlightPlanRecord, flight_plan_id)
    if record is None:
        raise HTTPException(status_code=404, detail="flight plan not found")
    response = flight_plan_response(record)
    _snapshots.put(response)
    return response
