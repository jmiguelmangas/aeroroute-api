from aeroroute_api.application.services.explanation import (
    ExplanationFacts,
    render_deterministic_explanation,
)


def test_deterministic_explanation_uses_only_fact_values_and_disclaimer() -> (
    None
):
    response = render_deterministic_explanation(
        ExplanationFacts(
            "LEMD", "KJFK", "minimum_fuel", 5_000_000, 24_000, 18_000
        )
    )

    assert response.provider == "template"
    assert "5000 km" in response.text
    assert "400 minutes" in response.text
    assert "18000 kg of modeled trip fuel" in response.text
    assert "not operational flight-planning advice" in response.text


def test_degraded_data_is_exposed_as_a_structured_warning() -> None:
    response = render_deterministic_explanation(
        ExplanationFacts(
            "LEMD", "KJFK", "balanced", 1, 1, 1, data_degraded=True
        )
    )

    assert response.warnings == ["weather_data_degraded"]


def test_negative_deltas_are_worded_as_savings() -> None:
    response = render_deterministic_explanation(
        ExplanationFacts(
            "EGLL",
            "OMDB",
            "minimum_fuel",
            5_000_000,
            20_400,
            15_000,
            baseline_time_s=21_000,
            baseline_fuel_kg=15_500,
        )
    )

    assert "saves 500 kg" in response.text
    assert "saves 10 minutes" in response.text


def test_positive_and_negligible_deltas_are_stable() -> None:
    response = render_deterministic_explanation(
        ExplanationFacts(
            "EGLL",
            "OMDB",
            "balanced",
            5_000_000,
            20_400,
            15_000.2,
            baseline_time_s=20_100,
            baseline_fuel_kg=15_000,
        )
    )

    assert "negligible difference in kg" in response.text
    assert "uses 5 more minutes" in response.text
