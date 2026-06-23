"""PostGIS persistence models; route physics intentionally lives elsewhere."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DatasetSnapshot(Base):
    __tablename__ = "dataset_snapshots"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_name: Mapped[str] = mapped_column(String(100), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False)


class Airport(Base):
    __tablename__ = "airports"
    __table_args__ = (
        CheckConstraint(
            "latitude_deg BETWEEN -90 AND 90", name="airport_latitude_bounds"
        ),
        CheckConstraint(
            "longitude_deg BETWEEN -180 AND 180",
            name="airport_longitude_bounds",
        ),
        Index("ix_airports_location", "location", postgresql_using="gist"),
        Index("ix_airports_icao", "icao_code"),
        Index("ix_airports_iata", "iata_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("dataset_snapshots.id"),
        nullable=False,
    )
    icao_code: Mapped[str] = mapped_column(String(8), nullable=False)
    iata_code: Mapped[str | None] = mapped_column(String(3))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    municipality: Mapped[str | None] = mapped_column(String(255))
    iso_country: Mapped[str | None] = mapped_column(String(2))
    airport_type: Mapped[str] = mapped_column(String(32), nullable=False)
    latitude_deg: Mapped[float] = mapped_column(nullable=False)
    longitude_deg: Mapped[float] = mapped_column(nullable=False)
    elevation_ft: Mapped[int | None]
    location: Mapped[str] = mapped_column(
        Geometry("POINT", srid=4326), nullable=False
    )
