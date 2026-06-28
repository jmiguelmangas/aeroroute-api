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
