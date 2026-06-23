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
    assert "18000 kg" in response.text
    assert "not operational flight-planning advice" in response.text


def test_degraded_data_is_exposed_as_a_structured_warning() -> None:
    response = render_deterministic_explanation(
        ExplanationFacts(
            "LEMD", "KJFK", "balanced", 1, 1, 1, data_degraded=True
        )
    )

    assert response.warnings == ["weather_data_degraded"]
