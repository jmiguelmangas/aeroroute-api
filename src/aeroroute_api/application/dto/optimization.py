from typing import Literal

from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):
    origin_icao: str = Field(min_length=3, max_length=8)
    destination_icao: str = Field(min_length=3, max_length=8)
    aircraft_type: Literal["A320", "B738"]
    profile: Literal["minimum_fuel", "minimum_time", "balanced"] = "balanced"


class CandidateResponse(BaseModel):
    path: list[str]
    geometry: list["RoutePoint"]
    distance_m: float
    time_s: float
    fuel_kg: float
    score: float


class RoutePoint(BaseModel):
    latitude_deg: float
    longitude_deg: float


class OptimizationResponse(BaseModel):
    run_id: str | None = None
    status: str
    algorithm_version: str
    winner: CandidateResponse | None
    alternatives: list[CandidateResponse]
    solver_termination_reason: str


class OptimizationHistoryItem(BaseModel):
    run_id: str
    status: str
    origin_icao: str
    destination_icao: str
    aircraft_type: str
    profile: str
