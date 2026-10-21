"""Reusable hashtags and footage many-to-many associations."""
from alembic import op
import sqlalchemy as sa
from uuid import uuid4
revision='0006'
down_revision='0005'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('hashtags',sa.Column('id',sa.String(36),primary_key=True),sa.Column('name_tag',sa.String(50),nullable=False,unique=True))
    op.create_table('video_clip_hashtags',sa.Column('video_clip_id',sa.String(36),sa.ForeignKey('video_clip.id',ondelete='CASCADE'),primary_key=True),sa.Column('hashtag_id',sa.String(36),sa.ForeignKey('hashtags.id',ondelete='CASCADE'),primary_key=True))
    op.create_index('ix_video_clip_hashtags_hashtag_id','video_clip_hashtags',['hashtag_id'])
    conn=op.get_bind();tags=sa.table('hashtags',sa.column('id',sa.String),sa.column('name_tag',sa.String));pivot=sa.table('video_clip_hashtags',sa.column('video_clip_id',sa.String),sa.column('hashtag_id',sa.String));old=sa.table('video_clip',sa.column('id',sa.String),sa.column('hashtags',sa.JSON));ids={}
    for row in conn.execute(sa.select(old.c.id,old.c.hashtags)):
        for name in dict.fromkeys(row.hashtags or []):
            if name not in ids:
                ids[name]=str(uuid4());conn.execute(tags.insert().values(id=ids[name],name_tag=name))
            conn.execute(pivot.insert().values(video_clip_id=row.id,hashtag_id=ids[name]))
    op.drop_column('video_clip','hashtags')
def downgrade():
    op.add_column('video_clip',sa.Column('hashtags',sa.JSON,nullable=False,server_default='[]'))
    conn=op.get_bind();rows=conn.execute(sa.text('SELECT p.video_clip_id,h.name_tag FROM video_clip_hashtags p JOIN hashtags h ON h.id=p.hashtag_id ORDER BY h.name_tag'));grouped={}
    for row in rows:grouped.setdefault(row.video_clip_id,[]).append(row.name_tag)
    table=sa.table('video_clip',sa.column('id',sa.String),sa.column('hashtags',sa.JSON))
    for vid,names in grouped.items():conn.execute(table.update().where(table.c.id==vid).values(hashtags=names))
    op.drop_table('video_clip_hashtags');op.drop_table('hashtags')
