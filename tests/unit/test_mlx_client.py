import httpx
import pytest

from aeroroute_api.infrastructure.explanations.mlx_client import (
    MlxExplanationClient,
    MlxUnavailable,
)


@pytest.mark.anyio
async def test_mlx_client_accepts_valid_contract_response() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "contract_version": "1.0.0",
                    "provider": "mlx",
                    "text": "Validated explanation.",
                    "fallback_used": False,
                },
            )
        )
    ) as client:
        result = await MlxExplanationClient(client, "http://mlx").explain(
            "summary", []
        )

    assert result.provider == "mlx"


@pytest.mark.anyio
async def test_mlx_client_rejects_invalid_contract_response() -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    ) as client:
        with pytest.raises(MlxUnavailable):
            await MlxExplanationClient(client, "http://mlx").explain(
                "summary", []
            )
