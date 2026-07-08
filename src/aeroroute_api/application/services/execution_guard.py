"""Bound concurrent optimization work and enforce request deadlines."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

ResultT = TypeVar("ResultT")


class OptimizationCapacityExceeded(RuntimeError):
    pass


class OptimizationDeadlineExceeded(RuntimeError):
    pass


class OptimizationExecutionGuard:
    def __init__(
        self,
        max_concurrent: int = 2,
        queue_timeout_s: float = 0.25,
        execution_timeout_s: float = 15.0,
    ) -> None:
        if (
            max_concurrent < 1
            or queue_timeout_s <= 0
            or execution_timeout_s <= 0
        ):
            raise ValueError("execution limits must be positive")
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_timeout_s = queue_timeout_s
        self._execution_timeout_s = execution_timeout_s

    async def run(self, operation: Callable[[], Awaitable[ResultT]]) -> ResultT:
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=self._queue_timeout_s
            )
        except TimeoutError as error:
            raise OptimizationCapacityExceeded(
                "optimization capacity is exhausted"
            ) from error
        try:
            async with asyncio.timeout(self._execution_timeout_s):
                return await operation()
        except TimeoutError as error:
            raise OptimizationDeadlineExceeded(
                "optimization deadline was exceeded"
            ) from error
        finally:
            self._semaphore.release()
