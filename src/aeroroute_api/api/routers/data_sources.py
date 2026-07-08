from fastapi import APIRouter

from aeroroute_api.application.dto.data_sources import (
    OperationalDataSourcesResponse,
)
from aeroroute_api.application.services.data_sources import (
    simulator_data_sources,
)
from aeroroute_api.api.routers.operational import OpsMode, _mode
from aeroroute_api.config import settings

router = APIRouter(
    prefix="/api/v1/operational-data-sources",
    tags=["operational-data-sources"],
)


@router.get("", response_model=OperationalDataSourcesResponse)
async def operational_data_sources() -> OperationalDataSourcesResponse:
    requested_mode: OpsMode = _mode(settings().ops_mode)
    sources = simulator_data_sources()
    blocking_domains = [
        source.domain for source in sources if not source.operational_ready
    ]
    return OperationalDataSourcesResponse(
        active_mode="simulator",
        requested_mode=requested_mode,
        operational_use_enabled=False,
        status="simulator_only" if requested_mode == "simulator" else "blocked",
        sources=sources,
        blocking_domains=blocking_domains,
    )
