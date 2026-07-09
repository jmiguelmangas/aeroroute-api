from fastapi import APIRouter

from aeroroute_api.application.dto.icao_fpl import (
    IcaoFplValidationRequest,
    IcaoFplValidationResponse,
)
from aeroroute_api.application.services.icao_fpl import validate_icao_fpl

router = APIRouter(prefix="/api/v1/icao-fpl", tags=["icao-fpl"])


@router.post("/validate", response_model=IcaoFplValidationResponse)
async def validate_fpl(
    request: IcaoFplValidationRequest,
) -> IcaoFplValidationResponse:
    return validate_icao_fpl(request)
