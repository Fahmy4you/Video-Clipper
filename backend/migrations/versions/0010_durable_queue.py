"""Durable queue and idempotent project submissions."""

from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("projects") as b:
        b.add_column(sa.Column("request_id", sa.String(100), nullable=True))
        b.add_column(sa.Column("request_hash", sa.String(64), nullable=True))
        b.create_unique_constraint("uq_project_request_id", ["request_id"])
    with op.batch_alter_table("jobs") as b:
        b.alter_column("project_id", existing_type=sa.String(36), nullable=True)
        b.add_column(sa.Column("library_id", sa.String(36), nullable=True))
        b.create_foreign_key(
            "fk_job_library", "video_clip", ["library_id"], ["id"], ondelete="SET NULL"
        )
        b.create_index("ix_jobs_library_id", ["library_id"])
        for name in ("queue_at", "next_attempt_at", "heartbeat_at"):
            b.add_column(sa.Column(name, sa.DateTime(timezone=True), nullable=True))
        b.add_column(sa.Column("owner_token", sa.String(36), nullable=True))
        b.add_column(sa.Column("wait_reason", sa.String(500), nullable=True))
        b.add_column(sa.Column("connection_label", sa.String(40), nullable=True))
        b.add_column(sa.Column("checkpoint", sa.JSON(), nullable=False, server_default="{}"))
    op.execute("UPDATE jobs SET queue_at=created_at")
    with op.batch_alter_table("jobs") as b:
        b.alter_column("queue_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        b.create_index("ix_jobs_queue_at", ["queue_at"])


def downgrade():
    conn = op.get_bind()
    if conn.scalar(sa.text("SELECT COUNT(*) FROM jobs WHERE project_id IS NULL")):
        raise RuntimeError("Library queue history must be handled before downgrade.")
    with op.batch_alter_table("jobs") as b:
        b.drop_constraint("fk_job_library", type_="foreignkey")
        b.drop_index("ix_jobs_library_id")
        b.drop_index("ix_jobs_queue_at")
        for name in (
            "library_id",
            "queue_at",
            "next_attempt_at",
            "heartbeat_at",
            "owner_token",
            "wait_reason",
            "connection_label",
            "checkpoint",
        ):
            b.drop_column(name)
        b.alter_column("project_id", existing_type=sa.String(36), nullable=False)
    with op.batch_alter_table("projects") as b:
        b.drop_constraint("uq_project_request_id", type_="unique")
        b.drop_column("request_id")
        b.drop_column("request_hash")
