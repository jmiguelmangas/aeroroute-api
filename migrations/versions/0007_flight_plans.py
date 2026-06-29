"""Persist immutable pre-operational flight-plan snapshots.

Revision ID: 0007_flight_plans
Revises: 0006_navigation_snapshots
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007_flight_plans"
down_revision = "0006_navigation_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "flight_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "optimization_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("input_json", postgresql.JSONB(), nullable=False),
        sa.Column("output_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["optimization_run_id"], ["optimization_runs.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_hash"),
    )
    op.create_index(
        "ix_flight_plans_created_at", "flight_plans", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_flight_plans_created_at", table_name="flight_plans")
    op.drop_table("flight_plans")
