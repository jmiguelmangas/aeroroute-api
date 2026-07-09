from fastapi import APIRouter

from aeroroute_api.application.dto.dispatch import (
    DispatchReadinessGate,
    DispatchReadinessResponse,
)

router = APIRouter(prefix="/api/v1/dispatch-readiness", tags=["dispatch"])


@router.get("", response_model=DispatchReadinessResponse)
async def dispatch_readiness() -> DispatchReadinessResponse:
    return DispatchReadinessResponse(
        gates=[
            DispatchReadinessGate(
                id="approved_performance_data",
                title="Approved aircraft performance data missing",
                status="missing",
                detail=(
                    "Current fuel and mass results use an educational curated "
                    "model, not operator-approved tail or fleet performance."
                ),
            ),
            DispatchReadinessGate(
                id="fuel_policy_acceptance",
                title="Operational fuel policy not accepted",
                status="missing",
                detail=(
                    "Simplified EASA-style fuel arithmetic is visible, but not "
                    "approved as company dispatch policy."
                ),
            ),
            DispatchReadinessGate(
                id="runway_weight_balance_limits",
                title="Runway, weight and balance limits not operational",
                status="missing",
                detail=(
                    "Runway performance, limitations, mass and balance inputs "
                    "are not connected to approved dispatch data."
                ),
            ),
            DispatchReadinessGate(
                id="minima_alternate_suitability",
                title="Minima and alternate suitability missing",
                status="missing",
                detail=(
                    "Weather minima, airport status, NOTAM and alternate "
                    "suitability do not yet block dispatch release."
                ),
            ),
            DispatchReadinessGate(
                id="dispatcher_signoff",
                title="Dispatcher/pilot release workflow missing",
                status="missing",
                detail=(
                    "No approved release state machine, signoff, revision "
                    "history or immutable operational record exists."
                ),
            ),
        ]
    )
