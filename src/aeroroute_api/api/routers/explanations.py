from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.api.dependencies import database_session
from aeroroute_api.application.dto.explanation import ExplanationResponse
from aeroroute_api.application.dto.optimization import OptimizationResponse
from aeroroute_api.application.services.explanation import (
    allowed_numeric_values,
    explanation_facts_from_result,
    render_deterministic_explanation,
)
from aeroroute_api.application.services.explanation_provider import (
    prefer_mlx_or_fallback,
)
from aeroroute_api.config import settings
from aeroroute_api.infrastructure.db.explanations import (
    explanation_response,
    find_explanation,
    persist_explanation,
)
from aeroroute_api.infrastructure.db.models import OptimizationRun
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
    if run is None or run.status != "completed" or run.output_json is None:
        raise HTTPException(
            status_code=404, detail="optimization run not found"
        )
    persisted = await find_explanation(session, run_id)
    if persisted is not None:
        return explanation_response(persisted)
    result = OptimizationResponse.model_validate(run.output_json)
    facts = explanation_facts_from_result(result)
    fallback = render_deterministic_explanation(facts)
    mlx_url = settings().mlx_service_url
    if mlx_url is None:
        response = fallback
    else:
        async with httpx.AsyncClient(
            timeout=settings().mlx_timeout_s
        ) as client:
            response = await prefer_mlx_or_fallback(
                MlxExplanationClient(client, mlx_url),
                fallback,
                allowed_numeric_values(facts),
            )
    stored = await persist_explanation(session, run_id, response, facts)
    return explanation_response(stored)
