from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.explanation import ExplanationResponse
from aeroroute_api.application.services.explanation import (
    ExplanationFacts,
    render_deterministic_explanation,
)
from aeroroute_api.application.services.explanation_provider import (
    prefer_mlx_or_fallback,
)
from aeroroute_api.config import settings
from aeroroute_api.infrastructure.db.models import (
    OptimizationRun,
    TrajectoryCandidate,
)
from aeroroute_api.infrastructure.explanations.mlx_client import (
    MlxExplanationClient,
)

router = APIRouter(prefix="/api/v1/optimizations", tags=["explanations"])


@router.get("/{run_id}/explanation", response_model=ExplanationResponse)
async def get_explanation(
    run_id: UUID,
    session: AsyncSession = Depends(database_session),
) -> ExplanationResponse:
    run = await session.get(OptimizationRun, run_id)
    candidate = await session.scalar(
        select(TrajectoryCandidate)
        .where(
            TrajectoryCandidate.run_id == run_id, TrajectoryCandidate.rank == 0
        )
        .limit(1)
    )
    if run is None or candidate is None:
        raise HTTPException(
            status_code=404, detail="optimization run not found"
        )
    fallback = render_deterministic_explanation(
        ExplanationFacts(
            origin_icao=str(run.input_json["origin_icao"]),
            destination_icao=str(run.input_json["destination_icao"]),
            profile=str(run.input_json["profile"]),
            distance_m=candidate.distance_m,
            time_s=candidate.time_s,
            fuel_kg=candidate.fuel_kg,
        )
    )
    mlx_url = settings().mlx_service_url
    if mlx_url is None:
        return fallback
    allowed_values = [
        f"{candidate.distance_m / 1_000:.0f}",
        f"{candidate.time_s / 60:.0f}",
        f"{candidate.fuel_kg:.0f}",
    ]
    async with httpx.AsyncClient(timeout=5.0) as client:
        return await prefer_mlx_or_fallback(
            MlxExplanationClient(client, mlx_url), fallback, allowed_values
        )
