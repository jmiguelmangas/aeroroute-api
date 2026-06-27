"""Deterministic explanations based solely on persisted optimization facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from aeroroute_api.application.dto.explanation import ExplanationResponse
from aeroroute_api.application.dto.optimization import OptimizationResponse


@dataclass(frozen=True, slots=True)
class ExplanationFacts:
    origin_icao: str
    destination_icao: str
    profile: str
    distance_m: float
    time_s: float
    fuel_kg: float
    data_degraded: bool = False
    baseline_time_s: float | None = None
    baseline_fuel_kg: float | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def explanation_facts_from_result(
    result: OptimizationResponse,
) -> ExplanationFacts:
    if result.request is None or result.winner is None:
        raise ValueError("completed result lacks explanation facts")
    degraded_codes = {
        "WEATHER_FALLBACK",
        "WEATHER_STALE",
        "WEATHER_STILL_AIR",
        "FUEL_NOT_CONVERGED",
    }
    return ExplanationFacts(
        origin_icao=result.request.origin_icao,
        destination_icao=result.request.destination_icao,
        profile=result.request.profile,
        distance_m=result.winner.distance_m,
        time_s=result.winner.time_s,
        fuel_kg=result.winner.fuel_kg,
        data_degraded=any(
            flag.code in degraded_codes for flag in result.data_quality
        ),
        baseline_time_s=(result.baseline.time_s if result.baseline else None),
        baseline_fuel_kg=(result.baseline.fuel_kg if result.baseline else None),
    )


def render_deterministic_explanation(
    facts: ExplanationFacts,
) -> ExplanationResponse:
    distance_km = facts.distance_m / 1_000
    time_minutes = facts.time_s / 60
    comparison = _comparison_text(facts)
    text = (
        f"For the {facts.profile} profile, the selected synthetic trajectory "
        f"from {facts.origin_icao} to {facts.destination_icao} covers "
        f"{distance_km:.0f} km, takes an estimated {time_minutes:.0f} minutes, "
        f"and uses {facts.fuel_kg:.0f} kg of modeled trip fuel. {comparison}"
        "This is an educational trajectory-efficiency estimate, not "
        "operational flight-planning advice."
    )
    warnings = ["weather_data_degraded"] if facts.data_degraded else []
    return ExplanationResponse(
        provider="template", text=text, warnings=warnings
    )


def allowed_numeric_values(facts: ExplanationFacts) -> list[str]:
    values = {
        f"{facts.distance_m / 1_000:.0f}",
        f"{facts.time_s / 60:.0f}",
        f"{facts.fuel_kg:.0f}",
    }
    if facts.baseline_time_s is not None:
        values.add(f"{abs(facts.time_s - facts.baseline_time_s) / 60:.0f}")
    if facts.baseline_fuel_kg is not None:
        values.add(f"{abs(facts.fuel_kg - facts.baseline_fuel_kg):.0f}")
    return sorted(values)


def _comparison_text(facts: ExplanationFacts) -> str:
    if facts.baseline_fuel_kg is None or facts.baseline_time_s is None:
        return ""
    fuel_delta = facts.fuel_kg - facts.baseline_fuel_kg
    time_delta_minutes = (facts.time_s - facts.baseline_time_s) / 60
    fuel_text = _delta_text(fuel_delta, "kg of modeled trip fuel")
    time_text = _delta_text(time_delta_minutes, "minutes")
    return f"Compared with the baseline, it {fuel_text} and {time_text}. "


def _delta_text(delta: float, unit: str) -> str:
    rounded = abs(delta)
    if rounded < 0.5:
        return f"has a negligible difference in {unit}"
    if delta < 0:
        return f"saves {rounded:.0f} {unit}"
    return f"uses {rounded:.0f} more {unit}"
