from typing import Literal

from pydantic import BaseModel, Field


class DispatchReadinessGate(BaseModel):
    id: str
    title: str
    status: Literal["missing", "partial", "accepted"]
    detail: str


class DispatchReadinessResponse(BaseModel):
    contract_version: str = "1.0.0"
    baseline: str = "dispatch-readiness-2026-07-09"
    operational_use_enabled: bool = False
    dispatch_release_enabled: bool = False
    status: Literal["blocked"] = "blocked"
    gates: list[DispatchReadinessGate] = Field(default_factory=list)
