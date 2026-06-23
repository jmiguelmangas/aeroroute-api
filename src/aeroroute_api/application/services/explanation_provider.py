"""Provider preference with deterministic fallback on every MLX failure."""

from typing import Protocol

from aeroroute_api.application.dto.explanation import ExplanationResponse


class ExplanationProvider(Protocol):
    async def explain(
        self, summary: str, allowed_numeric_values: list[str]
    ) -> ExplanationResponse: ...


async def prefer_mlx_or_fallback(
    provider: ExplanationProvider | None,
    fallback: ExplanationResponse,
    allowed_numeric_values: list[str],
) -> ExplanationResponse:
    if provider is None:
        return fallback
    try:
        response = await provider.explain(fallback.text, allowed_numeric_values)
    except Exception:
        return fallback
    return response if response.provider == "mlx" else fallback
