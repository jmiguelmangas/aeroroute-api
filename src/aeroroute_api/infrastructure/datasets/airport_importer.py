"""Local CSV import into the API-owned airport catalogue."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path

from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from aeroroute_api.infrastructure.db.models import Airport, DatasetSnapshot


@dataclass(frozen=True, slots=True)
class ImportSummary:
    snapshot_id: str
    accepted_rows: int
    rejected_rows: int
    already_imported: bool


async def import_airports_csv(
    session: AsyncSession, path: Path
) -> ImportSummary:
    checksum = _sha256(path)
    snapshot = await session.scalar(
        select(DatasetSnapshot).where(DatasetSnapshot.sha256 == checksum)
    )
    if snapshot is not None:
        return ImportSummary(
            snapshot_id=str(snapshot.id),
            accepted_rows=snapshot.accepted_rows,
            rejected_rows=snapshot.rejected_rows,
            already_imported=True,
        )

    valid_rows, rejected_rows = _parse_rows(path)
    snapshot = DatasetSnapshot(
        source_name="ourairports-csv",
        sha256=checksum,
        accepted_rows=len(valid_rows),
        rejected_rows=rejected_rows,
    )
    session.add(snapshot)
    await session.flush()
    session.add_all(
        [
            Airport(
                snapshot_id=snapshot.id,
                icao_code=row["ident"],
                iata_code=row["iata_code"],
                name=row["name"],
                municipality=row["municipality"],
                iso_country=row["iso_country"],
                airport_type=row["airport_type"],
                latitude_deg=row["latitude_deg"],
                longitude_deg=row["longitude_deg"],
                elevation_ft=row["elevation_ft"],
                location=WKTElement(
                    f"POINT({row['longitude_deg']} {row['latitude_deg']})",
                    srid=4326,
                ),
            )
            for row in valid_rows
        ]
    )
    await session.commit()
    return ImportSummary(
        snapshot_id=str(snapshot.id),
        accepted_rows=len(valid_rows),
        rejected_rows=rejected_rows,
        already_imported=False,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_rows(path: Path) -> tuple[list[dict[str, object]], int]:
    valid_rows: list[dict[str, object]] = []
    rejected_rows = 0
    with path.open(newline="", encoding="utf-8") as source:
        for raw in csv.DictReader(source):
            try:
                latitude = float(raw["latitude_deg"])
                longitude = float(raw["longitude_deg"])
                ident = raw["ident"].strip()
                name = raw["name"].strip()
                if (
                    not ident
                    or not name
                    or not -90 <= latitude <= 90
                    or not -180 <= longitude <= 180
                ):
                    raise ValueError("invalid airport row")
                elevation = raw.get("elevation_ft", "").strip()
                valid_rows.append(
                    {
                        "ident": ident,
                        "iata_code": _optional(raw.get("iata_code")),
                        "name": name,
                        "municipality": _optional(raw.get("municipality")),
                        "iso_country": _optional(raw.get("iso_country")),
                        "airport_type": raw.get("type", "").strip(),
                        "latitude_deg": latitude,
                        "longitude_deg": longitude,
                        "elevation_ft": int(elevation) if elevation else None,
                    }
                )
            except (KeyError, ValueError):
                rejected_rows += 1
    return valid_rows, rejected_rows


def _optional(value: str | None) -> str | None:
    normalized = (value or "").strip()
    return normalized or None
