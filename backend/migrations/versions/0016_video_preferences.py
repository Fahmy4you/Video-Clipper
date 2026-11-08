"""Workspace video style defaults."""

from alembic import op
import sqlalchemy as sa

revision = "0016_video_preferences"
down_revision = "0015_highlight_requests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "video_preferences",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("video_preferences")
