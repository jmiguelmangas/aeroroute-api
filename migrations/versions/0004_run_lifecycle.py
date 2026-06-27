"""Add explicit optimization run lifecycle metadata.

Revision ID: 0004_run_lifecycle
Revises: 0003_run_output_snapshot
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_run_lifecycle"
down_revision = "0003_run_output_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "optimization_runs",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "optimization_runs",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "optimization_runs",
        sa.Column("error_code", sa.String(length=64), nullable=True),
    )
    op.execute(
        "UPDATE optimization_runs "
        "SET status = 'completed', completed_at = created_at "
        "WHERE output_json IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("optimization_runs", "error_code")
    op.drop_column("optimization_runs", "completed_at")
    op.drop_column("optimization_runs", "updated_at")
