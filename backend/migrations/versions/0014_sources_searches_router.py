"""Shared sources, repeat proposal searches and 9Router selection."""

from alembic import op
import sqlalchemy as sa

revision = "0014_sources_searches_router"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "media_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("youtube_id", sa.String(11), nullable=False, unique=True),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.add_column(
        "projects",
        sa.Column("source_id", sa.String(36), sa.ForeignKey("media_sources.id"), nullable=True),
    )
    op.add_column("projects", sa.Column("ai_combo", sa.String(200), nullable=True))
    op.create_index("ix_projects_source_id", "projects", ["source_id"])
    op.create_table(
        "proposal_searches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_id", sa.String(36), unique=True, nullable=False),
        sa.Column("combo", sa.String(200), nullable=False),
        sa.Column("prompt", sa.String(4000), nullable=False),
        sa.Column("count", sa.Integer, nullable=False),
        sa.Column("avoid_used", sa.Boolean, nullable=False),
        sa.Column("exclusions", sa.JSON, nullable=False),
        sa.Column("job_id", sa.String(36)),
        sa.Column("completed", sa.Boolean, nullable=False),
        sa.Column("report", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_proposal_searches_project_id", "proposal_searches", ["project_id"])
    op.add_column(
        "highlight_proposals",
        sa.Column(
            "search_id", sa.String(36), sa.ForeignKey("proposal_searches.id", ondelete="SET NULL")
        ),
    )
    op.create_index("ix_highlight_proposals_search_id", "highlight_proposals", ["search_id"])
    # Existing media and transcripts remain in place and are registered lazily.


def downgrade():
    op.drop_column("highlight_proposals", "search_id")
    op.drop_table("proposal_searches")
    op.drop_column("projects", "source_id")
    op.drop_column("projects", "ai_combo")
    op.drop_table("media_sources")
