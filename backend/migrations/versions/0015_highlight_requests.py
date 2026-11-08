"""Persistent items for every requested highlight, including unfulfilled results."""

from alembic import op
import sqlalchemy as sa

revision = "0015_highlight_requests"
down_revision = "0014_sources_searches_router"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "highlight_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "search_id", sa.String(36), sa.ForeignKey("proposal_searches.id", ondelete="SET NULL")
        ),
        sa.Column(
            "proposal_id",
            sa.String(36),
            sa.ForeignKey("highlight_proposals.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("job_id", sa.String(36)),
        sa.Column("reason", sa.String(2000), nullable=False),
        sa.Column("deleted", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "number"),
    )
    op.create_index("ix_highlight_requests_project_id", "highlight_requests", ["project_id"])
    from sqlalchemy.orm import Session
    from app.highlight_requests import backfill

    with Session(bind=op.get_bind()) as session:
        backfill(session)
        session.flush()


def downgrade():
    op.drop_table("highlight_requests")
