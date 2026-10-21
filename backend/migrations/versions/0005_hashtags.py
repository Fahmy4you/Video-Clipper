"""Replace footage categories with hashtags and snapshot project selection."""
from alembic import op
import sqlalchemy as sa
import re,unicodedata
revision='0005'
down_revision='0004'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('projects',sa.Column('mix_hashtags',sa.JSON,nullable=False,server_default='[]'))
    op.add_column('video_clip',sa.Column('hashtags',sa.JSON,nullable=False,server_default='[]'))
    table=sa.table('video_clip',sa.column('id',sa.String),sa.column('type',sa.String),sa.column('hashtags',sa.JSON))
    conn=op.get_bind()
    for row in conn.execute(sa.select(table.c.id,table.c.type)):
        tag=re.sub(r'[^\w]+','_',unicodedata.normalize('NFKC',row.type or '').casefold()).strip('_')[:50]
        conn.execute(table.update().where(table.c.id==row.id).values(hashtags=[tag] if tag else []))
    op.drop_column('video_clip','type')
def downgrade():
    op.add_column('video_clip',sa.Column('type',sa.String(100),nullable=False,server_default=''))
    table=sa.table('video_clip',sa.column('id',sa.String),sa.column('type',sa.String),sa.column('hashtags',sa.JSON))
    conn=op.get_bind()
    for row in conn.execute(sa.select(table.c.id,table.c.hashtags)):
        conn.execute(table.update().where(table.c.id==row.id).values(type=(row.hashtags or [''])[0]))
    op.drop_column('video_clip','hashtags');op.drop_column('projects','mix_hashtags')
