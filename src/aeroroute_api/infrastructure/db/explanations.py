"""Idempotent persistence for generated optimization explanations."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.application.dto.explanation import ExplanationResponse
from aeroroute_api.application.services.explanation import ExplanationFacts
from aeroroute_api.infrastructure.db.models import OptimizationExplanation


async def find_explanation(
    session: AsyncSession, run_id: UUID
) -> OptimizationExplanation | None:
    return await session.scalar(
        select(OptimizationExplanation).where(
            OptimizationExplanation.run_id == run_id
        )
    )


async def persist_explanation(
    session: AsyncSession,
    run_id: UUID,
    response: ExplanationResponse,
    facts: ExplanationFacts,
) -> OptimizationExplanation:
    existing = await find_explanation(session, run_id)
    if existing is not None:
        return existing
    explanation = OptimizationExplanation(
        run_id=run_id,
        provider=response.provider,
        text=response.text,
        warnings_json=response.warnings,
        facts_json=facts.as_dict(),
    )
    session.add(explanation)
    await session.commit()
    return explanation


def explanation_response(
    explanation: OptimizationExplanation,
) -> ExplanationResponse:
    return ExplanationResponse(
        provider=explanation.provider,
        text=explanation.text,
        warnings=list(explanation.warnings_json),
    )
