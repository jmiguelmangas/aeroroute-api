from typing import Literal

from pydantic import BaseModel, Field


OpsMode = Literal["simulator", "ops_candidate", "approved_operator_build"]


class OperationalReadinessGap(BaseModel):
    code: str
    title: str
    severity: Literal["blocking", "warning"]
    detail: str


class OperationalReadinessResponse(BaseModel):
    active_mode: OpsMode
    requested_mode: OpsMode
    operational_use_enabled: bool
    status: Literal["simulator_only", "blocked", "approved"]
    approval_required: bool = True
    regulator_path_identified: bool = False
    operator_profile_present: bool = False
    licensed_operational_data_present: bool = False
    safety_case_present: bool = False
    requirements_traceability_present: bool = False
    manual_procedure_acceptance_present: bool = False
    disclaimer: str
    gaps: list[OperationalReadinessGap] = Field(default_factory=list)
