from fastapi import APIRouter

from aeroroute_api.application.dto.assurance import (
    AssuranceReadinessGate,
    AssuranceReadinessResponse,
)

router = APIRouter(prefix="/api/v1/assurance-readiness", tags=["assurance"])


@router.get("", response_model=AssuranceReadinessResponse)
async def assurance_readiness() -> AssuranceReadinessResponse:
    return AssuranceReadinessResponse(
        gates=[
            AssuranceReadinessGate(
                id="requirements_traceability",
                title="Requirements-to-test traceability not accepted",
                status="missing",
                detail=(
                    "Operational requirements, hazards, tests, defects and "
                    "release evidence are not yet linked into an accepted "
                    "traceability repository."
                ),
            ),
            AssuranceReadinessGate(
                id="independent_validation",
                title="Independent verification and validation missing",
                status="missing",
                detail=(
                    "Safety-relevant route, fuel, data and filing behavior "
                    "has not been independently benchmarked and accepted."
                ),
            ),
            AssuranceReadinessGate(
                id="release_data_cycle_control",
                title="Release and data-cycle control incomplete",
                status="missing",
                detail=(
                    "Operational releases are not tied to approved data cycles, "
                    "supplier review, rollback procedure and immutable evidence."
                ),
            ),
            AssuranceReadinessGate(
                id="audit_slo_observability",
                title="Operational audit logs and SLOs missing",
                status="missing",
                detail=(
                    "Production audit logging, retention policy, alerting and "
                    "operator SLOs are not approved."
                ),
            ),
            AssuranceReadinessGate(
                id="security_incident_response",
                title="Security and incident response not accepted",
                status="missing",
                detail=(
                    "Threat model, access control, secrets process, penetration "
                    "testing and incident response are not approved for ops."
                ),
            ),
            AssuranceReadinessGate(
                id="fallback_procedures",
                title="Fallback and backup procedures missing",
                status="missing",
                detail=(
                    "Operator backup dispatch procedures and degraded-mode "
                    "manuals are not accepted."
                ),
            ),
        ]
    )
