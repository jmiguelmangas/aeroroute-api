from typing import Literal

from pydantic import BaseModel, Field


DataSourceDomain = Literal[
    "navdata",
    "weather",
    "notam",
    "airspace_restrictions",
    "airport_status",
    "terrain_obstacle",
    "aircraft_performance",
    "filing",
]
DataSourceStatus = Literal[
    "missing", "demo_only", "candidate", "expired", "operational"
]
FallbackBehavior = Literal[
    "block_operational_use", "degrade_simulator_only", "not_available"
]


class OperationalDataSourceLicense(BaseModel):
    terms: str
    approved_for_operational_use: bool
    redistribution_allowed: bool


class OperationalDataSourceQuality(BaseModel):
    grade: Literal[
        "unknown", "demo", "public_reference", "candidate", "operational"
    ]
    validation_status: Literal["not_validated", "partial", "validated"]
    validated_at: str | None = None


class OperationalDataSource(BaseModel):
    contract_version: str = "1.0.0"
    domain: DataSourceDomain
    source: str
    status: DataSourceStatus
    version_or_cycle: str | None = None
    timestamp: str | None = None
    expires_at: str | None = None
    license: OperationalDataSourceLicense
    quality: OperationalDataSourceQuality
    fallback_behavior: FallbackBehavior
    operational_ready: bool
    blockers: list[str] = Field(default_factory=list)


class OperationalDataSourcesResponse(BaseModel):
    active_mode: Literal["simulator"]
    requested_mode: Literal[
        "simulator", "ops_candidate", "approved_operator_build"
    ]
    operational_use_enabled: bool
    data_contract_version: str = "1.0.0"
    data_baseline: str = "operational-data-sources-2026-07-09"
    status: Literal["simulator_only", "blocked"]
    sources: list[OperationalDataSource]
    blocking_domains: list[DataSourceDomain] = Field(default_factory=list)
