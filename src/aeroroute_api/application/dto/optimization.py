from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):
    origin_icao: str = Field(min_length=3, max_length=8)
    destination_icao: str = Field(min_length=3, max_length=8)
    departure_time_utc: datetime | None = None
    aircraft_type: Literal["A320", "B738"]
    profile: Literal["minimum_fuel", "minimum_time", "balanced"] = "balanced"


class CandidateResponse(BaseModel):
    path: list[str]
    geometry: list["RoutePoint"]
    distance_m: float
    time_s: float
    fuel_kg: float
    score: float
    display_geojson: "GeoJsonGeometry"
    waypoints: list["WaypointDetail"]
    fuel_breakdown: "FuelBreakdown | None" = None
    objective_breakdown: "ObjectiveBreakdown | None" = None


class FuelBreakdown(BaseModel):
    modeled_trip_fuel_kg: float
    cruise_fuel_kg: float
    fixed_climb_descent_fuel_kg: float
    mass_assumption_fuel_kg: float
    reserves_optimized: bool = False


class ObjectiveBreakdown(BaseModel):
    fuel_delta: float
    time_delta: float
    route_extension: float
    fuel_weight: float
    time_weight: float
    extension_weight: float
    fuel_component: float
    time_component: float
    extension_component: float
    total_score: float


class FuelIterationSummary(BaseModel):
    initial_mass_kg: float
    trip_fuel_kg: float
    iterations: int
    converged: bool
    warning_code: str | None = None


class RoutePoint(BaseModel):
    latitude_deg: float
    longitude_deg: float


class GeoJsonGeometry(BaseModel):
    type: Literal["LineString", "MultiLineString"]
    coordinates: list[list[float]] | list[list[list[float]]]


class WaypointDetail(BaseModel):
    node_id: str
    latitude_deg: float
    longitude_deg: float
    flight_level: int
    elapsed_time_s: float
    cumulative_distance_m: float
    cumulative_fuel_kg: float
    estimated_mass_kg: float
    wind_component_kt: float | None = None


class DataQualityFlag(BaseModel):
    code: str
    severity: Literal["info", "warning"]
    message: str


class OptimizationResponse(BaseModel):
    run_id: str | None = None
    status: str
    algorithm_version: str
    winner: CandidateResponse | None
    alternatives: list[CandidateResponse]
    solver_termination_reason: str
    baseline: CandidateResponse | None = None
    assumptions: list[str] = Field(default_factory=list)
    data_quality: list[DataQualityFlag] = Field(default_factory=list)
    request: OptimizationRequest | None = None
    fuel_iteration: FuelIterationSummary | None = None


class OptimizationHistoryItem(BaseModel):
    run_id: str
    status: str
    origin_icao: str
    destination_icao: str
    aircraft_type: str
    profile: str
