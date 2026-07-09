from typing import Literal

from pydantic import BaseModel, Field


FplItem = Literal["7", "8", "9", "10", "13", "15", "16", "18", "19"]


class IcaoFplValidationRequest(BaseModel):
    aircraft_identification: str = Field(min_length=2, max_length=7)
    flight_rules: Literal["I", "V", "Y", "Z"] = "I"
    flight_type: Literal["S", "N", "G", "M", "X"] = "S"
    aircraft_type: str = Field(min_length=2, max_length=4)
    equipment: str = Field(default="SDE2E3FGHIJ1J5M1RWXY/LB1", min_length=1)
    departure_aerodrome: str = Field(min_length=4, max_length=4)
    departure_time_hhmm: str = Field(pattern="^[0-2][0-9][0-5][0-9]$")
    cruising_speed: str = Field(default="N0480", pattern="^[NK][0-9]{4}$")
    cruising_level: str = Field(default="F350", pattern="^[FA][0-9]{3}$")
    route: str = Field(min_length=1, max_length=1500)
    destination_aerodrome: str = Field(min_length=4, max_length=4)
    total_eet_hhmm: str = Field(pattern="^[0-9]{4}$")
    alternate_aerodrome: str | None = Field(
        default=None, min_length=4, max_length=4
    )
    other_information: str = Field(default="", max_length=1000)


class IcaoFplItemValidation(BaseModel):
    item: FplItem
    valid: bool
    blockers: list[str] = Field(default_factory=list)


class AircraftCapabilityProfile(BaseModel):
    aircraft_type: str
    capability_baseline: str
    operator_approval_status: Literal["missing", "accepted"] = "missing"
    allowed_equipment: list[str] = Field(default_factory=list)
    requested_equipment: list[str] = Field(default_factory=list)
    unsupported_equipment: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class IcaoFplValidationResponse(BaseModel):
    contract_version: str = "1.0.0"
    baseline: str = "icao-fpl-validation-2026-07-09"
    operational_use_enabled: bool = False
    filing_enabled: bool = False
    status: Literal["blocked", "invalid"]
    items: list[IcaoFplItemValidation]
    aircraft_capability: AircraftCapabilityProfile
