"""Create dataset snapshots and PostGIS airport catalogue.

Revision ID: 0001_airport_catalogue
Revises:
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0001_airport_catalogue"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "dataset_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("accepted_rows", sa.Integer(), nullable=False),
        sa.Column("rejected_rows", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256"),
    )
    op.create_table(
        "airports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("icao_code", sa.String(length=8), nullable=False),
        sa.Column("iata_code", sa.String(length=3)),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("municipality", sa.String(length=255)),
        sa.Column("iso_country", sa.String(length=2)),
        sa.Column("airport_type", sa.String(length=32), nullable=False),
        sa.Column("latitude_deg", sa.Float(), nullable=False),
        sa.Column("longitude_deg", sa.Float(), nullable=False),
        sa.Column("elevation_ft", sa.Integer()),
        sa.Column("location", Geometry("POINT", srid=4326), nullable=False),
        sa.CheckConstraint(
            "latitude_deg BETWEEN -90 AND 90", name="airport_latitude_bounds"
        ),
        sa.CheckConstraint(
            "longitude_deg BETWEEN -180 AND 180",
            name="airport_longitude_bounds",
        ),
        sa.ForeignKeyConstraint(["snapshot_id"], ["dataset_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_airports_location",
        "airports",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index("ix_airports_icao", "airports", ["icao_code"])
    op.create_index("ix_airports_iata", "airports", ["iata_code"])


def downgrade() -> None:
    op.drop_index("ix_airports_iata", table_name="airports")
    op.drop_index("ix_airports_icao", table_name="airports")
    op.drop_index("ix_airports_location", table_name="airports")
    op.drop_table("airports")
    op.drop_table("dataset_snapshots")
