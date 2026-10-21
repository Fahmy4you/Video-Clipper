"""Mix library and generation mode."""
from alembic import op
import sqlalchemy as sa
revision='0004'
down_revision='0003'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('projects',sa.Column('visual_mode',sa.String(16),nullable=False,server_default='podcast'))
    op.create_table('video_clip',sa.Column('id',sa.String(36),primary_key=True),sa.Column('title',sa.String(200),nullable=False),sa.Column('url_path',sa.String(500),nullable=False),sa.Column('type',sa.String(100),nullable=False),sa.Column('explain',sa.String(4000),nullable=False),sa.Column('scenes',sa.JSON,nullable=False),sa.Column('duration',sa.Float,nullable=False),sa.Column('width',sa.Integer,nullable=False),sa.Column('height',sa.Integer,nullable=False),sa.Column('status',sa.String(24),nullable=False),sa.Column('error',sa.String(2000)),sa.Column('archived',sa.Boolean,nullable=False),sa.Column('revision',sa.Integer,nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
def downgrade():
    op.drop_table('video_clip');op.drop_column('projects','visual_mode')
