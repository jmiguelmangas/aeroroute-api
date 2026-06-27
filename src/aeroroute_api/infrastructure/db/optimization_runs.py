"""Persistence adapter for completed deterministic optimization results."""

from __future__ import annotations

import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.application.dto.optimization import (
    OptimizationRequest,
    OptimizationResponse,
)
from aeroroute_api.infrastructure.db.models import (
    OptimizationRun,
    TrajectoryCandidate,
)


async def persist_completed_run(
    session: AsyncSession,
    request: OptimizationRequest,
    response: OptimizationResponse,
) -> OptimizationRun:
    canonical_request = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    request_hash = hashlib.sha256(canonical_request.encode()).hexdigest()
    existing = await session.scalar(
        select(OptimizationRun).where(
            OptimizationRun.request_hash == request_hash
        )
    )
    if existing is not None:
        if existing.output_json is None:
            existing.output_json = response.model_dump(mode="json")
            await session.commit()
        return existing
    run = OptimizationRun(
        request_hash=request_hash,
        status=response.status,
        algorithm_version=response.algorithm_version,
        input_json=request.model_dump(mode="json"),
        output_json=response.model_dump(mode="json"),
    )
    session.add(run)
    await session.flush()
    candidates = [
        candidate
        for candidate in [response.winner, *response.alternatives]
        if candidate
    ]
    session.add_all(
        [
            TrajectoryCandidate(
                run_id=run.id,
                rank=rank,
                path_json=candidate.path,
                distance_m=candidate.distance_m,
                time_s=candidate.time_s,
                fuel_kg=candidate.fuel_kg,
                score=candidate.score,
            )
            for rank, candidate in enumerate(candidates)
        ]
    )
    await session.commit()
    return run
