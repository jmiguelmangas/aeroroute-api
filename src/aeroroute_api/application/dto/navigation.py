from typing import Literal

from pydantic import BaseModel, Field


class RunwayOption(BaseModel):
    identifier: str
    bearing_deg: float
    length_ft: float
    width_ft: float | None = None
    surface: str | None = None
    compatible_procedures: int = 0
    suggested: bool = False
    headwind_component_kt: float | None = None
    crosswind_component_kt: float | None = None


class RunwayOptionsResponse(BaseModel):
    airport_icao: str
    procedure_type: Literal["SID", "STAR"]
    items: list[RunwayOption]
    suggested_runway: str | None = None
    airac_cycle: str | None = None
    recommendation_basis: list[str] = Field(default_factory=list)
    surface_wind_speed_kt: float | None = None
    surface_wind_direction_deg: float | None = None
    surface_wind_source: str | None = None


class ProcedureOption(BaseModel):
    identifier: str
    procedure_type: Literal["SID", "STAR"]
    runway_family: str
    entry_fix: str
    exit_fix: str
    point_count: int
    airac_cycle: str | None = None


class ProcedureOptionsResponse(BaseModel):
    airport_icao: str
    procedure_type: Literal["SID", "STAR"]
    runway: str | None = None
    items: list[ProcedureOption]


class RouteSupportAirportCoverage(BaseModel):
    airport_icao: str
    procedure_type: Literal["SID", "STAR"]
    runway_available: bool
    procedure_available: bool
    suggested_runway: str | None = None
    compatible_procedure_count: int = 0
    airac_cycle: str | None = None


class RouteSupportProblem(BaseModel):
    code: Literal[
        "airport_not_supported",
        "navigation_provider_unavailable",
        "runway_procedure_coverage_missing",
    ]
    message: str
    airport_icao: str | None = None


class RouteSupportResponse(BaseModel):
    origin_icao: str
    destination_icao: str
    supported: bool
    status: Literal["supported", "unsupported", "unavailable"]
    airac_cycle: str | None = None
    navigation_manifest: dict[str, object]
    airports: list[RouteSupportAirportCoverage] = Field(default_factory=list)
    problems: list[RouteSupportProblem] = Field(default_factory=list)
