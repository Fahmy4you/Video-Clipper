"""Allow one video to belong to multiple institutions without changing media."""

from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instasi_to_video_clips",
        sa.Column(
            "video_clip_id",
            sa.String(36),
            sa.ForeignKey("video_clip.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "instansi_id",
            sa.String(36),
            sa.ForeignKey("instansi.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_instasi_to_video_clips_instansi_id", "instasi_to_video_clips", ["instansi_id"]
    )
    op.execute(
        "INSERT INTO instasi_to_video_clips(video_clip_id,instansi_id) SELECT id,instansi_id FROM video_clip WHERE instansi_id IS NOT NULL"
    )
    with op.batch_alter_table("video_clip") as batch:
        batch.drop_constraint("ck_video_clip_scope", type_="check")
        batch.drop_constraint("fk_video_clip_instansi", type_="foreignkey")
        batch.drop_index("ix_video_clip_instansi_id")
        batch.drop_column("instansi_id")
        batch.create_check_constraint("ck_video_clip_scope", "scope IN ('global','instansi')")


def downgrade():
    c = op.get_bind()
    if c.execute(
        sa.text(
            "SELECT video_clip_id FROM instasi_to_video_clips GROUP BY video_clip_id HAVING COUNT(*)>1 LIMIT 1"
        )
    ).first():
        raise RuntimeError(
            "Tidak dapat downgrade: ada video dengan beberapa instansi. Kurangi relasi secara eksplisit terlebih dahulu."
        )
    op.add_column("video_clip", sa.Column("instansi_id", sa.String(36), nullable=True))
    op.execute(
        "UPDATE video_clip SET instansi_id=(SELECT p.instansi_id FROM instasi_to_video_clips p WHERE p.video_clip_id=video_clip.id)"
    )
    with op.batch_alter_table("video_clip") as batch:
        batch.drop_constraint("ck_video_clip_scope", type_="check")
        batch.create_foreign_key(
            "fk_video_clip_instansi", "instansi", ["instansi_id"], ["id"], ondelete="RESTRICT"
        )
        batch.create_index("ix_video_clip_instansi_id", ["instansi_id"])
        batch.create_check_constraint(
            "ck_video_clip_scope",
            "(scope='global' AND instansi_id IS NULL) OR (scope='instansi' AND instansi_id IS NOT NULL)",
        )
    op.drop_table("instasi_to_video_clips")
