"""Store the complete versioned optimization response snapshot.

Revision ID: 0003_run_output_snapshot
Revises: 0002_optimization_runs
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_run_output_snapshot"
down_revision = "0002_optimization_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "optimization_runs",
        sa.Column("output_json", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("optimization_runs", "output_json")
