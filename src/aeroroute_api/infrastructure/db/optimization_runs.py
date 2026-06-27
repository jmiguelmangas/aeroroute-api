"""Short transaction adapters for the optimization run lifecycle."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.application.dto.optimization import (
    OptimizationRequest,
    OptimizationResponse,
)
from aeroroute_api.infrastructure.db.models import (
    OptimizationRun,
    TrajectoryCandidate,
)


@dataclass(frozen=True, slots=True)
class RunReservation:
    run: OptimizationRun
    should_execute: bool


def optimization_request_hash(request: OptimizationRequest) -> str:
    canonical = json.dumps(
        request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def reserve_optimization_run(
    session: AsyncSession, request: OptimizationRequest
) -> RunReservation:
    request_hash = optimization_request_hash(request)
    existing = await session.scalar(
        select(OptimizationRun).where(
            OptimizationRun.request_hash == request_hash
        )
    )
    if existing is not None:
        if existing.status == "failed":
            existing.status = "running"
            existing.error_code = None
            existing.completed_at = None
            await session.commit()
            return RunReservation(existing, True)
        await session.commit()
        return RunReservation(existing, False)
    run = OptimizationRun(
        request_hash=request_hash,
        status="running",
        algorithm_version="pending",
        input_json=request.model_dump(mode="json"),
        output_json=None,
    )
    session.add(run)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        concurrent = await session.scalar(
            select(OptimizationRun).where(
                OptimizationRun.request_hash == request_hash
            )
        )
        if concurrent is None:
            raise
        await session.commit()
        return RunReservation(concurrent, False)
    return RunReservation(run, True)


async def complete_optimization_run(
    session: AsyncSession,
    run_id: UUID,
    response: OptimizationResponse,
) -> OptimizationRun:
    run = await session.get(OptimizationRun, run_id)
    if run is None:
        raise ValueError("optimization run disappeared before completion")
    if run.status == "completed":
        return run
    if run.status != "running":
        raise ValueError("only a running optimization can be completed")
    run.status = "completed"
    run.algorithm_version = response.algorithm_version
    run.output_json = response.model_dump(mode="json")
    run.completed_at = datetime.now(UTC)
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


async def fail_optimization_run(
    session: AsyncSession, run_id: UUID, error_code: str
) -> None:
    run = await session.get(OptimizationRun, run_id)
    if run is None or run.status != "running":
        return
    run.status = "failed"
    run.error_code = error_code
    run.completed_at = datetime.now(UTC)
    await session.commit()
