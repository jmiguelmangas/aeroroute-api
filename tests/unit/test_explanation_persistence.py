from uuid import uuid4

import pytest

from aeroroute_api.application.dto.explanation import ExplanationResponse
from aeroroute_api.application.services.explanation import ExplanationFacts
from aeroroute_api.infrastructure.db.explanations import persist_explanation
from aeroroute_api.infrastructure.db.models import OptimizationExplanation


class _Session:
    def __init__(self) -> None:
        self.existing = None
        self.added: list[object] = []
        self.commits = 0

    async def scalar(self, _statement):
        return self.existing

    def add(self, value) -> None:
        self.existing = value
        self.added.append(value)

    async def commit(self) -> None:
        self.commits += 1


@pytest.mark.anyio
async def test_explanation_is_persisted_once_with_its_facts() -> None:
    session = _Session()
    run_id = uuid4()
    response = ExplanationResponse(
        provider="template", text="Stable explanation", warnings=[]
    )
    facts = ExplanationFacts(
        "EGLL", "OMDB", "minimum_fuel", 5_000_000, 20_000, 15_000
    )

    first = await persist_explanation(  # type: ignore[arg-type]
        session, run_id, response, facts
    )
    second = await persist_explanation(  # type: ignore[arg-type]
        session, run_id, response, facts
    )

    assert isinstance(first, OptimizationExplanation)
    assert second is first
    assert first.facts_json["origin_icao"] == "EGLL"
    assert session.commits == 1
    assert len(session.added) == 1
