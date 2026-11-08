"""Institution ownership and collaboration sources; preserve existing media."""

from alembic import op
import sqlalchemy as sa
from uuid import uuid5, NAMESPACE_URL

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instansi",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("name_key", sa.String(300), nullable=False, unique=True),
    )
    op.create_table(
        "project_instansi",
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "instansi_id",
            sa.String(36),
            sa.ForeignKey("instansi.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("ix_project_instansi_instansi_id", "project_instansi", ["instansi_id"])
    op.add_column(
        "projects",
        sa.Column("include_global", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "video_clip", sa.Column("scope", sa.String(16), nullable=False, server_default="global")
    )
    op.add_column("video_clip", sa.Column("instansi_id", sa.String(36), nullable=True))
    with op.batch_alter_table("video_clip") as batch:
        batch.create_foreign_key(
            "fk_video_clip_instansi", "instansi", ["instansi_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_check_constraint(
            "ck_video_clip_scope",
            "(scope='global' AND instansi_id IS NULL) OR (scope='instansi' AND instansi_id IS NOT NULL)",
        )
        batch.create_index("ix_video_clip_instansi_id", ["instansi_id"])
    c = op.get_bind()
    crypto = str(uuid5(NAMESPACE_URL, "video-clipping:instansi:cryptowave"))
    akademi = str(uuid5(NAMESPACE_URL, "video-clipping:instansi:akademi-crypto"))
    table = sa.table("instansi", sa.column("id"), sa.column("name"), sa.column("name_key"))
    c.execute(
        table.insert(),
        [
            {"id": crypto, "name": "Cryptowave", "name_key": "cryptowave"},
            {"id": akademi, "name": "Akademi Crypto", "name_key": "akademi crypto"},
        ],
    )
    c.execute(
        sa.text(
            "UPDATE video_clip SET scope='instansi',instansi_id=CASE WHEN id=:exception THEN :akademi ELSE :crypto END"
        ),
        {"exception": "80ec4727-788a-54c5-9f33-ed897f837066", "akademi": akademi, "crypto": crypto},
    )
    c.execute(sa.text("UPDATE projects SET include_global=false WHERE visual_mode='mix'"))
    c.execute(
        sa.text(
            "INSERT INTO project_instansi(project_id,instansi_id) SELECT id,:id FROM projects WHERE visual_mode='mix'"
        ),
        {"id": crypto},
    )
    c.execute(
        sa.text(
            "INSERT INTO project_instansi(project_id,instansi_id) SELECT id,:id FROM projects WHERE visual_mode='mix'"
        ),
        {"id": akademi},
    )


def downgrade():
    with op.batch_alter_table("video_clip") as batch:
        batch.drop_index("ix_video_clip_instansi_id")
        batch.drop_constraint("ck_video_clip_scope", type_="check")
        batch.drop_constraint("fk_video_clip_instansi", type_="foreignkey")
        batch.drop_column("instansi_id")
        batch.drop_column("scope")
    op.drop_column("projects", "include_global")
    op.drop_table("project_instansi")
    op.drop_table("instansi")
