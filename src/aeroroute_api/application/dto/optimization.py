from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):
    origin_icao: str = Field(min_length=3, max_length=8)
    destination_icao: str = Field(min_length=3, max_length=8)
    departure_time_utc: datetime | None = None
    aircraft_type: Literal["A320", "B738", "B77W", "B788", "A359", "A388"]
    profile: Literal["minimum_fuel", "minimum_time", "balanced"] = "balanced"
    departure_runway: str | None = Field(
        default=None, min_length=2, max_length=8
    )
    arrival_runway: str | None = Field(default=None, min_length=2, max_length=8)
    destination_alternate_icao: str | None = Field(
        default=None, min_length=3, max_length=8
    )
    extra_fuel_kg: float | None = Field(default=None, ge=0.0, le=100_000.0)
    contingency_percent: float | None = Field(
        default=None, ge=0.0, le=100.0
    )
    final_reserve_minutes: float | None = Field(
        default=None, ge=0.0, le=120.0
    )
    payload_mass_kg: float | None = Field(
        default=None, ge=0.0, le=100_000.0
    )


class TerminalSelection(BaseModel):
    departure_runway: str | None = None
    departure_runway_suggested: bool = False
    sid_identifier: str | None = None
    arrival_runway: str | None = None
    arrival_runway_suggested: bool = False
    star_identifier: str | None = None
    airac_cycle: str | None = None
    rationale: list[str] = Field(default_factory=list)


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


class FuelPlanResponse(BaseModel):
    policy_identifier: str
    taxi_fuel_kg: float
    trip_fuel_kg: float
    contingency_fuel_kg: float
    alternate_fuel_kg: float
    final_reserve_fuel_kg: float
    extra_fuel_kg: float
    block_fuel_kg: float
    takeoff_fuel_kg: float
    estimated_landing_fuel_kg: float
    estimated_alternate_arrival_fuel_kg: float
    ramp_mass_kg: float
    takeoff_mass_kg: float
    estimated_landing_mass_kg: float
    operationally_approved: bool = False
    mass_iterations: int = 1
    mass_converged: bool = False
    assumptions: list[str] = Field(default_factory=list)


class DestinationAlternate(BaseModel):
    icao_code: str
    name: str
    distance_from_destination_nm: float
    estimated_flight_time_minutes: float
    estimated_fuel_kg: float
    longest_published_runway_ft: float | None = None
    runway_compatible: bool
    selection: Literal["requested", "suggested"]
    navigation_source: str | None = None
    airac_cycle: str | None = None
    operationally_approved: bool = False
    rationale: list[str] = Field(default_factory=list)


class EnrouteDiversion(BaseModel):
    icao_code: str
    name: str
    distance_to_route_nm: float
    nearest_route_fraction: float
    longest_published_runway_ft: float | None = None
    runway_compatible: bool
    navigation_source: str | None = None
    airac_cycle: str | None = None
    operationally_approved: bool = False
    rationale: list[str] = Field(default_factory=list)


class RoutePoint(BaseModel):
    latitude_deg: float
    longitude_deg: float


class GeoJsonGeometry(BaseModel):
    type: Literal["LineString", "MultiLineString"]
    coordinates: list[list[float]] | list[list[list[float]]]


class WaypointDetail(BaseModel):
    node_id: str
    display_name: str = "Synthetic node"
    kind: Literal[
        "airport", "navigation_fix", "oceanic_coordinate", "synthetic"
    ] = "synthetic"
    latitude_deg: float
    longitude_deg: float
    flight_level: int
    elapsed_time_s: float
    cumulative_distance_m: float
    cumulative_fuel_kg: float
    estimated_mass_kg: float
    wind_component_kt: float | None = None
    navigation_source: str | None = None
    airac_cycle: str | None = None
    airac_region: str | None = None
    snap_distance_nm: float | None = None
    inbound_via: str | None = None
    airway_validated: bool | None = None
    procedure_type: Literal["SID", "STAR"] | None = None
    procedure_identifier: str | None = None
    runway: str | None = None


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
    terminal_selection: TerminalSelection | None = None
    fuel_plan: FuelPlanResponse | None = None
    destination_alternate: DestinationAlternate | None = None
    enroute_diversions: list[EnrouteDiversion] = Field(default_factory=list)


class OptimizationHistoryItem(BaseModel):
    run_id: str
    status: str
    origin_icao: str
    destination_icao: str
    aircraft_type: str
    profile: str
