from fastapi import APIRouter

from aeroroute_api.application.dto.operational import (
    OperationalReadinessGap,
    OperationalReadinessResponse,
    OpsMode,
)
from aeroroute_api.config import settings

router = APIRouter(
    prefix="/api/v1/operational-readiness",
    tags=["operational-readiness"],
)

ALLOWED_MODES: set[str] = {
    "simulator",
    "ops_candidate",
    "approved_operator_build",
}
DISCLAIMER = (
    "AeroRoute MLX is currently limited to simulator mode. It is not "
    "ICAO-fileable, dispatch-authorized, or suitable for operational or "
    "safety-critical decisions."
)
EVIDENCE_BASELINE = "operational-readiness-evidence-2026-07-08"
HAZARD_LOG_BASELINE = "operational-hazard-log-2026-07-08"


@router.get("", response_model=OperationalReadinessResponse)
async def operational_readiness() -> OperationalReadinessResponse:
    configured = settings()
    requested_mode = _mode(configured.ops_mode)
    gaps = [
        OperationalReadinessGap(
            code="operator_profile_missing",
            title="Launch operator not configured",
            severity="blocking",
            detail=(
                "Operational use requires a named operator, fleet, operation "
                "type, jurisdiction and approval path."
            ),
        ),
        OperationalReadinessGap(
            code="licensed_operational_data_missing",
            title="Operational data supply chain not approved",
            severity="blocking",
            detail=(
                "Navdata, weather, NOTAM, restrictions, airport, terrain and "
                "aircraft performance sources must be licensed, versioned and "
                "validated for operational use."
            ),
        ),
        OperationalReadinessGap(
            code="safety_case_missing",
            title="Safety case not accepted",
            severity="blocking",
            detail=(
                "Hazards, mitigations, verification evidence and fallback "
                "procedures must be accepted before operational dispatch."
            ),
        ),
        OperationalReadinessGap(
            code="requirements_traceability_missing",
            title="Requirements traceability incomplete",
            severity="blocking",
            detail=(
                "Operational requirements, tests, defects and release evidence "
                "must be traceable before enabling approved modes."
            ),
        ),
        OperationalReadinessGap(
            code="manual_acceptance_missing",
            title="Operator manuals and procedures not accepted",
            severity="blocking",
            detail=(
                "Dispatcher/pilot procedures, training, backup procedures and "
                "manual revisions must be accepted by the operator."
            ),
        ),
    ]
    return OperationalReadinessResponse(
        active_mode="simulator",
        requested_mode=requested_mode,
        operational_use_enabled=False,
        status="simulator_only" if requested_mode == "simulator" else "blocked",
        evidence_baseline=EVIDENCE_BASELINE,
        hazard_log_baseline=HAZARD_LOG_BASELINE,
        disclaimer=DISCLAIMER,
        gaps=gaps,
    )


def _mode(value: str) -> OpsMode:
    normalized = value.strip().lower()
    if normalized in ALLOWED_MODES:
        return normalized  # type: ignore[return-value]
    return "simulator"
