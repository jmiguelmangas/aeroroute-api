"""HTTP adapter for the optional native MLX explanation service."""

from __future__ import annotations

import httpx

from aeroroute_api.application.dto.explanation import ExplanationResponse


class MlxUnavailable(RuntimeError):
    pass


class MlxExplanationClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")

    async def explain(
        self, summary: str, allowed_numeric_values: list[str]
    ) -> ExplanationResponse:
        try:
            response = await self._client.post(
                f"{self._base_url}/v1/explanations",
                json={
                    "contract_version": "1.0.0",
                    "summary": summary,
                    "allowed_numeric_values": allowed_numeric_values,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if (
                payload.get("contract_version") != "1.0.0"
                or payload.get("provider") not in {"template", "mlx"}
                or not isinstance(payload.get("text"), str)
            ):
                raise MlxUnavailable(
                    "MLX response violates explanation contract"
                )
            return ExplanationResponse(
                provider=payload["provider"], text=payload["text"], warnings=[]
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise MlxUnavailable(
                "MLX explanation service is unavailable"
            ) from error
