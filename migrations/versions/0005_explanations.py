"""Persist one versioned explanation per optimization run.

Revision ID: 0005_explanations
Revises: 0004_run_lifecycle
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_explanations"
down_revision = "0004_run_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "optimization_explanations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("warnings_json", postgresql.JSONB(), nullable=False),
        sa.Column("facts_json", postgresql.JSONB(), nullable=False),
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
    op.drop_table("optimization_explanations")
