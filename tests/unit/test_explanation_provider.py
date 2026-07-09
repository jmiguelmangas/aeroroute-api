import pytest

from aeroroute_api.application.dto.explanation import ExplanationResponse
from aeroroute_api.application.services.explanation_provider import (
    explanation_provider_health,
    prefer_mlx_or_fallback,
)


class _Provider:
    def __init__(
        self,
        response: ExplanationResponse | None = None,
        raises: bool = False,
    ) -> None:
        self._response = response
        self._raises = raises

    async def explain(
        self, summary: str, allowed_numeric_values: list[str]
    ) -> ExplanationResponse:
        if self._raises:
            raise RuntimeError("mlx unavailable")
        assert self._response is not None
        return self._response


@pytest.mark.anyio
async def test_prefer_mlx_or_fallback_counts_mlx_and_fallback_outcomes() -> (
    None
):
    fallback = ExplanationResponse(
        provider="template", text="fallback", warnings=[]
    )
    mlx_response = ExplanationResponse(
        provider="mlx", text="mlx text", warnings=[]
    )
    non_mlx_response = ExplanationResponse(
        provider="template", text="not mlx", warnings=[]
    )
    before = explanation_provider_health()

    # Real MLX output is used and counted as such.
    result = await prefer_mlx_or_fallback(_Provider(mlx_response), fallback, [])
    assert result.provider == "mlx"

    # Provider failure falls back and is counted as a fallback.
    result = await prefer_mlx_or_fallback(_Provider(raises=True), fallback, [])
    assert result is fallback

    # A non-MLX-tagged response is treated as a fallback too.
    result = await prefer_mlx_or_fallback(
        _Provider(non_mlx_response), fallback, []
    )
    assert result is fallback

    # No provider configured falls back.
    result = await prefer_mlx_or_fallback(None, fallback, [])
    assert result is fallback

    after = explanation_provider_health()
    assert after["mlx_used"] == before["mlx_used"] + 1
    assert after["fallback_used"] == before["fallback_used"] + 3
