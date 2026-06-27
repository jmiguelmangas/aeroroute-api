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
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID
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


class OptimizationRun(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    request_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    input_json: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TrajectoryCandidate(Base):
    __tablename__ = "trajectory_candidates"
    __table_args__ = (
        Index("ix_trajectory_candidates_run_rank", "run_id", "rank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(
        PostgresUUID(as_uuid=True),
        ForeignKey("optimization_runs.id"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    path_json: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    distance_m: Mapped[float] = mapped_column(nullable=False)
    time_s: Mapped[float] = mapped_column(nullable=False)
    fuel_kg: Mapped[float] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(nullable=False)
