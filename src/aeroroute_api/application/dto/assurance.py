from typing import Literal

from pydantic import BaseModel, Field


class AssuranceReadinessGate(BaseModel):
    id: str
    title: str
    status: Literal["missing", "partial", "accepted"]
    detail: str


class AssuranceReadinessResponse(BaseModel):
    contract_version: str = "1.0.0"
    baseline: str = "assurance-readiness-2026-07-09"
    operational_use_enabled: bool = False
    assurance_enabled: bool = False
    status: Literal["blocked"] = "blocked"
    gates: list[AssuranceReadinessGate] = Field(default_factory=list)
