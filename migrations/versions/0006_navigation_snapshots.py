"""Persist immutable AIRAC navigation snapshots per optimization run.

Revision ID: 0006_navigation_snapshots
Revises: 0005_explanations
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_navigation_snapshots"
down_revision = "0005_explanations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "navigation_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("airac_cycle", sa.String(length=64), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["optimization_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("navigation_snapshots")
