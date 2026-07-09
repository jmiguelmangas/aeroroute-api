"""HTTP adapter for the optional native MLX explanation service."""

from __future__ import annotations

import re

import httpx

from aeroroute_api.application.dto.explanation import ExplanationResponse


class MlxUnavailable(RuntimeError):
    pass


# Duplicated (not imported) from
# aeroroute-mlx/src/aeroroute_mlx/validator.py's validate_numeric_claims and
# validate_operational_claims. aeroroute-mlx already validates its own output
# once, but per HLD SS5.1 "MLX output is untrusted text and must pass
# validation before display" -- aeroroute-mlx is a separate network service
# the API does not fully trust, so the same lightweight checks are repeated
# independently here. aeroroute-api must not take aeroroute-mlx as a runtime
# dependency, hence the duplication instead of an import.
_NUMERIC_TOKEN = re.compile(r"[-+]?\d+(?:[.,]\d+)?%?")
_BANNED_OPERATIONAL_CLAIMS = (
    "atc clearance",
    "atc-compliant",
    "cleared for",
    "dispatchable",
    "guarantees safety",
    "operational flight plan",
    "safe route",
)


def _validate_numeric_claims(text: str, allowed_values: list[str]) -> bool:
    allowed = {_normalize(value) for value in allowed_values}
    return all(
        _normalize(token) in allowed for token in _NUMERIC_TOKEN.findall(text)
    )


def _validate_operational_claims(text: str) -> bool:
    normalized = text.casefold()
    return not any(claim in normalized for claim in _BANNED_OPERATIONAL_CLAIMS)


def _normalize(value: str) -> str:
    return value.strip().replace(",", ".").removesuffix(".0")


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
            text = payload["text"]
            if not _validate_numeric_claims(
                text, allowed_numeric_values
            ) or not _validate_operational_claims(text):
                raise MlxUnavailable(
                    "MLX response failed independent API-side validation"
                )
            return ExplanationResponse(
                provider=payload["provider"], text=text, warnings=[]
            )
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise MlxUnavailable(
                "MLX explanation service is unavailable"
            ) from error
