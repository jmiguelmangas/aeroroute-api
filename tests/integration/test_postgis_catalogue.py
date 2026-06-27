from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from aeroroute_api.infrastructure.datasets.airport_importer import (
    import_airports_csv,
)
from aeroroute_api.infrastructure.db.models import Airport

ASYNC_URL = os.getenv("AEROROUTE_TEST_DATABASE_URL")
SYNC_URL = os.getenv("AEROROUTE_TEST_DATABASE_SYNC_URL")

pytestmark = pytest.mark.skipif(
    not ASYNC_URL or not SYNC_URL,
    reason="PostGIS integration URLs are not configured",
)


def migrate(revision: str) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", SYNC_URL or "")
    command.upgrade(
        config, revision
    ) if revision != "base" else command.downgrade(config, revision)


@pytest.mark.anyio
async def test_migrations_import_and_spatial_coordinate_order(
    tmp_path: Path,
) -> None:
    migrate("base")
    migrate("head")
    engine = create_async_engine(ASYNC_URL or "")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    csv_path = tmp_path / "airports.csv"
    csv_path.write_text(
        "ident,type,name,latitude_deg,longitude_deg,elevation_ft,"
        "iso_country,municipality,iata_code\n"
        "LEMD,large_airport,Adolfo Suarez Madrid-Barajas,40.4719,"
        "-3.5626,1998,ES,Madrid,MAD\n"
    )

    try:
        async with session_factory() as session:
            first = await import_airports_csv(session, csv_path)
            second = await import_airports_csv(session, csv_path)
            row = (
                await session.execute(
                    select(
                        Airport.icao_code,
                        func.ST_X(Airport.location),
                        func.ST_Y(Airport.location),
                    ).where(Airport.icao_code == "LEMD")
                )
            ).one()

        assert first.accepted_rows == 1
        assert first.rejected_rows == 0
        assert not first.already_imported
        assert second.already_imported
        assert row[0] == "LEMD"
        assert row[1] == pytest.approx(-3.5626)
        assert row[2] == pytest.approx(40.4719)
    finally:
        await engine.dispose()
        migrate("base")

    verification_engine = create_async_engine(ASYNC_URL or "")
    try:
        async with verification_engine.connect() as connection:
            relation = await connection.scalar(
                text("SELECT to_regclass('public.airports')")
            )
        assert relation is None
    finally:
        await verification_engine.dispose()
