import pytest

from aeroroute_api.api.routers.airports import search_airports


class _Scalars:
    def all(self):
        return []


class _Session:
    def __init__(self) -> None:
        self.statement = None

    async def scalars(self, statement):
        self.statement = statement
        return _Scalars()


@pytest.mark.anyio
async def test_search_treats_sql_wildcards_as_literal_text() -> None:
    session = _Session()

    result = await search_airports(
        query=r"%_'; DROP TABLE airports; --",
        limit=20,
        offset=0,
        session=session,  # type: ignore[arg-type]
    )

    assert result.items == []
    assert session.statement is not None
    parameters = session.statement.compile().params
    assert not any("DROP TABLE" in str(value) for value in parameters.values())
