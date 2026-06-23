"""Create persisted optimization runs and candidates.

Revision ID: 0002_optimization_runs
Revises: 0001_airport_catalogue
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0002_optimization_runs"
down_revision = "0001_airport_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("input_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_hash"),
    )
    op.create_table(
        "trajectory_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("path_json", postgresql.JSONB(), nullable=False),
        sa.Column("distance_m", sa.Float(), nullable=False),
        sa.Column("time_s", sa.Float(), nullable=False),
        sa.Column("fuel_kg", sa.Float(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["optimization_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trajectory_candidates_run_rank",
        "trajectory_candidates",
        ["run_id", "rank"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trajectory_candidates_run_rank", table_name="trajectory_candidates"
    )
    op.drop_table("trajectory_candidates")
    op.drop_table("optimization_runs")
