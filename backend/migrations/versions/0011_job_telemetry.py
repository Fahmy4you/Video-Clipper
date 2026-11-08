"""Job phase timings and resource diagnostics."""

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("jobs", sa.Column("telemetry", sa.JSON(), nullable=False, server_default="{}"))


def downgrade():
    op.drop_column("jobs", "telemetry")
