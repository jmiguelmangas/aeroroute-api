"""Provider preference with deterministic fallback on every MLX failure."""

from typing import Protocol

from aeroroute_api.application.dto.explanation import ExplanationResponse


class ExplanationProvider(Protocol):
    async def explain(
        self, summary: str, allowed_numeric_values: list[str]
    ) -> ExplanationResponse: ...


# Module-level counters (mirrors the `_cache_hits`/`_cache_misses` counter
# style in infrastructure/navigation/airac.py's AiracNavigationClient) so
# the MLX-fallback-rate metric named in HLD SS20.2 survives across requests
# without needing a request-scoped object threaded through the call site.
_mlx_used = 0
_fallback_used = 0


def explanation_provider_health() -> dict[str, object]:
    total = _mlx_used + _fallback_used
    return {
        "mlx_used": _mlx_used,
        "fallback_used": _fallback_used,
        "fallback_rate": (_fallback_used / total) if total else None,
    }


async def prefer_mlx_or_fallback(
    provider: ExplanationProvider | None,
    fallback: ExplanationResponse,
    allowed_numeric_values: list[str],
) -> ExplanationResponse:
    global _mlx_used, _fallback_used
    if provider is None:
        _fallback_used += 1
        return fallback
    try:
        response = await provider.explain(fallback.text, allowed_numeric_values)
    except Exception:
        _fallback_used += 1
        return fallback
    if response.provider == "mlx":
        _mlx_used += 1
        return response
    _fallback_used += 1
    return fallback
