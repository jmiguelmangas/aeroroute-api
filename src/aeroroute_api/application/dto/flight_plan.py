from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from aeroroute_api.application.dto.optimization import (
    OptimizationRequest,
    OptimizationResponse,
)


class FlightPlanRequest(OptimizationRequest):
    callsign: str | None = Field(default=None, min_length=2, max_length=12)


class FlightPlanResponse(BaseModel):
    flight_plan_id: str
    optimization_run_id: str
    status: Literal["completed"] = "completed"
    created_at: datetime
    coded_route: str
    request: FlightPlanRequest
    optimization: OptimizationResponse
    operationally_approved: bool = False
    disclaimer: str


class FlightPlanHistoryItem(BaseModel):
    flight_plan_id: str
    optimization_run_id: str
    created_at: datetime
    origin_icao: str
    destination_icao: str
    aircraft_type: str
    callsign: str | None = None
