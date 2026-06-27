import asyncio

import pytest

from aeroroute_api.application.services.execution_guard import (
    OptimizationCapacityExceeded,
    OptimizationDeadlineExceeded,
    OptimizationExecutionGuard,
)


@pytest.mark.anyio
async def test_concurrency_limit_rejects_when_queue_budget_expires() -> None:
    guard = OptimizationExecutionGuard(
        max_concurrent=1,
        queue_timeout_s=0.01,
        execution_timeout_s=1,
    )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def blocking_operation() -> str:
        entered.set()
        await release.wait()
        return "done"

    first = asyncio.create_task(guard.run(blocking_operation))
    await entered.wait()
    with pytest.raises(OptimizationCapacityExceeded):
        await guard.run(blocking_operation)
    release.set()
    assert await first == "done"


@pytest.mark.anyio
async def test_execution_deadline_cancels_slow_operation() -> None:
    guard = OptimizationExecutionGuard(
        max_concurrent=1,
        queue_timeout_s=0.1,
        execution_timeout_s=0.01,
    )

    async def slow_operation() -> None:
        await asyncio.sleep(1)

    with pytest.raises(OptimizationDeadlineExceeded):
        await guard.run(slow_operation)
