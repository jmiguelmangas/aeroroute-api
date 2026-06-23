from typing import Literal

from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):
    origin_icao: str = Field(min_length=3, max_length=8)
    destination_icao: str = Field(min_length=3, max_length=8)
    aircraft_type: Literal["A320", "B738"]
    profile: Literal["minimum_fuel", "minimum_time", "balanced"] = "balanced"


class CandidateResponse(BaseModel):
    path: list[str]
    distance_m: float
    time_s: float
    fuel_kg: float
    score: float


class OptimizationResponse(BaseModel):
    status: str
    algorithm_version: str
    winner: CandidateResponse | None
    alternatives: list[CandidateResponse]
    solver_termination_reason: str
