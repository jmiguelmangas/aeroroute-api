from typing import Literal

from pydantic import BaseModel, Field


class OperatorApprovalGate(BaseModel):
    id: str
    title: str
    status: Literal["missing", "partial", "accepted"]
    detail: str


class OperatorApprovalReadinessResponse(BaseModel):
    contract_version: str = "1.0.0"
    baseline: str = "operator-approval-readiness-2026-07-09"
    operational_use_enabled: bool = False
    operator_approval_enabled: bool = False
    rollout_state: Literal["blocked"] = "blocked"
    ops_mode: Literal["simulator"] = "simulator"
    gates: list[OperatorApprovalGate] = Field(default_factory=list)
