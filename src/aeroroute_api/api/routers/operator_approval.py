from fastapi import APIRouter

from aeroroute_api.application.dto.operator_approval import (
    OperatorApprovalGate,
    OperatorApprovalReadinessResponse,
)

router = APIRouter(
    prefix="/api/v1/operator-approval-readiness",
    tags=["operator-approval"],
)


@router.get("", response_model=OperatorApprovalReadinessResponse)
async def operator_approval_readiness() -> OperatorApprovalReadinessResponse:
    return OperatorApprovalReadinessResponse(
        gates=[
            OperatorApprovalGate(
                id="operator_acceptance",
                title="Operator acceptance not recorded",
                status="missing",
                detail=(
                    "No named operator has formally accepted the intended use, "
                    "limitations, manuals revision and approval path."
                ),
            ),
            OperatorApprovalGate(
                id="regulator_submission_pack",
                title="Regulator or principal-inspector pack missing",
                status="missing",
                detail=(
                    "The submission package, compliance mapping and authority "
                    "interaction record are not approved for operational use."
                ),
            ),
            OperatorApprovalGate(
                id="manuals_training",
                title="Manuals and training not accepted",
                status="missing",
                detail=(
                    "Operator manuals, dispatcher/pilot training, backup "
                    "procedures and compliance monitoring are not accepted."
                ),
            ),
            OperatorApprovalGate(
                id="parallel_run_campaign",
                title="Parallel-run campaign incomplete",
                status="missing",
                detail=(
                    "The system has not completed a documented parallel run "
                    "against the incumbent dispatch process."
                ),
            ),
            OperatorApprovalGate(
                id="go_no_go_decision",
                title="Go/no-go decision not recorded",
                status="missing",
                detail=(
                    "Open limitations, acceptance report, production tag and "
                    "operator go/no-go decision are not recorded."
                ),
            ),
        ]
    )
