"""Deterministic explanation fallback based solely on supplied facts."""

from dataclasses import dataclass

from aeroroute_api.application.dto.explanation import ExplanationResponse


@dataclass(frozen=True, slots=True)
class ExplanationFacts:
    origin_icao: str
    destination_icao: str
    profile: str
    distance_m: float
    time_s: float
    fuel_kg: float
    data_degraded: bool = False


def render_deterministic_explanation(
    facts: ExplanationFacts,
) -> ExplanationResponse:
    distance_km = facts.distance_m / 1_000
    time_minutes = facts.time_s / 60
    text = (
        f"For the {facts.profile} profile, the selected synthetic trajectory from "
        f"{facts.origin_icao} to {facts.destination_icao} covers {distance_km:.0f} km, "
        f"takes an estimated {time_minutes:.0f} minutes, and uses an estimated "
        f"{facts.fuel_kg:.0f} kg of cruise fuel. "
        "This is an educational trajectory-efficiency estimate, not operational "
        "flight-planning advice."
    )
    warnings = ["weather_data_degraded"] if facts.data_degraded else []
    return ExplanationResponse(
        provider="template", text=text, warnings=warnings
    )
